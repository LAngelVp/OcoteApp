import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import MigrationSettings, Settings
from app.main import create_app
from tools.f1_local import role_connection

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OCOTE_RUN_PG_TESTS") != "1",
        reason="Explicit OCOTE_RUN_PG_TESTS=1 required; local technical schema only",
    ),
]


@pytest.fixture
def runtime():
    with role_connection(Settings().database_url.get_secret_value()) as connection:
        yield connection


@pytest.fixture
def migrator():
    with role_connection(
        MigrationSettings().migration_database_url.get_secret_value()
    ) as connection:
        yield connection


def test_real_roles_and_scoped_privileges(runtime, migrator):
    for connection, name, create in [
        (runtime, "ocote_runtime", False),
        (migrator, "ocote_migrador", True),
    ]:
        identity = connection.execute(
            "SELECT current_database(), current_user, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity == ("ocoteAppDatabase", name, False, False, False, False, False)
        assert (
            connection.execute(
                "SELECT has_schema_privilege(current_user,'public','CREATE')"
            ).fetchone()[0]
            is create
        )
        assert (
            connection.execute(
                "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
            ).fetchone()[0]
            is False
        )
    assert runtime.execute("SELECT version_num FROM public.alembic_version").fetchall() == [
        ("20261125_0006",)
    ]
    assert runtime.execute("SELECT count(*) FROM public.release_history").fetchone()[0] >= 1
    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert (
            runtime.execute(
                "SELECT has_table_privilege(current_user,'public.release_history',%s)",
                (privilege,),
            ).fetchone()[0]
            is False
        )
    assert (
        runtime.execute(
            "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
        ).fetchone()[0]
        is False
    )
    for table in (
        "annual_plans",
        "objectives",
        "tasks",
        "subtasks",
        "task_history",
        "due_date_requests",
    ):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
            expected = privilege in {"SELECT", "INSERT"} or (
                privilege == "UPDATE" and table != "task_history"
            )
            assert (
                runtime.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", ("public." + table, privilege)
                ).fetchone()[0]
                is expected
            )


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.f1_forbidden (id integer)",
        "UPDATE public.release_history SET version=version+1 WHERE false",
        "DELETE FROM public.release_history WHERE false",
        "SET ROLE ocote_migrador",
    ],
)
def test_runtime_cannot_mutate_schema_ledger_or_assume_migrator(runtime, statement):
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        runtime.transaction(force_rollback=True),
    ):
        runtime.execute(statement)


def test_release_history_identity_versions_and_terminals_are_protected(migrator):
    attempt, request_id = uuid4(), uuid4()
    with migrator.transaction(force_rollback=True):
        migrator.execute(
            "INSERT INTO public.release_history (id,created_at,updated_at,application_version,"
            "artifact_sha256,manifest_sha256,target_revision,operator_ref,deployment_mode,phase,"
            "request_id) VALUES (%s,%s,%s,'synthetic-test',%s,%s,'20261124_0001',"
            "'rollback-only-fixture','local','validation',%s)",
            (attempt, datetime.now(UTC), datetime.now(UTC), "a" * 64, "b" * 64, request_id),
        )
        for statement in [
            "UPDATE public.release_history SET operator_ref='changed',"
            "version=version+1 WHERE id=%s",
            "UPDATE public.release_history SET phase='backup' WHERE id=%s",
            "DELETE FROM public.release_history WHERE id=%s",
        ]:
            with pytest.raises(psycopg.errors.CheckViolation), migrator.transaction():
                migrator.execute(statement, (attempt,))
        migrator.execute(
            "UPDATE public.release_history SET status='failed',finished_at=%s,updated_at=%s,"
            "result_code='ROLLBACK_TEST',version=version+1 WHERE id=%s",
            (datetime.now(UTC), datetime.now(UTC), attempt),
        )
        with pytest.raises(psycopg.errors.CheckViolation), migrator.transaction():
            migrator.execute(
                "UPDATE public.release_history SET version=version+1 WHERE id=%s",
                (attempt,),
            )
    assert (
        migrator.execute(
            "SELECT count(*) FROM public.release_history WHERE id=%s",
            (attempt,),
        ).fetchone()[0]
        == 0
    )


def test_real_health_with_runtime_connection():
    settings = Settings()
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 403
        response = client.get(
            "/api/v1/health/ready",
            headers={"X-Health-Token": settings.health_token.get_secret_value()},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
        assert "ocote_runtime" not in response.text
