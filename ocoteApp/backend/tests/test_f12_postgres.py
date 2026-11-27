import base64
import csv
import io
import os
import re
import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from test_f8 import policy_values
from test_f11_postgres import f11_api as f11_api
from test_identity import api as api
from test_identity import tokens as tokens
from test_operations import core as core

pytestmark = pytest.mark.skipif(os.environ.get("OCOTE_RUN_PG_TESTS") != "1",
                                reason="Explicit F12 isolated PostgreSQL authorization required")


def command(**values):
    return {"current_password": "Synthetic-password-123!", "expected_version": 0,
            "reason": "Explicit synthetic UUID-only F12 operation", **values}


def configure_f12(client):
    response = client.get("/api/v1/admin/configuration")
    assert response.status_code == 200, response.text
    current = response.json()
    policy_version = (current["security_policy"] or {}).get("version", 0)
    versions = {row["code"]: row["version"] for row in current["modules"]}
    response = client.put("/api/v1/admin/security-policy", json=command(
        values=policy_values(), expected_version=policy_version,
    ))
    assert response.status_code == 200, response.text
    for code in ("imports", "executive_reports", "advanced_operations", "evaluations", "exports"):
        response = client.put("/api/v1/admin/feature-flags", json=command(
            code=code, enabled=True, expected_version=versions[code],
        ))
        assert response.status_code == 200, response.text


@pytest.fixture
def f12_api(f11_api):
    client, factory, *_rest = f11_api
    diagnostics = []

    def capture(context):
        diagnostics.append(safe_database_error(context))

    event.listen(factory.kw["bind"], "handle_error", capture)
    client.app.state.f12_database_diagnostics = diagnostics
    client.app.state.import_scanner = lambda _content: "ClamAV synthetic test transport"
    try:
        configure_f12(client)
        yield f11_api
    finally:
        event.remove(factory.kw["bind"], "handle_error", capture)


def safe_database_error(context):
    original = context.original_exception
    diagnostic = getattr(original, "diag", None)
    result = {}
    for output, value, pattern in (
        ("sqlstate", getattr(original, "sqlstate", None), r"[0-9A-Z]{5}"),
        *((name, getattr(diagnostic, name, None), r"[a-z][a-z0-9_]*") for name in (
            "constraint_name", "table_name", "column_name",
        )),
        ("guard", getattr(diagnostic, "message_primary", None), r"F[0-9]+_[A-Z0-9_]+"),
    ):
        result[output] = value if isinstance(value, str) and re.fullmatch(pattern, value) else None
    return result


def api_failure(client, response):
    return response.text, client.app.state.f12_database_diagnostics


def test_real_f12_additive_migration_noop_preservation_and_privileges():
    from tools import f12_release
    from tools.f2_local import isolated_database, migration_engine, upgrade

    revision = runpy.run_path(str(Path(__file__).parents[1] /
                                 "alembic/versions/20261126_0011_bulk_operations.py"))
    with isolated_database() as name:
        upgrade(name, f12_release.SOURCE)
        engine = migration_engine(name)
        try:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO deployment_instances(id,root_key_ref) "
                                        "VALUES(:id,'synthetic-f12-preserved-root')"),
                                   {"id": uuid4()})
                tables = set(connection.scalars(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'",
                )))
                assert len(tables) == 67
                before = {table: connection.execute(text(
                    f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY to_jsonb(t)::text",
                )).all() for table in tables - {"alembic_version"}}
            upgrade(name, f12_release.HEAD)
            upgrade(name, f12_release.HEAD)
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    f12_release.HEAD
                )
                after = set(connection.scalars(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'",
                )))
                assert len(after) == 72 and after - tables == set(revision["TABLES"])
                for table in revision["TABLES"]:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                for table, rows in before.items():
                    projection = ("to_jsonb(t)-'operation_payload'" if table == "job_runs"
                                  else "to_jsonb(t)")
                    assert connection.execute(text(
                        f"SELECT ({projection})::text FROM {table} t ORDER BY ({projection})::text",
                    )).all() == rows
            f12_release.verify_runtime(name)
        finally:
            engine.dispose()


def csv_upload(client, objective, person, *, title="Synthetic imported task", key=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["title", "objective", "assignee", "start", "end"])
    writer.writerow([title, objective["id"], person["id"], "2027-12-10", "2028-02-20"])
    response = client.post("/api/v1/imports", json={
        "entity_type": "task", "file_format": "csv",
        "content": base64.b64encode(output.getvalue().encode()).decode(),
        "idempotency_key": str(key or uuid4()), "reason": "Synthetic F12 import source",
    })
    return response


def dry_run(client, record):
    response = client.post("/api/v1/imports/" + record["id"] + "/dry-run", json={
        "expected_version": record["version"], "mapping": {
            "title": "title", "objective": "objective_id", "assignee": "assignee_id",
            "start": "start_date", "end": "due_date",
        }, "reason": "Synthetic explicit F12 dry-run",
    })
    assert response.status_code == 200, api_failure(client, response)
    return response.json()


def test_real_f12_dry_run_never_creates_domain_and_commit_is_idempotent(f12_api):
    client, factory, _task, _plan, objective, person, *_rest = f12_api
    with factory() as database:
        before = database.scalar(text("SELECT count(*) FROM tasks"))
    response = csv_upload(client, objective, person)
    assert response.status_code == 201, api_failure(client, response)
    uploaded = response.json()
    preview = dry_run(client, uploaded)
    assert preview["error_count"] == 0 and preview["state"] == "previewed"
    with factory() as database:
        assert database.scalar(text("SELECT count(*) FROM tasks")) == before
        assert database.scalar(text("SELECT count(*) FROM import_rows")) == 1
    body = {"expected_version": preview["version"], "preview_hash": preview["preview_hash"],
            "idempotency_key": str(uuid4()), "reason": "Synthetic atomic F12 commit"}
    path = "/api/v1/imports/" + uploaded["id"] + "/commit"
    response = client.post(path, json=body)
    assert response.status_code == 200, api_failure(client, response)
    assert response.json()["state"] == "committed"
    result = response.json()["result_ids"]
    assert client.post(path, json=body).json()["result_ids"] == result
    with factory() as database:
        assert database.scalar(text("SELECT count(*) FROM tasks")) == before + 1
        assert database.scalar(text("SELECT count(*) FROM job_runs WHERE kind='import' "
                                    "AND state='succeeded'")) == 1


def test_real_f12_revalidation_prevents_partial_or_stale_commit(f12_api):
    client, factory, _task, _plan, objective, person, *_rest = f12_api
    response = csv_upload(client, objective, person)
    assert response.status_code == 201, api_failure(client, response)
    preview = dry_run(client, response.json())
    updated = client.patch("/api/v1/objectives/" + objective["id"], json={
        "expected_version": objective["version"], "title": "Synthetic concurrent objective",
        "description": "Explicit concurrency test",
    })
    assert updated.status_code == 200, updated.text
    with factory() as database:
        before = database.scalar(text("SELECT count(*) FROM tasks"))
    response = client.post("/api/v1/imports/" + preview["id"] + "/commit", json={
        "expected_version": preview["version"], "preview_hash": preview["preview_hash"],
        "idempotency_key": str(uuid4()), "reason": "Synthetic stale F12 commit",
    })
    assert response.status_code == 409, response.text
    with factory() as database:
        assert database.scalar(text("SELECT count(*) FROM tasks")) == before


def test_real_f12_audit_vocabulary_and_append_guards(f12_api):
    from types import SimpleNamespace

    from app.services.identity import audit

    _client, factory, *_rest = f12_api
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    revision = runpy.run_path(str(Path(__file__).parents[1] /
                                 "alembic/versions/20261126_0011_bulk_operations.py"))
    with factory.begin() as database:
        for event in revision["AUDIT_EVENTS"]:
            audit(database, request, event, entity="f12_synthetic_check", entity_id=uuid4())
    with pytest.raises(DBAPIError), factory.begin() as database:
        audit(database, request, "unknown_f12_event", entity="f12_synthetic_check")
    for statement in ("TRUNCATE import_rows CASCADE", "TRUNCATE export_jobs CASCADE",
                      "TRUNCATE backup_records CASCADE"):
        with pytest.raises(DBAPIError), factory.begin() as database:
            database.execute(text(statement))