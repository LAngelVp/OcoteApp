import hashlib
import hmac
import importlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import monotonic
from uuid import uuid4

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.evidence import private_root
from app.core.vault import OSSealedFile
from app.models.platform import DeploymentInstance
from app.schemas.installation import Connection, Install, https_origin, secret_values
from app.services.identity import bootstrap_admin
from app.services.platform import seal_path

HEAD = "20261126_0011"
LOCK_KEY = 726_018_241


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True).encode("ascii")


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami"], check=True, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(OI)(CI)F"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    else:
        path.chmod(0o700)
    private_root(path)


def write_private(path, content):
    private_root(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def connection_options(body: Connection):
    with ExitStack() as stack:
        try:
            addresses = {
                entry[4][0]
                for entry in socket.getaddrinfo(body.host, body.port, type=socket.SOCK_STREAM)
            }
            if body.approved_address not in addresses:
                raise CommandError(409, "SETUP_ADDRESS_CHANGED")
            directory = Path(
                stack.enter_context(tempfile.TemporaryDirectory(prefix="ocote-ca-"))
            ).resolve()
            private_directory(directory)
            options = {
                "host": body.host,
                "hostaddr": body.approved_address,
                "port": body.port,
                "dbname": body.database,
                "sslmode": body.sslmode,
                "connect_timeout": 3,
                "application_name": "ocote-setup",
                "options": "-c timezone=UTC -c statement_timeout=60000 -c lock_timeout=5000",
            }
            if body.mode == "managed":
                certificates = x509.load_pem_x509_certificates(body.ca_pem.encode("ascii"))
                if not certificates or any(
                    not certificate.extensions.get_extension_for_class(
                        x509.BasicConstraints,
                    ).value.ca
                    for certificate in certificates
                ):
                    raise ValueError("Invalid CA")
                write_private(directory / "ca.pem", body.ca_pem.encode("ascii"))
                options["sslrootcert"] = str(directory / "ca.pem")
        except CommandError:
            raise
        except Exception:
            raise CommandError(503, "SETUP_CONNECTION_UNAVAILABLE") from None
        yield options


def role_options(options, body, role):
    return {
        **options,
        "user": role,
        "password": (
            body.runtime_password if role == "ocote_runtime" else body.migrator_password
        ).get_secret_value(),
    }


def inspect_role(connection, body, role, *, virgin=True):
    identity = connection.execute(
        "SELECT current_database(), (SELECT oid FROM pg_database WHERE datname=current_database()),"
        " host(inet_server_addr()), inet_server_port(), current_setting('server_version_num'),"
        " current_setting('server_encoding'), current_user"
    ).fetchone()
    if (
        identity[0] != body.database
        or (body.mode == "local" and identity[2] != body.approved_address)
        or (body.mode == "local" and identity[3] != body.port)
        or not 180000 <= int(identity[4]) < 190000
        or identity[5:] != ("UTF8", role)
    ):
        raise CommandError(409, "SETUP_DATABASE_IDENTITY")
    attributes = connection.execute(
        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,"
        " EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid)"
        " FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    if attributes is None or any(attributes):
        raise CommandError(409, "SETUP_ROLE_PERMISSIONS")
    schema = connection.execute(
        "SELECT pg_get_userbyid(nspowner),has_schema_privilege(current_user,oid,'USAGE'),"
        " has_schema_privilege(current_user,oid,'CREATE'),"
        " EXISTS(SELECT 1 FROM aclexplode(coalesce(nspacl,acldefault('n',nspowner)))"
        " WHERE grantee=0 AND privilege_type='CREATE') FROM pg_namespace WHERE nspname='public'"
    ).fetchone()
    if (
        not schema
        or schema != ("ocote_migrador", True, role == "ocote_migrador", False)
        or (
            role == "ocote_runtime"
            and connection.execute(
                "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
            ).fetchone()[0]
        )
    ):
        raise CommandError(409, "SETUP_ROLE_PERMISSIONS")
    if (
        connection.execute(
            "SELECT count(*) FROM pg_extension WHERE extname='btree_gist'"
        ).fetchone()[0]
        != 1
    ):
        raise CommandError(409, "SETUP_EXTENSION_REQUIRED")
    if (
        body.mode == "managed"
        and not connection.execute(
            "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
        ).fetchone()[0]
    ):
        raise CommandError(409, "SETUP_TLS_REQUIRED")
    if virgin:
        extensions = connection.execute(
            "SELECT count(*) FROM pg_extension WHERE extname NOT IN ('plpgsql','btree_gist')"
        ).fetchone()[0]
        types = connection.execute(
            "WITH RECURSIVE permitted(oid) AS ("
            "SELECT objid FROM pg_depend WHERE classid='pg_type'::regclass AND deptype='e'"
            " AND refclassid='pg_extension'::regclass AND refobjid=("
            "SELECT oid FROM pg_extension WHERE extname='btree_gist') UNION "
            "SELECT d.objid FROM pg_depend d JOIN permitted p ON d.refobjid=p.oid"
            " WHERE d.classid='pg_type'::regclass AND d.refclassid='pg_type'::regclass"
            " AND d.deptype IN ('a','i')) SELECT count(*) FROM pg_type t"
            " JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_'"
            " AND n.nspname<>'information_schema' AND t.oid NOT IN(SELECT oid FROM permitted)"
        ).fetchone()[0]
        if extensions or types:
            raise CommandError(409, "SETUP_DATABASE_NOT_EMPTY")
        objects = connection.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
            " WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'"
            " AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass"
            " AND d.objid=c.oid AND d.deptype='e')"
        ).fetchone()[0]
        routines = connection.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace"
            " WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'"
            " AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass"
            " AND d.objid=p.oid AND d.deptype='e')"
        ).fetchone()[0]
        schemas = connection.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname !~ '^pg_'"
            " AND nspname NOT IN ('public','information_schema')"
        ).fetchone()[0]
        if objects or routines or schemas:
            raise CommandError(409, "SETUP_DATABASE_NOT_EMPTY")
    return list(identity[:6])


def probe(body):
    with connection_options(body) as options:
        identities = []
        for role in ("ocote_runtime", "ocote_migrador"):
            try:
                connected = psycopg.connect(**role_options(options, body, role), autocommit=True)
            except psycopg.OperationalError:
                raise CommandError(503, "SETUP_CONNECTION_UNAVAILABLE") from None
            with connected as connection:
                connection.execute("BEGIN READ ONLY")
                try:
                    identities.append(inspect_role(connection, body, role))
                finally:
                    connection.execute("ROLLBACK")
        if identities[0] != identities[1]:
            raise CommandError(409, "SETUP_DATABASE_IDENTITY")
        return identities[0]


class Setup:
    def __init__(self, directory, origin, *, legacy_paths=None, portable_directory=None):
        if os.name != "nt":
            raise CommandError(503, "OS_SEAL_PLATFORM_NOT_VERIFIED")
        self.directory = Path(directory).absolute()
        self.origin = https_origin(origin)
        legacy = (
            legacy_paths
            if legacy_paths is not None
            else (
                BACKEND_DIR / ".env",
                BACKEND_DIR / ".local",
            )
        )
        if any(path.exists() for path in legacy) or os.environ.get("DATABASE_URL"):
            raise CommandError(403, "SETUP_SEALED")
        if self.directory.exists():
            raise CommandError(409, "SETUP_EXISTING_STATE")
        private_directory(self.directory)
        self.identity = uuid4()
        self.code = secrets.token_urlsafe(32)
        self.paired = False
        self.expires = monotonic() + 900
        self.tested = None
        self.lock = RLock()
        self.closed = False
        self.portable_directory = Path(portable_directory or BACKEND_DIR.parent / "postgres")
        self.portable_metadata = None
        write_private(
            self.directory / "prepared.json",
            canonical(
                {
                    "instance": str(self.identity),
                    "origin": self.origin,
                    "state": "prepared",
                }
            ),
        )

    def authorize(self, code, origin, *, require_pair=False):
        private_root(self.directory)
        if self.closed or (self.directory / "sealed.json").exists():
            raise CommandError(403, "SETUP_SEALED")
        if (self.directory / "installing.json").exists():
            raise CommandError(409, "SETUP_RECOVERY_REQUIRED")
        if (
            monotonic() >= self.expires
            or origin != self.origin
            or not code
            or not hmac.compare_digest(code, self.code)
        ):
            raise CommandError(403, "SETUP_CAPABILITY_INVALID")
        if require_pair and not self.paired:
            raise CommandError(409, "SETUP_PAIR_REQUIRED")

    def pair(self):
        if self.paired:
            raise CommandError(409, "SETUP_ALREADY_PAIRED")
        self.paired = True
        self.code = secrets.token_urlsafe(32)
        write_private(self.directory / "paired.json", canonical({"state": "paired"}))
        return {"session_code": self.code}

    def fingerprint(self, body):
        return hmac.digest(self.code.encode(), canonical(secret_values(body)), "sha256")

    def local_check(self, body):
        from app.services.portable_postgres import PortablePostgres
        if self.closed or any((self.directory / name).exists() for name in (
            "sealed.json", "installing.json", "local-failure.json",
        )):
            raise CommandError(403, "SETUP_SEALED")
        return PortablePostgres(self.directory, self.portable_directory, body).validate()

    def install_local(self, body, request):
        from app.services.portable_postgres import PortablePostgres
        if not self.lock.acquire(blocking=False):
            raise CommandError(409, "SETUP_BUSY")
        cluster = None
        try:
            self.local_check(body.local)
            cluster = PortablePostgres(self.directory, self.portable_directory, body.local)
            self.portable_metadata = cluster.prepare()
            connection = body.local.connection()
            tested = self.test(connection)
            command = Install(connection=connection, test_id=tested["test_id"],
                              admin=body.admin, organization_timezone=body.organization_timezone)
            return self.install(command, request)
        except Exception as error:
            stop_error = None
            if cluster is not None and not self.closed:
                try:
                    cluster.stop_failed_attempt()
                except Exception as stopping:
                    stop_error = getattr(stopping, "code", "SETUP_LOCAL_STOP_FAILED")
                if cluster.created and not (self.directory / "local-failure.json").exists():
                    write_private(self.directory / "local-failure.json", canonical({
                        "state": "failed", "request_id": request.state.request_id,
                        "code": getattr(error, "code", "SETUP_LOCAL_INSTALL_FAILED"),
                        "stop_error": stop_error, "sealed": False,
                    }))
            self.tested = None
            if stop_error:
                raise CommandError(503, "SETUP_LOCAL_RECOVERY_REQUIRED") from None
            if isinstance(error, CommandError):
                raise
            raise CommandError(503, "SETUP_LOCAL_INSTALL_FAILED") from None
        finally:
            self.lock.release()

    def test(self, body):
        self.tested = None
        identity = probe(body)
        token = uuid4().hex
        self.tested = (token, self.fingerprint(body), monotonic(), identity)
        return {
            "test_id": token,
            "expires_in": 600,
            "roles_verified": True,
            "tls_verified": body.mode == "managed",
            "target_head": HEAD,
        }

    def install(self, body: Install, request):
        if not self.lock.acquire(blocking=False):
            raise CommandError(409, "SETUP_BUSY")
        try:
            if self.closed or (self.directory / "installing.json").exists():
                raise CommandError(403, "SETUP_SEALED")
            tested = self.tested
            if (
                not tested
                or tested[0] != body.test_id
                or monotonic() - tested[2] >= 600
                or not hmac.compare_digest(tested[1], self.fingerprint(body.connection))
            ):
                raise CommandError(409, "SETUP_TEST_REQUIRED")
            if probe(body.connection) != tested[3]:
                raise CommandError(409, "SETUP_DATABASE_IDENTITY")
            result = install_new(self, body, request)
            self.closed = True
            self.code = ""
            self.tested = None
            return result
        finally:
            self.lock.release()


def install_new(setup, body, request):
    with connection_options(body.connection) as options:
        with psycopg.connect(
            **role_options(options, body.connection, "ocote_migrador"), autocommit=True
        ) as guard:
            if not guard.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
                raise CommandError(409, "SETUP_BUSY")
            try:
                inspect_role(guard, body.connection, "ocote_migrador")
                config = Config(str(BACKEND_DIR / "alembic.ini"))
                config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
                if ScriptDirectory.from_config(config).get_heads() != [HEAD]:
                    raise CommandError(409, "SETUP_ARTIFACT_INVALID")
                write_private(
                    setup.directory / "installing.json",
                    canonical(
                        {
                            "state": "installing",
                            "request_id": request.state.request_id,
                            "instance": str(setup.identity),
                            "target": HEAD,
                        }
                    ),
                )
                engine = create_engine(
                    "postgresql+psycopg://",
                    hide_parameters=True,
                    creator=lambda: psycopg.connect(
                        **role_options(options, body.connection, "ocote_migrador")
                    ),
                )
                try:
                    with engine.connect() as connection:
                        config.attributes.update(
                            connection=connection, expected_database=body.connection.database
                        )
                        command.upgrade(config, HEAD)
                        importlib.import_module("app.main")
                        from tools import delivery_support

                        support = (
                            delivery_support.load_support()
                            if hasattr(delivery_support, "load_support")
                            else delivery_support
                        )
                        first = support.snapshot(guard)
                        command.upgrade(config, HEAD)
                        if support.snapshot(guard) != first or len(first["tables"]) != 72:
                            raise CommandError(409, "SETUP_MIGRATION_NOT_NOOP")
                        if connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalars().all() != [HEAD]:
                            raise CommandError(409, "SETUP_HEAD_INVALID")
                        if connection.execute(
                            text("SELECT count(*) FROM pg_constraint WHERE NOT convalidated")
                        ).scalar_one():
                            raise CommandError(409, "SETUP_CONSTRAINT_INVALID")
                        connection.rollback()
                    with psycopg.connect(
                        **role_options(options, body.connection, "ocote_runtime"),
                        autocommit=True,
                    ) as runtime:
                        inspect_role(runtime, body.connection, "ocote_runtime", virgin=False)
                        if any(
                            not runtime.execute(
                                "SELECT has_table_privilege(current_user,%s,'SELECT')",
                                (table,),
                            ).fetchone()[0]
                            for table in first["tables"]
                        ):
                            raise CommandError(409, "SETUP_RUNTIME_GRANTS_INVALID")
                    root = secrets.token_bytes(32)
                    root_path = seal_path(setup.identity)
                    private_directory(root_path.parent)
                    OSSealedFile(root_path, setup.identity).create(root)
                    if OSSealedFile(root_path, setup.identity).read() != root:
                        raise CommandError(503, "SETUP_SEAL_FAILED")
                    with Session(engine) as database, database.begin():
                        database.add(
                            DeploymentInstance(id=setup.identity, root_key_ref="windows-dpapi-v1")
                        )
                        bootstrap_admin(
                            database,
                            email=body.admin.email,
                            display_name=body.admin.display_name,
                            password=body.admin.password.get_secret_value(),
                            request=request,
                        )
                        timestamp = datetime.now(UTC)
                        attempt = uuid4()
                        artifact = hashlib.sha256(support.canonical(first)).hexdigest()
                        database.execute(
                            text(
                                "INSERT INTO release_history(id,created_at,updated_at,"
                                "application_version,artifact_sha256,manifest_sha256,source_revision,"
                                "target_revision,operator_ref,deployment_mode,phase,status,request_id)"
                                " VALUES(:id,:at,:at,'0.13.0',:hash,:hash,NULL,:head,"
                                ":operator,:mode,"
                                "'validation','running',:request)"
                            ),
                            {
                                "id": attempt,
                                "at": timestamp,
                                "hash": artifact,
                                "head": HEAD,
                                "operator": body.admin.display_name,
                                "mode": body.connection.mode,
                                "request": request.state.request_id,
                            },
                        )
                    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
                    signing = key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                    bootstrap = {
                        "connection": {
                            name: value
                            for name, value in secret_values(body.connection).items()
                            if name != "migrator_password"
                        },
                        "auth_origin": setup.origin,
                        "organization_timezone": body.organization_timezone,
                        "health_token": secrets.token_urlsafe(32),
                        "csrf": secrets.token_hex(32),
                        "signing_key": signing.decode("ascii"),
                        "instance": str(setup.identity),
                        "state": "sealed",
                    }
                    if setup.portable_metadata is not None:
                        bootstrap["portable_postgres"] = setup.portable_metadata
                    OSSealedFile(setup.directory / "bootstrap.dpapi", setup.identity).create(
                        canonical(bootstrap),
                    )
                    with engine.begin() as connection:
                        if (
                            connection.execute(
                                text(
                                    "UPDATE release_history SET version=version+1,updated_at=:at,"
                                    "finished_at=:at,phase='complete',status='succeeded',"
                                    "result_code='INSTALL_LOCAL_VERIFIED'"
                                    " WHERE id=:id AND version=1"
                                    " AND status='running' AND phase='validation'"
                                ),
                                {"at": datetime.now(UTC), "id": attempt},
                            ).rowcount
                            != 1
                        ):
                            raise CommandError(409, "SETUP_LEDGER_CAS_FAILED")
                    write_private(
                        setup.directory / "sealed.json",
                        canonical(
                            {
                                "state": "sealed",
                                "instance": str(setup.identity),
                                "head": HEAD,
                                "request_id": request.state.request_id,
                            }
                        ),
                    )
                    return {"state": "sealed", "login_path": "/login", "head": HEAD}
                finally:
                    engine.dispose()
            finally:
                guard.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
