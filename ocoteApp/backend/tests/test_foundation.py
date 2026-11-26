from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import MigrationSettings, Settings
from app.db.session import get_session, unit_of_work
from app.main import create_app

RUNTIME_URL = "postgresql+psycopg://ocote_runtime:synthetic@127.0.0.1:5432/ocoteAppDatabase"
TOKEN = "synthetic-monitor-token-for-tests-only"


def settings(**overrides):
    values = {
        "_env_file": None,
        "database_url": RUNTIME_URL,
        "health_token": TOKEN,
        "organization_timezone": "America/Mexico_City",
        "app_env": "test",
    }
    return Settings(**(values | overrides))


@pytest.fixture
def app(tmp_path):
    with patch("app.routers.health.BACKEND_DIR", tmp_path):
        yield create_app(settings())


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def test_live_does_not_connect_and_only_authorized_f9_routes(app, client):
    app.state.session_factory = MagicMock(side_effect=AssertionError)
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    paths = set(app.openapi()["paths"])
    assert {"/api/v1/health/live", "/api/v1/health/ready", "/api/v1/auth/login"} <= paths
    allowed = {
        "health",
        "auth",
        "departments",
        "users",
        "workflow-stages",
        "workflow-transitions",
        "workflow",
        "settings",
        "priorities",
        "horizon-types",
        "catalogs",
        "configuration-status",
        "audit-events",
        "release-history",
        "releases",
        "annual-plans",
        "objectives",
        "tasks",
        "subtasks",
        "due-date-requests",
        "kanban",
        "timeline",
        "evidence",
        "analytics",
        "evaluations",
        "exports",
        "admin",
        "configuration",
        "branding",
        "calendar",
        "collaboration",
    }
    assert all(path.split("/")[3] in allowed for path in paths)
    assert {path for path in paths if path.startswith("/api/v1/admin/")} == {
        "/api/v1/admin/health",
        "/api/v1/admin/custody",
        "/api/v1/admin/vault",
        "/api/v1/admin/vault/rotate",
        "/api/v1/admin/vault/{owner}/{purpose}",
        "/api/v1/admin/integrations/{kind}",
        "/api/v1/admin/integrations/{kind}/test",
        "/api/v1/admin/integrations/{kind}/activation",
        "/api/v1/admin/configuration",
        "/api/v1/admin/security-policy",
        "/api/v1/admin/feature-flags",
        "/api/v1/admin/branding",
        "/api/v1/admin/branding/reset",
        "/api/v1/admin/branding/logo",
        "/api/v1/admin/calendars",
        "/api/v1/admin/calendars/{identity}",
        "/api/v1/admin/calendars/{identity}/holidays",
        "/api/v1/admin/calendars/{identity}/holidays/{holiday_id}",
        "/api/v1/admin/calendar-preview",
        "/api/v1/admin/object-storage",
        "/api/v1/admin/object-storage/{identity}",
        "/api/v1/admin/object-storage/{identity}/test",
        "/api/v1/admin/object-storage/{identity}/activation",
    }
    assert {path for path in paths if path.split("/")[3] in {
        "configuration", "branding", "calendar"
    }} == {"/api/v1/configuration", "/api/v1/branding/logo/{identity}",
           "/api/v1/calendar/preview"}
    assert client.get("/openapi.json").status_code == 404
    UUID(response.headers["x-request-id"])


def test_maintenance_blocks_readiness(app, client, tmp_path):
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local" / "maintenance.json").write_text("{}")
    session = MagicMock()
    app.dependency_overrides[get_session] = lambda: session
    with patch("app.routers.health.BACKEND_DIR", tmp_path):
        response = client.get("/api/v1/health/ready", headers={"X-Health-Token": TOKEN})
    assert response.status_code == 503
    session.execute.assert_not_called()


@pytest.mark.parametrize("token", [None, "wrong"])
def test_ready_requires_monitor_before_database(app, client, token):
    def forbidden_session():
        raise AssertionError("Database must not be accessed")
        yield

    app.dependency_overrides[get_session] = forbidden_session
    response = client.get(
        "/api/v1/health/ready",
        headers={"X-Health-Token": token} if token else {},
    )
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    "database,heads,status",
    [
        ("ocoteAppDatabase", ["20261125_0008"], 200),
        ("ocote_f2_00000000000000000000000000000000", ["20261125_0008"], 503),
        ("ocoteAppDatabase", ["20261125_0007"], 503),
        ("ocoteAppDatabase", ["20261125_0006"], 503),
        ("ocoteAppDatabase", ["20261125_0005"], 503),
        ("ocoteAppDatabase", ["20261124_0003"], 503),
        ("ocoteAppDatabase", ["20261124_0002"], 503),
        ("ocoteAppDatabase", ["20261124_0001"], 503),
        ("ocote", ["20261124_0001"], 503),
        ("ocoteAppDatabase", [], 503),
        ("ocoteAppDatabase", ["unknown"], 503),
        ("ocoteAppDatabase", ["20261124_0001", "another_head"], 503),
    ],
)
def test_ready_checks_database_and_exact_revision(app, client, database, heads, status):
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = database
    app.dependency_overrides[get_session] = lambda: session
    with patch("app.routers.health.MigrationContext.configure") as context:
        context.return_value.get_current_heads.return_value = heads
        response = client.get("/api/v1/health/ready", headers={"X-Health-Token": TOKEN})
    assert response.status_code == status
    assert "20261124" not in response.text


def test_database_failure_never_leaks_secrets(app, client):
    session = MagicMock()
    session.execute.side_effect = OperationalError("SELECT secret", {}, Exception("private DSN"))
    app.dependency_overrides[get_session] = lambda: session
    response = client.get("/api/v1/health/ready", headers={"X-Health-Token": TOKEN})
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "private" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_unexpected_and_validation_errors_are_sanitized(app, client):
    @app.get("/test-error")
    def error():
        raise RuntimeError("secret-password")

    @app.get("/test-input")
    def invalid(value: int):
        return value

    @app.get("/test-auth")
    def auth():
        raise HTTPException(401, detail="secret-password")

    for path, status in [
        ("/test-error", 500),
        ("/test-input?value=secret-password", 422),
        ("/test-auth", 401),
        ("/missing?secret-password", 404),
    ]:
        response = client.get(path)
        assert response.status_code == status
        assert response.headers["content-type"] == "application/problem+json"
        assert "secret-password" not in response.text
        assert response.json()["request_id"] == response.headers["x-request-id"]
    assert client.get("/test-auth").headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": RUNTIME_URL.replace("ocoteAppDatabase", "ocoteappdatabase")},
        {"database_url": RUNTIME_URL.replace("ocote_runtime", "postgres")},
        {"database_url": RUNTIME_URL.replace("ocote_runtime", "ocote_migrador")},
        {"database_url": RUNTIME_URL.replace("+psycopg", "")},
        {"database_url": RUNTIME_URL.replace("127.0.0.1", "remote.example")},
        {"health_token": "short"},
        {"organization_timezone": "not/a-zone"},
        {"db_pool_size": 0},
        {"deployment_mode": "managed"},
        {"app_env": "production"},
    ],
)
def test_invalid_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError) as error:
        settings(**overrides)
    assert "synthetic@" not in str(error.value)


def test_migration_configuration_needs_its_own_dsn():
    config = MigrationSettings(
        _env_file=None,
        migration_database_url=RUNTIME_URL.replace("runtime", "migrador"),
    )
    assert "synthetic" not in repr(config)
    with pytest.raises(ValidationError):
        MigrationSettings(_env_file=None, migration_database_url=RUNTIME_URL)


def test_unit_of_work_uses_one_transaction_and_propagates_failures():
    session = MagicMock()
    with unit_of_work(session) as current:
        assert current is session
    session.begin.assert_called_once()
    with pytest.raises(RuntimeError), unit_of_work(session):
        raise RuntimeError("rollback")
    assert session.begin.return_value.__exit__.call_args.args[0] is RuntimeError
