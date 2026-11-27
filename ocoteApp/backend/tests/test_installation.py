from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.errors import CommandError
from app.routers.setup import create_setup_app
from app.schemas.installation import Connection, secret_values
from app.services.installation import Setup


def connection(**changes):
    return Connection(
        **(
            {
                "mode": "local",
                "host": "127.0.0.1",
                "approved_address": "127.0.0.1",
                "port": 5432,
                "database": "ocoteAppDatabase",
                "runtime_role": "ocote_runtime",
                "migrator_role": "ocote_migrador",
                "runtime_password": "synthetic-runtime",
                "migrator_password": "synthetic-migrator",
                "sslmode": "disable",
            }
            | changes
        )
    )


@pytest.fixture
def setup(tmp_path):
    with (
        patch("app.services.installation.private_root"),
        patch(
            "app.services.installation.private_directory",
            side_effect=lambda path: path.mkdir(parents=True, exist_ok=True),
        ),
    ):
        yield Setup(tmp_path / "installation", "https://localhost:8443", legacy_paths=())


def test_existing_installation_never_becomes_virgin(tmp_path):
    legacy = tmp_path / ".env"
    legacy.touch()
    with pytest.raises(CommandError, match="SETUP_SEALED") as error:
        Setup(tmp_path / "new", "https://localhost:8443", legacy_paths=(legacy,))
    assert error.value.status == 403
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "remote.example"},
        {"runtime_role": "postgres"},
        {"runtime_password": "synthetic-migrator"},
        {"mode": "managed", "sslmode": "disable"},
    ],
)
def test_transport_and_roles_fail_closed(changes):
    with pytest.raises(ValidationError):
        connection(**changes)


def test_unavailable_database_is_not_empty(setup):
    with patch(
        "app.services.installation.probe",
        side_effect=CommandError(
            503,
            "SETUP_CONNECTION_UNAVAILABLE",
        ),
    ):
        with pytest.raises(CommandError):
            setup.test(connection())
    assert setup.tested is None
    assert not (setup.directory / "installing.json").exists()


def test_connection_context_does_not_hide_consumer_failure():
    from app.services.installation import connection_options

    with patch("app.services.installation.private_directory"):
        with pytest.raises(RuntimeError, match="SYNTHETIC_UPGRADE_STAGE"):
            with connection_options(connection()):
                raise RuntimeError("SYNTHETIC_UPGRADE_STAGE")


def test_actual_connection_failure_remains_sanitized():
    import psycopg

    from app.services.installation import probe

    with (
        patch("app.services.installation.private_directory"),
        patch(
            "app.services.installation.psycopg.connect",
            side_effect=psycopg.OperationalError("synthetic-secret-must-not-leak"),
        ),
    ):
        with pytest.raises(CommandError) as error:
            probe(connection())
    assert error.value.code == "SETUP_CONNECTION_UNAVAILABLE"
    assert error.value.status == 503
    assert "synthetic-secret" not in str(error.value)


def test_capability_origin_expiration_and_sealed(setup):
    setup.authorize(setup.code, setup.origin)
    for code, origin in [("wrong", setup.origin), (setup.code, "https://attacker.example")]:
        with pytest.raises(CommandError):
            setup.authorize(code, origin)
    setup.closed = True
    with pytest.raises(CommandError) as error:
        setup.authorize(setup.code, setup.origin)
    assert error.value.code == "SETUP_SEALED"


def test_http_sanitized_errors_and_no_secret_echo(setup):
    with TestClient(create_setup_app(setup), client=("127.0.0.1", 50000)) as client:
        denied = client.get("/api/v1/setup/status")
        assert denied.status_code == 403
        assert denied.headers["content-type"] == "application/problem+json"
        headers = {"Origin": setup.origin, "X-Setup-Code": setup.code}
        assert client.get("/api/v1/setup/status", headers=headers).status_code == 200
        paired = client.post("/api/v1/setup/pair", headers=headers, json={})
        assert paired.status_code == 200
        headers["X-Setup-Code"] = paired.json()["session_code"]
        with patch("app.services.installation.probe", return_value=["synthetic-database"]):
            response = client.post(
                "/api/v1/setup/connection-tests", headers=headers, json=secret_values(connection())
            )
        assert response.status_code == 200
        assert "password" not in response.text
        assert "request_id" in denied.json()


def test_installation_checkpoint_never_reopens_after_failure(setup):
    (setup.directory / "installing.json").write_text('{"state":"installing"}')
    with pytest.raises(CommandError) as error:
        setup.authorize(setup.code, setup.origin)
    assert error.value.code == "SETUP_RECOVERY_REQUIRED"


def test_expired_pairing_is_rejected(setup):
    setup.expires = 0
    with pytest.raises(CommandError) as error:
        setup.authorize(setup.code, setup.origin)
    assert error.value.status == 403


def test_pairing_code_is_consumed_once_without_renewal(setup):
    old, expiry = setup.code, setup.expires
    result = setup.pair()
    assert result["session_code"] != old
    assert setup.expires == expiry
    with pytest.raises(CommandError):
        setup.authorize(old, setup.origin)
    with pytest.raises(CommandError):
        setup.pair()


def test_existing_type_without_tables_is_not_a_virgin_database():
    from app.services.installation import inspect_role

    database = MagicMock()
    rows = [
        ("ocoteAppDatabase", 123, "127.0.0.1", 5432, "180004", "UTF8", "ocote_migrador"),
        (False, False, False, False, False, False),
        ("ocote_migrador", True, True, False),
        (1,),
        (0,),
        (1,),
    ]
    database.execute.side_effect = [MagicMock(fetchone=lambda row=row: row) for row in rows]
    with pytest.raises(CommandError) as error:
        inspect_role(database, connection(), "ocote_migrador")
    assert error.value.code == "SETUP_DATABASE_NOT_EMPTY"


def test_distributed_runtime_supports_sealed_local_profile_without_env():
    from tools.delivery_runtime import DeliverySettings

    settings = DeliverySettings(
        _env_file=None,
        app_env="production",
        deployment_mode="local",
        database_url="postgresql+psycopg://ocote_runtime:synthetic@"
        "127.0.0.1:5432/ocoteAppDatabase?sslmode=disable&hostaddr=127.0.0.1",
        health_token="synthetic-monitor-token-for-tests-only",
        organization_timezone="America/Mexico_City",
    )
    assert settings.app_env == "production"


def test_distributed_runtime_never_downgrades_managed_tls():
    from tools.delivery_runtime import DeliverySettings

    with pytest.raises(ValidationError):
        DeliverySettings(
            _env_file=None,
            app_env="production",
            deployment_mode="managed",
            database_url="postgresql+psycopg://ocote_runtime:synthetic@"
            "pg.example.invalid:5432/ocoteAppDatabase?sslmode=require",
            health_token="synthetic-monitor-token-for-tests-only",
            organization_timezone="America/Mexico_City",
        )
