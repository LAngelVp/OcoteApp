import os
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_identity import api as api
from test_identity import tokens as tokens
from test_operations import command
from test_operations import core as core

from app.core.errors import CommandError
from app.schemas.analytics import AnalyticsFilters, EvaluationFinalize
from app.services.analytics import collect, monthly_series, summarize


def sample(**changes):
    return {
        "completed_at": None,
        "punctuality_status": "pending",
        "baseline_punctuality_status": "pending",
        "stage": {"kind": "open"},
        "pending_closure": False,
        "subtasks_total": 0,
        "subtasks_completed": 0,
        "delay_days": 0,
        "baseline_delay_days": 0,
        "due_date_delta_days": 0,
        "due_date_change_count": 0,
        "original_due_date": "2027-12-15",
        **changes,
    }


def test_ratified_denominator_and_both_punctualities():
    result = summarize(
        [
            sample(
                completed_at="2027-12-14T12:00:00Z",
                punctuality_status="on_time",
                baseline_punctuality_status="on_time",
            ),
            sample(
                completed_at="2027-12-18T12:00:00Z",
                punctuality_status="on_time",
                baseline_punctuality_status="late",
                due_date_delta_days=5,
                baseline_delay_days=3,
                due_date_change_count=1,
            ),
            sample(),
            sample(
                stage={"kind": "blocked"},
                punctuality_status="overdue",
                baseline_punctuality_status="overdue",
                delay_days=2,
                baseline_delay_days=2,
            ),
        ]
    )
    assert result["task_count"] == 4
    assert result["completion_rate"] == 50
    assert result["baseline_on_time_rate"] == 25
    assert result["on_time_rate"] == 50
    assert result["progress_percent"] == 50
    assert result["blocked_count"] == 1
    assert result["rescheduled_count"] == result["due_date_change_count"] == 1
    assert result["average_baseline_delay_days"] == 1.25


def test_empty_cohort_is_not_perfect_or_zero():
    result = summarize([])
    assert result["task_count"] == result["completed_count"] == 0
    for field in (
        "progress_percent",
        "completion_rate",
        "on_time_rate",
        "baseline_on_time_rate",
        "average_delay_days",
    ):
        assert result[field] is None


def test_progress_uses_subtasks_not_stage_position_or_closure_rate():
    result = summarize(
        [
            sample(subtasks_total=3, subtasks_completed=1),
            sample(subtasks_total=4, subtasks_completed=4, pending_closure=True),
        ]
    )
    assert abs(result["progress_percent"] - 200 / 3) < 1e-12
    assert result["completion_rate"] == 0
    assert result["pending_closure_count"] == 1


def test_months_preserve_years_and_empty_denominators():
    rows = monthly_series(
        [sample(), sample(original_due_date="2028-02-29")], date(2027, 12, 15), date(2028, 2, 29)
    )
    assert [row["month"] for row in rows] == ["2027-12", "2028-01", "2028-02"]
    assert rows[1]["task_count"] == 0
    assert rows[1]["on_time_rate"] is None
    assert monthly_series([]) == []


def test_reprogramming_back_to_original_is_still_counted():
    result = summarize([sample(due_date_change_count=2)])
    assert result["rescheduled_count"] == 1
    assert result["due_date_change_count"] == 2
    assert result["average_due_date_delta_days"] == 0


def test_filters_are_strict_and_do_not_invent_a_calendar():
    assert AnalyticsFilters().period_start is None
    for values in (
        {"period_start": "2027-01-01"},
        {"period_start": "2028-02-29", "period_end": "2028-02-28"},
        {"period_start": "2028-02-29T00:00:00Z", "period_end": "2028-03-01"},
        {"status": "unknown"},
    ):
        with pytest.raises(ValidationError):
            AnalyticsFilters(**values)
    with pytest.raises(ValidationError):
        EvaluationFinalize(expected_version=1, summary="short")


def test_series_limits_do_not_truncate_and_keep_four_digit_years():
    assert [row["month"] for row in monthly_series([], date(1, 1, 1), date(1, 2, 28))] == [
        "0001-01",
        "0001-02",
    ]
    with pytest.raises(CommandError) as failure:
        monthly_series([], date(1, 1, 1), date(9999, 12, 31))
    assert failure.value.status == 413


def test_csv_evaluation_includes_frozen_conclusion_and_metrics():
    import csv
    import io
    import json

    from app.services.exports import encode_csv

    content = encode_csv(
        [{"id": "task"}],
        {
            "evaluation_id": "evaluation",
            "summary": "=Synthetic conclusion",
            "metrics": {"task_count": 1, "baseline_on_time_rate": 0},
        },
    )
    row = next(csv.DictReader(io.StringIO(content.decode())))
    assert row["evaluation_id"] == "evaluation"
    assert row["summary"] == "'=Synthetic conclusion"
    assert json.loads(row["metrics"])["task_count"] == 1


def test_collaborator_denied_before_any_database_access():
    with pytest.raises(CommandError) as failure:
        collect(None, SimpleNamespace(role="colaborador"), AnalyticsFilters())
    assert failure.value.status == 403


@pytest.mark.skipif(
    os.environ.get("OCOTE_RUN_PG_TESTS") != "1", reason="Authorized isolated PostgreSQL required"
)
def test_f6_migration_empty_and_noop_preserves_source():
    from app.core.config import MigrationSettings
    from tools import f1_local, f2_local

    with f2_local.isolated_database() as name:
        f2_local.upgrade(name, "20261124_0004")
        url = MigrationSettings().migration_database_url.get_secret_value()
        with f1_local.role_connection(url, name) as db:
            before = f2_local.snapshot(db)
            f2_local.upgrade(name)
            after = f2_local.snapshot(db)
            assert set(after["tables"]) - set(before["tables"]) == {
                "evaluations",
                "evaluation_items",
            }
            assert after["rows"]["evaluations"] == after["rows"]["evaluation_items"] == []
            for table, rows in before["rows"].items():
                if table != "alembic_version":
                    assert after["rows"][table] == rows
            f2_local.upgrade(name)
            assert f2_local.snapshot(db) == after


def test_real_analytics_cohort_and_evaluation_lifecycle(core):
    client, factory, task, plan, _, person, terminal = core
    response = client.get("/api/v1/analytics/summary", params={"annual_plan_id": plan["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["task_count"] == 1
    assert response.json()["organization_timezone"] == "America/Mexico_City"
    assert response.json()["metrics"]["completion_rate"] == 0
    body = {
        "annual_plan_id": plan["id"],
        "department_id": person["department_id"],
        "period_start": "2027-12-01",
        "period_end": "2028-02-29",
    }
    draft = command(client, "evaluations", body, 201)
    assert draft["metrics"]["task_count"] == 1
    assert draft["items"][0]["id"] == task["id"]
    command(client, "evaluations", body, 409)
    stale = client.post(
        "/api/v1/evaluations/" + draft["id"] + "/recalculate", json={"expected_version": 9}
    )
    assert stale.status_code == 409
    assert stale.headers["content-type"] == "application/problem+json"
    assert stale.json()["request_id"] == stale.headers["x-request-id"]
    command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": 1},
    )
    assert (
        client.get("/api/v1/evaluations/" + draft["id"]).json()["metrics"]["completion_rate"] == 0
    )
    recalculated = command(
        client, "evaluations/" + draft["id"] + "/recalculate", {"expected_version": 1}
    )
    assert recalculated["metrics"]["completion_rate"] == 100
    assert recalculated["version"] == 2
    command(
        client,
        "evaluations/" + draft["id"] + "/finalize",
        {"expected_version": 2, "summary": "Synthetic valid conclusion"},
        409,
    )
    with factory() as db:
        from sqlalchemy import text

        assert db.scalar(text("SELECT count(*) FROM evaluation_items")) == 1


def test_real_series_filters_and_denied_modules(core):
    from test_identity import person_client

    client, _, _, plan, _, _, _ = core
    response = client.get(
        "/api/v1/analytics/series",
        params={
            "annual_plan_id": plan["id"],
            "period_start": "2027-12-01",
            "period_end": "2028-02-29",
            "limit": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["month"] == "2027-12"
    assert response.json()["next_cursor"] == "2027-12"
    with person_client(client) as collaborator:
        for path in (
            "/analytics/summary",
            "/analytics/series",
            "/evaluations",
            "/evaluations/" + plan["id"],
        ):
            assert collaborator.get("/api/v1" + path).status_code == 403


@pytest.mark.parametrize(
    "value", ["=SUM(1,2)", " +cmd", "-formula", "@formula", "\ttext", " \rtext", "\x00 =formula"]
)
def test_csv_neutralizes_formulas_with_standard_quoting(value):
    import csv
    import io

    from app.services.exports import encode_csv

    data = encode_csv([{"title": value, "id": "synthetic", "description": "not exported"}], {})
    row = next(csv.DictReader(io.StringIO(data.decode())))
    assert row["title"] == "'" + value
    assert "description" not in row


def test_real_exports_are_bounded_and_audited(core):
    from sqlalchemy import select
    from test_identity import person_client

    from app.models.identity import AuditEvent

    client, factory, _, plan, _, _, _ = core
    response = client.post(
        "/api/v1/exports/tasks", json={"format": "json", "annual_plan_id": plan["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["row_count"] == 1
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    empty = client.post(
        "/api/v1/exports/tasks",
        json={"format": "csv", "period_start": "2020-01-01", "period_end": "2020-01-01"},
    )
    assert empty.status_code == 200 and len(empty.text.splitlines()) == 1
    with person_client(client) as collaborator:
        assert (
            collaborator.post("/api/v1/exports/tasks", json={"format": "json"}).status_code == 403
        )
    with factory() as db:
        events = list(db.scalars(select(AuditEvent.event_type)))
        assert events.count("export_requested") == events.count("export_prepared") == 2
        assert events.count("export_denied") == 1


@pytest.fixture
def historical(core):
    client, factory, _, _, _, person, terminal = core
    plan = command(
        client,
        "annual-plans",
        {
            "title": "Synthetic historical plan",
            "horizon_type": "custom",
            "start_date": "2024-01-01",
            "due_date": "2027-12-31",
        },
        201,
    )
    objective = command(
        client,
        "objectives",
        {
            "annual_plan_id": plan["id"],
            "department_id": person["department_id"],
            "title": "Synthetic historical objective",
            "horizon_type": "custom",
            "start_date": "2024-01-01",
            "due_date": "2027-12-31",
        },
        201,
    )
    command(
        client,
        "annual-plans/" + plan["id"] + "/status-changes",
        {"status": "active", "expected_version": 1},
    )
    tasks = [
        command(
            client,
            "tasks",
            {
                "objective_id": objective["id"],
                "assignee_id": person["id"],
                "title": "=SUM(1,2)" if index == 0 else "Synthetic historical " + str(index),
                "start_date": "2025-03-01",
                "due_date": "2025-03-10",
            },
            201,
        )
        for index in range(4)
    ]
    command(
        client,
        "tasks/" + tasks[0]["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": 1},
    )
    changed = command(
        client,
        "tasks/" + tasks[1]["id"] + "/due-date-changes",
        {"due_date": "2027-01-01", "expected_version": 1, "reason": "Synthetic changed deadline"},
    )
    command(
        client,
        "tasks/" + changed["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": changed["version"]},
    )
    body = {
        "annual_plan_id": plan["id"],
        "department_id": person["department_id"],
        "period_start": "2025-03-01",
        "period_end": "2025-03-31",
    }
    yield client, factory, plan, person, tasks, body


def test_real_final_snapshot_and_exports_are_immutable(historical):
    import csv
    import io

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    client, factory, _, _, tasks, body = historical
    draft = command(client, "evaluations", body, 201)
    final = command(
        client,
        "evaluations/" + draft["id"] + "/finalize",
        {"expected_version": 1, "summary": "Synthetic departmental conclusion"},
    )
    assert final["status"] == "final"
    assert final["metrics"]["task_count"] == 4
    assert final["metrics"]["completion_rate"] == 50
    assert final["metrics"]["baseline_on_time_rate"] == 0
    assert final["metrics"]["on_time_rate"] == 25
    assert final["metrics"]["rescheduled_count"] == 1
    command(
        client,
        "tasks/" + tasks[2]["id"] + "/due-date-changes",
        {
            "due_date": "2027-02-01",
            "expected_version": 1,
            "reason": "Synthetic change after snapshot",
        },
    )
    priority = final["items"][0]["priority"]
    response = client.patch(
        "/api/v1/priorities/" + priority["id"],
        json={
            "name": "Synthetic renamed",
            "position": 0,
            "is_active": True,
            "expected_version": 1,
            "reason": "Synthetic label after snapshot",
        },
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/evaluations/" + final["id"]).json() == final
    command(client, "evaluations/" + final["id"] + "/recalculate", {"expected_version": 2}, 409)
    exported = client.post("/api/v1/exports/evaluations/" + final["id"], json={"format": "json"})
    assert exported.status_code == 200, exported.text
    assert exported.json()["items"] == final["items"]
    csv_response = client.post("/api/v1/exports/evaluations/" + final["id"], json={"format": "csv"})
    assert any(
        row["title"].startswith("'=SUM") for row in csv.DictReader(io.StringIO(csv_response.text))
    )
    with factory.begin() as db:
        for statement in (
            "UPDATE evaluations SET summary='Synthetic forbidden',version=version+1 "
            "WHERE id=:identity",
            "DELETE FROM evaluations WHERE id=:identity",
            "DELETE FROM evaluation_items WHERE evaluation_id=:identity",
            "UPDATE evaluation_items SET snapshot_data='{}'::jsonb WHERE evaluation_id=:identity",
            "TRUNCATE evaluations CASCADE",
        ):
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(text(statement), {"identity": final["id"]})


def test_real_leader_sees_only_own_finals(historical):
    from test_identity import create_department, create_person, person_client

    client, _, plan, person, _, body = historical
    draft = command(client, "evaluations", body, 201)
    leader = create_person(
        client, role="lider", department=person["department_id"], email="leader@example.invalid"
    )
    other_department = create_department(client, "other_evaluation")
    other = create_person(
        client, role="lider", department=other_department, email="otherleader@example.invalid"
    )
    with person_client(client, leader["email"]) as own:
        assert own.get("/api/v1/evaluations").json()["items"] == []
        assert own.get("/api/v1/evaluations/" + draft["id"]).status_code == 404
        assert own.post("/api/v1/evaluations", json=body).status_code == 403
        assert (
            own.get(
                "/api/v1/analytics/summary", params={"department_id": other_department}
            ).status_code
            == 404
        )
    final = command(
        client,
        "evaluations/" + draft["id"] + "/finalize",
        {"expected_version": 1, "summary": "Synthetic final report for leaders"},
    )
    with person_client(client, leader["email"]) as own:
        assert own.get("/api/v1/evaluations/" + final["id"]).status_code == 200
        assert (
            own.get("/api/v1/analytics/summary", params={"annual_plan_id": plan["id"]}).json()[
                "scope"
            ]["department_id"]
            == person["department_id"]
        )
        assert (
            own.post(
                "/api/v1/exports/evaluations/" + final["id"], json={"format": "json"}
            ).status_code
            == 200
        )
    with person_client(client, other["email"]) as foreign:
        assert foreign.get("/api/v1/evaluations/" + final["id"]).status_code == 404
        assert foreign.get("/api/v1/evaluations").json()["items"] == []
        assert (
            foreign.post(
                "/api/v1/exports/evaluations/" + final["id"], json={"format": "json"}
            ).status_code
            == 404
        )


def test_real_export_limit_empty_evaluation_and_plan_contraction(historical):
    from sqlalchemy import select

    from app.models.identity import AuditEvent

    client, factory, plan, _, _, body = historical
    empty = command(
        client,
        "evaluations",
        {**body, "period_start": "2024-01-01", "period_end": "2024-12-31"},
        201,
    )
    command(
        client,
        "evaluations/" + empty["id"] + "/finalize",
        {"expected_version": 1, "summary": "Synthetic empty cannot finalize"},
        409,
    )
    command(
        client,
        "annual-plans/" + plan["id"] + "/period-changes",
        {
            "horizon_type": "custom",
            "start_date": "2025-01-01",
            "due_date": "2027-12-31",
            "expected_version": 2,
            "reason": "Synthetic excluded snapshot",
        },
        409,
    )
    setting = client.get("/api/v1/settings/export_max_rows").json()
    assert (
        client.patch(
            "/api/v1/settings/export_max_rows",
            json={
                "value": 3,
                "expected_version": setting["version"],
                "reason": "Synthetic export bound",
            },
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/exports/tasks", json={"format": "json", "annual_plan_id": plan["id"]}
    )
    assert response.status_code == 413, response.text
    assert response.json()["code"] == "EXPORT_TOO_LARGE"
    assert response.headers["content-type"] == "application/problem+json"
    with factory() as db:
        assert "export_failed" in list(db.scalars(select(AuditEvent.event_type)))


def test_transport_interruption_records_failure_without_changing_content():
    import anyio

    from app.services.exports import ExportResponse

    recorded = []
    response = ExportResponse(
        b"synthetic",
        media_type="text/csv",
        filename="ocote-tasks.csv",
        failure=lambda: recorded.append("transport_failed"),
    )

    async def execute():
        async def send(message):
            raise OSError("Synthetic disconnected receiver")

        with pytest.raises(OSError):
            await response({"type": "http"}, None, send)

    anyio.run(execute)
    assert recorded == ["transport_failed"]
    assert response.body == b"synthetic"


@pytest.mark.parametrize("race", ["create", "recalculate", "finalize"])
def test_real_evaluation_races_preserve_one_version_and_cohort(historical, race):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi.testclient import TestClient

    client, _, _, _, _, body = historical
    draft = command(client, "evaluations", body, 201) if race != "create" else None
    barrier = Barrier(2)

    def execute(index):
        with TestClient(
            client.app, base_url=str(client.base_url), raise_server_exceptions=False
        ) as peer:
            peer.headers.update(dict(client.headers))
            barrier.wait(timeout=10)
            if race == "create":
                return peer.post("/api/v1/evaluations", json=body)
            action = "finalize" if race == "finalize" and index == 0 else "recalculate"
            payload = {"expected_version": 1}
            if action == "finalize":
                payload["summary"] = "Synthetic racing final conclusion"
            return peer.post("/api/v1/evaluations/" + draft["id"] + "/" + action, json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(execute, [0, 1]))
    assert sorted(response.status_code for response in responses) == [
        201 if race == "create" else 200,
        409,
    ], [response.text for response in responses]
    records = client.get("/api/v1/evaluations").json()["items"]
    assert len(records) == 1
    record = client.get("/api/v1/evaluations/" + records[0]["id"]).json()
    assert record["version"] == (1 if race == "create" else 2)
    assert record["metrics"]["task_count"] == len(record["items"]) == 4
    assert len({item["id"] for item in record["items"]}) == 4


def test_real_report_snapshot_survives_committed_task_write(core, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.services import analytics

    client, _, task, plan, _, _, _ = core
    original = analytics.collect

    def write():
        with TestClient(
            client.app, base_url=str(client.base_url), raise_server_exceptions=False
        ) as peer:
            peer.headers.update(dict(client.headers))
            return peer.post(
                "/api/v1/tasks/" + task["id"] + "/due-date-changes",
                json={
                    "due_date": "2028-02-20",
                    "expected_version": 1,
                    "reason": "Synthetic write during report snapshot",
                },
            )

    def capture(db, user, filters, **keywords):
        first = original(db, user, filters, **keywords)
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(write).result(timeout=15)
        assert response.status_code == 200, response.text
        second = original(db, user, filters, **keywords)
        assert first == second
        return first

    monkeypatch.setattr(analytics, "collect", capture)
    response = client.get("/api/v1/analytics/summary", params={"annual_plan_id": plan["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["due_date_change_count"] == 0
    assert client.get("/api/v1/tasks/" + task["id"]).json()["due_date"] == "2028-02-20"


def test_real_export_audit_failure_blocks_content(core, monkeypatch):
    from sqlalchemy import select

    from app.core.errors import ServiceUnavailable
    from app.models.identity import AuditEvent
    from app.services import exports

    client, factory, _, plan, _, _, _ = core
    original = exports.log_export

    def record(request, user, event, context, **keywords):
        if event == "export_prepared":
            raise ServiceUnavailable()
        return original(request, user, event, context, **keywords)

    monkeypatch.setattr(exports, "log_export", record)
    response = client.post(
        "/api/v1/exports/tasks", json={"format": "csv", "annual_plan_id": plan["id"]}
    )
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert "content-disposition" not in response.headers
    with factory() as db:
        events = list(db.scalars(select(AuditEvent.event_type)))
        assert "export_requested" in events
        assert "export_prepared" not in events


def test_real_export_rate_denial_is_audited(core, monkeypatch):
    from sqlalchemy import select

    from app.models.identity import AuditEvent

    client, factory, _, _, _, _, _ = core

    def deny(*arguments):
        raise CommandError(429, "RATE_LIMITED")

    monkeypatch.setattr(client.app.state.export_limiter, "check", deny)
    response = client.post("/api/v1/exports/tasks", json={"format": "json"})
    assert response.status_code == 429
    with factory() as db:
        assert "export_denied" in list(db.scalars(select(AuditEvent.event_type)))
