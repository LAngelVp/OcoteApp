import json
import tempfile
from pathlib import Path
from uuid import UUID

from pydantic import SecretStr, field_validator, model_validator
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.core.errors import CommandError
from app.core.evidence import private_root
from app.core.security import AuthSettings, Tokens
from app.core.vault import OSSealedFile
from app.main import create_app
from app.schemas.installation import https_origin
from app.services.installation import private_directory, write_private


class DeliverySettings(Settings):
    @field_validator("database_url")
    @classmethod
    def _database(cls, value):
        url = make_url(value.get_secret_value())
        if (
            url.drivername != "postgresql+psycopg"
            or url.username != "ocote_runtime"
            or url.database != "ocoteAppDatabase"
            or not url.password
            or not url.host
            or url.port is None
            or set(url.query) - {"sslmode", "sslrootcert", "hostaddr"}
        ):
            raise ValueError("Invalid sealed runtime connection")
        return value

    @model_validator(mode="after")
    def valid_transport(self):
        url = make_url(self.database_url.get_secret_value())
        if self.deployment_mode == "local":
            if url.host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Local transport requires loopback")
        else:
            self.validate_transport(self.database_url)
        return self


class DeliveryAuth(AuthSettings):
    @model_validator(mode="after")
    def local_https_only(self):
        https_origin(self.auth_origin)
        return self


def read_bootstrap(directory):
    directory = Path(directory).absolute()
    private_root(directory)
    receipt = json.loads((directory / "sealed.json").read_text())
    identity = UUID(receipt["instance"])
    sealed = json.loads(OSSealedFile(directory / "bootstrap.dpapi", identity).read())
    if (
        receipt.get("state") != "sealed"
        or sealed.get("state") != "sealed"
        or sealed.get("instance") != str(identity)
        or "migrator_password" in sealed["connection"]
    ):
        raise CommandError(503, "SETUP_SEAL_FAILED")
    return sealed


def runtime_app(directory):
    directory = Path(directory).absolute()
    sealed = read_bootstrap(directory)
    if "portable_postgres" in sealed:
        from app.services.portable_postgres import ensure_started
        from tools.delivery import ROOT
        ensure_started(directory, sealed["portable_postgres"], ROOT / "postgres")
    connection = sealed["connection"]
    query = {"sslmode": connection["sslmode"], "hostaddr": connection["approved_address"]}
    if connection["mode"] == "managed":
        ca = directory / "runtime-ca.crt"
        if not ca.exists():
            write_private(ca, connection["ca_pem"].encode("ascii"))
        if ca.is_symlink() or ca.read_text() != connection["ca_pem"]:
            raise CommandError(503, "SETUP_SEAL_FAILED")
        query["sslrootcert"] = str(ca)
    url = URL.create(
        "postgresql+psycopg",
        username="ocote_runtime",
        password=connection["runtime_password"],
        host=connection["host"],
        port=connection["port"],
        database=connection["database"],
        query=query,
    )
    settings = DeliverySettings(
        _env_file=None,
        app_env="production",
        deployment_mode=connection["mode"],
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        health_token=sealed["health_token"],
        organization_timezone=sealed["organization_timezone"],
    )
    with tempfile.TemporaryDirectory(prefix="ocote-runtime-") as temporary:
        root = Path(temporary).resolve()
        private_directory(root)
        write_private(root / "signing.key", sealed["signing_key"].encode("ascii"))
        write_private(root / "csrf.key", bytes.fromhex(sealed["csrf"]))
        auth = DeliveryAuth(
            _env_file=None,
            app_env="production",
            deployment_mode=connection["mode"],
            auth_origin=sealed["auth_origin"],
            jwt_private_key_file=root / "signing.key",
            csrf_secret_file=root / "csrf.key",
        )
        tokens = Tokens(auth)
    identity = sealed["instance"]
    from app.services.installation import HEAD, canonical
    from tools.delivery import ROOT, sha

    manifest_hash = sha(canonical(json.loads((ROOT / "manifest.json").read_text())))
    sealed.clear()
    app = create_app(settings, tokens=tokens)

    @app.middleware("http")
    async def monitor_identity(request, call_next):
        if (directory / "maintenance.json").exists() and request.url.path not in {
            "/api/v1/health/live",
            "/api/v1/health/ready",
        }:
            from app.core.errors import problem

            return problem(request, 503, "MAINTENANCE", "Runtime is fenced for maintenance.")
        response = await call_next(request)
        if request.url.path == "/api/v1/health/ready" and response.status_code == 200:
            response.headers["X-OCOTE-Instance"] = identity
            response.headers["X-OCOTE-Head"] = HEAD
            response.headers["X-OCOTE-Manifest"] = manifest_hash
        return response

    return app
