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


def portable_values(**changes):
    from app.schemas.installation import PortableLocal
    return PortableLocal(**({"postgres_password": "Synthetic-Postgres-2026!",
                             "migrator_password": "Synthetic-Migrator-2026!",
                             "runtime_password": "Synthetic-Runtime-2026!"} | changes))


@pytest.fixture
def portable_cluster(tmp_path, monkeypatch):
    from app.services import portable_postgres as portable
    state, binaries = tmp_path / "state", tmp_path / "postgres"
    state.mkdir()
    for folder in ("bin", "lib", "share"):
        (binaries / folder).mkdir(parents=True)
    for name in portable.EXECUTABLES:
        (binaries / "bin" / name).write_bytes(b"synthetic-only; never execute")
    monkeypatch.setattr(portable, "private_root", lambda _path: None)
    monkeypatch.setattr(portable, "port_available", lambda _port: None)
    monkeypatch.setattr(portable, "verify_version", lambda _root: None)
    return portable.PortablePostgres(state, binaries, portable_values())


@pytest.mark.parametrize("changes", [{"database": "anotherDatabase"}, {"port": 0}, {"port": True},
                                    {"port": 65536}, {"postgres_password": "weak"},
                                    {"postgres_password": "aaaaaaaaaaaaaaaa"},
                                    {"runtime_password": "Synthetic-Migrator-2026!"}])
def test_portable_local_contract_rejects_database_port_and_weak_passwords(changes):
    with pytest.raises(ValidationError):
        portable_values(**changes)


def test_portable_data_must_be_empty_below_private_state(portable_cluster):
    from app.services.portable_postgres import state_data_directory
    with pytest.raises(CommandError):
        state_data_directory(portable_cluster.state, "../outside")
    portable_cluster.data.mkdir()
    (portable_cluster.data / "PG_VERSION").write_text("synthetic existing cluster")
    with pytest.raises(CommandError) as error:
        portable_cluster.validate()
    assert error.value.code == "SETUP_LOCAL_DATA_NOT_EMPTY"


def test_portable_sealed_state_is_never_reinitialized(portable_cluster):
    (portable_cluster.state / "sealed.json").write_text('{"state":"sealed"}')
    with pytest.raises(CommandError) as error:
        portable_cluster.validate()
    assert error.value.code == "SETUP_LOCAL_EXISTING_STATE"


def test_portable_occupied_loopback_port_is_rejected():
    from app.services.portable_postgres import port_available
    listener = MagicMock()
    listener.__enter__.return_value.bind.side_effect = OSError("synthetic port occupied")
    with patch("app.services.portable_postgres.socket.socket", return_value=listener):
        with pytest.raises(CommandError) as error:
            port_available(5432)
    assert error.value.code == "SETUP_LOCAL_PORT_IN_USE"


def test_portable_prepares_cluster_roles_and_exact_database_without_password_argv(
    portable_cluster, monkeypatch,
):
    from pathlib import Path

    from app.services import portable_postgres as portable
    commands = []
    def run(binary, arguments, state, **options):
        commands.append((binary.name, [str(value) for value in arguments]))
        if binary.name == "initdb.exe":
            password_file = Path(next(value.split("=", 1)[1] for value in arguments
                                      if str(value).startswith("--pwfile=")))
            assert password_file.read_text().strip() == "Synthetic-Postgres-2026!"
        return 0
    monkeypatch.setattr(portable, "native_command", run)
    admin = MagicMock()
    admin.execute.return_value.fetchone.return_value = (
        "postgres", str(portable_cluster.data), "180004",
    )
    admin.pgconn.encrypt_password.return_value = b"SCRAM-SHA-256$synthetic-verifier"
    connector = MagicMock()
    connector.return_value.__enter__.return_value = admin
    monkeypatch.setattr(portable.psycopg, "connect", connector)
    metadata = portable_cluster.prepare()
    assert [name for name, _ in commands] == ["initdb.exe", "pg_ctl.exe"]
    assert "--auth=scram-sha-256" in commands[0][1]
    assert "Synthetic-" not in repr(commands)
    assert not list(portable_cluster.state.glob("local-password-*"))
    sql_commands = [call.args[0].as_string() if hasattr(call.args[0], "as_string")
                    else str(call.args[0]) for call in admin.execute.call_args_list]
    assert any('CREATE DATABASE "ocoteAppDatabase"' in command for command in sql_commands)
    assert any("CREATE EXTENSION btree_gist" in command for command in sql_commands)
    assert not any("Synthetic-" in command for command in sql_commands)
    assert metadata["host"] == "127.0.0.1" and metadata["port"] == 5432


def test_portable_initdb_failure_removes_password_and_never_seals(portable_cluster, monkeypatch):
    from app.services import portable_postgres as portable
    monkeypatch.setattr(portable, "native_command", MagicMock(side_effect=CommandError(
        503, "SETUP_LOCAL_PREPARATION_FAILED",
    )))
    with pytest.raises(CommandError):
        portable_cluster.prepare()
    assert not list(portable_cluster.state.glob("local-password-*"))
    assert not (portable_cluster.state / "sealed.json").exists()


def test_local_install_runs_provision_then_existing_install_without_external_changes(setup):
    from types import SimpleNamespace

    from app.schemas.installation import LocalInstall
    command = LocalInstall(local=portable_values(), organization_timezone="America/Mexico_City",
                           admin={"email": "synthetic@example.invalid", "display_name": "Synthetic",
                                  "password": "Synthetic-Admin-2026!", "role": "admin",
                                  "reason": "Explicit synthetic local installation"})
    cluster = MagicMock(created=True)
    cluster.prepare.return_value = {"kind": "local-portable-v1"}
    with patch.object(setup, "local_check"), patch(
        "app.services.portable_postgres.PortablePostgres", return_value=cluster,
    ), patch.object(setup, "test", return_value={"test_id": "a" * 32}), patch.object(
        setup, "install", return_value={"state": "sealed"},
    ) as install:
        assert setup.install_local(command, SimpleNamespace(state=SimpleNamespace(
            request_id="synthetic-request"))) == {"state": "sealed"}
    assert install.call_args.args[0].connection.database == "ocoteAppDatabase"
    assert install.call_args.args[0].connection.sslmode == "disable"
    cluster.stop_failed_attempt.assert_not_called()


def test_local_install_failure_stops_its_cluster_and_never_seals(setup):
    from types import SimpleNamespace

    from app.schemas.installation import LocalInstall
    command = LocalInstall(local=portable_values(), organization_timezone="America/Mexico_City",
                           admin={"email": "synthetic@example.invalid", "display_name": "Synthetic",
                                  "password": "Synthetic-Admin-2026!", "role": "admin",
                                  "reason": "Explicit synthetic local installation"})
    cluster = MagicMock(created=True)
    cluster.prepare.side_effect = CommandError(503, "SETUP_LOCAL_PREPARATION_FAILED")
    with patch.object(setup, "local_check"), patch(
        "app.services.portable_postgres.PortablePostgres", return_value=cluster,
    ):
        with pytest.raises(CommandError):
            setup.install_local(command, SimpleNamespace(state=SimpleNamespace(
                request_id="synthetic-request")))
    cluster.stop_failed_attempt.assert_called_once()
    assert not (setup.directory / "sealed.json").exists()
    assert (setup.directory / "local-failure.json").exists()


@pytest.mark.parametrize("running", [False, True])
def test_portable_runtime_starts_only_its_sealed_cluster(portable_cluster, monkeypatch, running):
    import json

    from app.services import portable_postgres as portable
    portable_cluster.data.mkdir()
    (portable_cluster.data / "PG_VERSION").write_text("18\n")
    metadata = {"kind": "local-portable-v1", "host": "127.0.0.1", "port": 5432,
                "major": 18, "data_directory": str(portable_cluster.data)}
    (portable_cluster.state / "portable-postgres.json").write_text(json.dumps(metadata))
    pid = portable_cluster.data / "postmaster.pid"
    def write_pid():
        pid.write_text("9999\n" + str(portable_cluster.data) + "\n0\n5432\n")
    if running:
        write_pid()
    calls = []
    def command(binary, arguments, _state, **_options):
        calls.append([str(value) for value in arguments])
        if "status" in arguments:
            return 0 if running else 3
        if "start" in arguments:
            write_pid()
        return 0
    monkeypatch.setattr(portable, "native_command", command)
    monkeypatch.setattr(portable, "process_matches", lambda *_args: True)
    result = portable.ensure_started(portable_cluster.state, metadata, portable_cluster.binaries)
    assert result["already_running"] is running
    assert any("start" in values for values in calls) is (not running)
    assert not (portable_cluster.state / "postgres-start.lock").exists()
    assert all("initdb" not in str(value) for value in calls)


def test_portable_runtime_never_removes_or_reuses_residual_pid(portable_cluster, monkeypatch):
    import json

    from app.services import portable_postgres as portable
    portable_cluster.data.mkdir()
    (portable_cluster.data / "PG_VERSION").write_text("18\n")
    metadata = {"kind": "local-portable-v1", "host": "127.0.0.1", "port": 5432,
                "major": 18, "data_directory": str(portable_cluster.data)}
    (portable_cluster.state / "portable-postgres.json").write_text(json.dumps(metadata))
    pid = portable_cluster.data / "postmaster.pid"
    pid.write_text("synthetic residual; must not remove")
    monkeypatch.setattr(portable, "native_command", lambda *_args, **_options: 3)
    with pytest.raises(CommandError) as error:
        portable.ensure_started(portable_cluster.state, metadata, portable_cluster.binaries)
    assert error.value.code == "SETUP_LOCAL_RECOVERY_REQUIRED"
    assert pid.read_text() == "synthetic residual; must not remove"


def test_portable_major_version_is_checked_before_initializing(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services.portable_postgres import verify_version
    with patch("app.services.portable_postgres.subprocess.run", return_value=SimpleNamespace(
        returncode=0, stdout="postgres (PostgreSQL) 19.0",
    )):
        with pytest.raises(CommandError) as error:
            verify_version(tmp_path)
    assert error.value.code == "SETUP_PORTABLE_VERSION_REJECTED"


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
