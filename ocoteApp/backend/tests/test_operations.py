from datetime import UTC, date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from test_identity import api as api
from test_identity import authenticated, create_department, create_person, workflow_body
from test_identity import tokens as tokens

from app.schemas.operations import Period, PlanCreate, TaskUpdate
from app.services.operations import task_progress, timeliness


def command(client, path, body, expected=200):
    response = client.post("/api/v1/" + path, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def current_task(client, identity):
    response = client.get("/api/v1/tasks/" + identity)
    assert response.status_code == 200, response.text
    return response.json()


def add_child(client, task):
    return command(
        client,
        "tasks/" + task["id"] + "/subtasks",
        {
            "title": "Synthetic subtask",
            "start_date": "2027-12-11",
            "due_date": "2028-02-15",
            "expected_version": task["version"],
        },
        201,
    )


def test_real_flexible_periods_and_contractions(core):
    client, _, task, plan, objective, person, _ = core
    duplicate = command(
        client,
        "annual-plans",
        {
            "title": "Synthetic overlapping",
            "horizon_type": "annual",
            "start_date": plan["start_date"],
            "due_date": plan["due_date"],
        },
        201,
    )
    command(
        client,
        "annual-plans/" + duplicate["id"] + "/status-changes",
        {"status": "active", "expected_version": 1, "reason": "Synthetic activation"},
        409,
    )
    command(
        client,
        "objectives",
        {
            "annual_plan_id": plan["id"],
            "department_id": person["department_id"],
            "title": "Synthetic invalid",
            "horizon_type": "custom",
            "start_date": "2027-01-01",
            "due_date": "2027-12-01",
        },
        422,
    )
    command(
        client,
        "annual-plans/" + plan["id"] + "/period-changes",
        {
            "horizon_type": "custom",
            "start_date": "2028-01-01",
            "due_date": "2028-02-29",
            "reason": "Synthetic contraction",
            "expected_version": 2,
        },
        409,
    )
    command(
        client,
        "objectives/" + objective["id"] + "/period-changes",
        {
            "horizon_type": "monthly",
            "start_date": "2027-12-01",
            "due_date": "2028-02-10",
            "reason": "Synthetic contraction",
            "expected_version": 1,
        },
        409,
    )
    updated = command(
        client,
        "tasks/" + task["id"] + "/due-date-changes",
        {"due_date": "2028-02-25", "expected_version": 1, "reason": "Synthetic postponement"},
    )
    assert updated["original_due_date"] == "2028-02-20"
    assert updated["due_date_delta_days"] == 5
    command(
        client,
        "tasks/" + task["id"] + "/due-date-changes",
        {"due_date": "2028-02-24", "expected_version": 1, "reason": "Synthetic stale version"},
        409,
    )


def test_real_four_subtasks_pending_closure_and_versions(core):
    client, _, task, plan, _, _, terminal = core
    children = []
    for _unused in range(4):
        created = add_child(client, task)
        children.append(created["subtask"])
        task = created["task"]
    command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": task["version"]},
        409,
    )
    for index, child in enumerate(children):
        result = command(
            client,
            "subtasks/" + child["id"] + "/completion",
            {"expected_version": child["version"], "expected_task_version": task["version"]},
        )
        task = result["task"]
        assert task["progress_percent"] == 25 * (index + 1)
        assert task["pending_closure"] == (index == 3)
    command(
        client,
        "subtasks/" + children[0]["id"] + "/completion",
        {"expected_version": 2, "expected_task_version": task["version"]},
        409,
    )
    task = command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": task["version"]},
    )
    assert not task["pending_closure"]
    add_body = {
        "title": "Synthetic forbidden",
        "start_date": "2027-12-11",
        "due_date": "2028-02-15",
        "expected_version": task["version"],
    }
    command(client, "tasks/" + task["id"] + "/subtasks", add_body, 409)
    closed = command(
        client,
        "annual-plans/" + plan["id"] + "/status-changes",
        {"status": "closed", "expected_version": 2, "reason": "Synthetic explicit closure"},
    )
    assert closed["status"] == "closed"
    events = client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]
    assert len(events) == 10
    assert len({event["subtask_id"] for event in events if event["subtask_id"]}) == 4


def test_real_dates_reject_orphaned_children_and_keep_original(core):
    client, _, task, _, objective, _, _ = core
    result = add_child(client, task)
    task, child = result["task"], result["subtask"]
    command(
        client,
        "tasks/" + task["id"] + "/due-date-changes",
        {
            "due_date": "2028-02-10",
            "expected_version": task["version"],
            "reason": "Synthetic contraction",
        },
        409,
    )
    result = command(
        client,
        "subtasks/" + child["id"] + "/due-date-changes",
        {
            "due_date": "2028-02-05",
            "expected_version": 1,
            "expected_task_version": task["version"],
            "reason": "Synthetic child advance",
        },
    )
    task = result["task"]
    assert result["subtask"]["original_due_date"] == "2028-02-15"
    task = command(
        client,
        "tasks/" + task["id"] + "/due-date-changes",
        {
            "due_date": "2028-02-10",
            "expected_version": task["version"],
            "reason": "Synthetic parent advance",
        },
    )
    assert task["original_due_date"] == "2028-02-20"
    command(
        client,
        "tasks/" + task["id"] + "/schedule-changes",
        {
            "start_date": "2027-12-12",
            "expected_version": task["version"],
            "reason": "Synthetic schedule change",
        },
        409,
    )
    command(
        client,
        "objectives/" + objective["id"] + "/period-changes",
        {
            "horizon_type": "custom",
            "start_date": "2027-12-01",
            "due_date": "2028-02-15",
            "expected_version": 1,
            "reason": "Synthetic original exclusion",
        },
        409,
    )


def test_real_history_rollback_when_command_fails(core, monkeypatch):
    from app.core.errors import CommandError
    from app.services import operations

    client, _, task, _, _, _, _ = core
    original = operations.history

    def failing_history(*args, **kwargs):
        original(*args, **kwargs)
        raise CommandError(409, "SYNTHETIC_ATOMIC_FAILURE")

    monkeypatch.setattr(operations, "history", failing_history)
    command(
        client,
        "tasks/" + task["id"] + "/due-date-changes",
        {
            "due_date": "2028-02-25",
            "expected_version": 1,
            "reason": "Synthetic rollback verification",
        },
        409,
    )
    assert current_task(client, task["id"])["version"] == 1
    assert current_task(client, task["id"])["due_date"] == task["due_date"]
    assert len(client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]) == 1


def test_real_requests_duplicate_approval_and_stale_target(core):
    from test_identity import person_client

    client, _, task, _, _, person, _ = core
    leader = create_person(
        client, role="lider", department=person["department_id"], email="leader@example.invalid"
    )
    with person_client(client, leader["email"]) as peer:
        body = {
            "proposed_due_date": "2028-02-25",
            "expected_task_version": 1,
            "reason": "Synthetic date request",
        }
        proposal = command(peer, "tasks/" + task["id"] + "/due-date-requests", body, 201)
        command(peer, "tasks/" + task["id"] + "/due-date-requests", body, 409)
        assert current_task(client, task["id"])["version"] == 1
        approved = command(
            client,
            "due-date-requests/" + proposal["id"] + "/approve",
            {"expected_version": 1, "reason": "Synthetic independent approval"},
        )
        assert approved["request"]["status"] == "approved"
        assert approved["task"]["original_due_date"] == task["original_due_date"]
        body.update(proposed_due_date="2028-02-26", expected_task_version=2)
        stale = command(peer, "tasks/" + task["id"] + "/due-date-requests", body, 201)
        response = client.patch(
            "/api/v1/tasks/" + task["id"],
            json={"title": "Synthetic edited", "description": "", "expected_version": 2},
        )
        assert response.status_code == 200, response.text
        command(
            client,
            "due-date-requests/" + stale["id"] + "/approve",
            {"expected_version": 1, "reason": "Synthetic stale approval"},
            409,
        )
        assert client.get("/api/v1/due-date-requests/" + stale["id"]).json()["status"] == "pending"
        command(
            peer,
            "due-date-requests/" + stale["id"] + "/cancel",
            {"expected_version": 1, "reason": "Synthetic cancellation"},
        )
    proposal = command(
        client,
        "tasks/" + task["id"] + "/due-date-requests",
        {
            "proposed_due_date": "2028-02-26",
            "expected_task_version": 3,
            "reason": "Synthetic self request",
        },
        201,
    )
    command(
        client,
        "due-date-requests/" + proposal["id"] + "/approve",
        {"expected_version": 1, "reason": "Synthetic prohibited self approval"},
        403,
    )


@pytest.mark.parametrize("race", ["subtask", "approval"])
def test_real_concurrent_closure_serializes(core, race):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi.testclient import TestClient
    from test_identity import person_client

    client, _, task, _, _, person, terminal = core
    proposal = None
    if race == "approval":
        create_person(
            client, role="lider", department=person["department_id"], email="race@example.invalid"
        )
        with person_client(client, "race@example.invalid") as peer:
            proposal = command(
                peer,
                "tasks/" + task["id"] + "/due-date-requests",
                {
                    "proposed_due_date": "2028-02-25",
                    "expected_task_version": 1,
                    "reason": "Synthetic concurrent request",
                },
                201,
            )
    barrier = Barrier(2)

    def execute(index):
        with TestClient(
            client.app, base_url=str(client.base_url), raise_server_exceptions=False
        ) as peer:
            peer.headers.update(dict(client.headers))
            barrier.wait(timeout=10)
            if index == 0:
                return peer.post(
                    "/api/v1/tasks/" + task["id"] + "/stage-transitions",
                    json={"to_stage_id": terminal, "expected_version": 1},
                )
            if race == "subtask":
                return peer.post(
                    "/api/v1/tasks/" + task["id"] + "/subtasks",
                    json={
                        "title": "Synthetic racing child",
                        "start_date": "2027-12-11",
                        "due_date": "2028-02-15",
                        "expected_version": 1,
                    },
                )
            return peer.post(
                "/api/v1/due-date-requests/" + proposal["id"] + "/approve",
                json={"expected_version": 1, "reason": "Synthetic concurrent approval"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(execute, [0, 1]))
    assert sorted(response.status_code for response in responses) in ([200, 409], [201, 409]), [
        r.text for r in responses
    ]
    final = current_task(client, task["id"])
    assert final["version"] == 2
    assert len(client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]) == 2
    if proposal:
        decision = client.get("/api/v1/due-date-requests/" + proposal["id"]).json()
        assert (decision["status"] == "approved") == (final["due_date"] == "2028-02-25")


def test_real_original_trigger_append_only_and_timezone(core):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    client, factory, task, _, _, _, _ = core
    for sql in [
        "UPDATE tasks SET original_due_date=original_due_date+1,version=version+1",
        "UPDATE task_history SET reason='Synthetic tampering'",
        "DELETE FROM task_history",
        "DELETE FROM tasks",
        "UPDATE release_history SET version=version+1 WHERE false",
    ]:
        with pytest.raises(DBAPIError), factory.begin() as db:
            db.execute(text(sql))
    response = client.patch(
        "/api/v1/settings/organization_timezone",
        json={"value": "UTC", "reason": "Synthetic timezone lock", "expected_version": 1},
    )
    assert response.status_code == 409, response.text
    assert current_task(client, task["id"])["original_due_date"] == task["original_due_date"]


def test_real_requests_validate_proposed_interval(core):
    client, _, task, _, _, _, _ = core
    command(
        client,
        "tasks/" + task["id"] + "/due-date-requests",
        {
            "proposed_due_date": "2029-01-01",
            "expected_task_version": 1,
            "reason": "Synthetic invalid proposal",
        },
        422,
    )


def test_unconfigured_core_fails_closed(api):
    client, factory = api
    authenticated(client)
    command(
        client,
        "annual-plans",
        {
            "title": "Synthetic unconfigured",
            "horizon_type": "custom",
            "start_date": "2028-02-29",
            "due_date": "2028-02-29",
        },
        409,
    )
    from sqlalchemy import select

    from app.models.operations import AnnualPlan

    with factory() as db:
        assert db.scalar(select(AnnualPlan.id)) is None


def test_real_scopes_minimal_context_and_manager_permissions(core):
    from test_identity import person_client

    client, _, task, plan, _, person, terminal = core
    other_department = create_department(client, "other_scope")
    other_person = create_person(client, department=other_department, email="other@example.invalid")
    objective = command(
        client,
        "objectives",
        {
            "annual_plan_id": plan["id"],
            "department_id": other_department,
            "title": "Synthetic private objective",
            "description": "Never visible to another department",
            "horizon_type": "custom",
            "start_date": "2027-12-01",
            "due_date": "2028-02-29",
        },
        201,
    )
    other_task = command(
        client,
        "tasks",
        {
            "objective_id": objective["id"],
            "assignee_id": other_person["id"],
            "title": "Synthetic private task",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
        201,
    )
    command(
        client,
        "tasks/" + other_task["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": 1},
    )
    create_person(
        client,
        role="lider",
        department=person["department_id"],
        email="scopeleader@example.invalid",
    )
    create_person(client, role="gerente", email="manager@example.invalid")
    assert client.get("/api/v1/annual-plans/" + plan["id"]).json()["progress_percent"] == 50
    with person_client(client, "scopeleader@example.invalid") as leader:
        assert leader.get("/api/v1/annual-plans/" + plan["id"]).json()["progress_percent"] == 0
        assert leader.get("/api/v1/objectives/" + objective["id"]).status_code == 404
        assert leader.get("/api/v1/tasks/" + other_task["id"]).status_code == 404
        assert len(leader.get("/api/v1/tasks").json()["items"]) == 1
        command(
            leader,
            "tasks/" + task["id"] + "/due-date-changes",
            {"due_date": "2028-02-25", "expected_version": 1, "reason": "Synthetic forbidden date"},
            403,
        )
    with person_client(client, person["email"]) as member:
        assert member.get("/api/v1/annual-plans").status_code == 403
        assert member.get("/api/v1/objectives").status_code == 403
        assert member.get("/api/v1/due-date-requests").status_code == 403
        assert member.get("/api/v1/tasks/" + other_task["id"] + "/history").status_code == 404
        assert (
            member.get("/api/v1/tasks", params={"assignee_id": other_person["id"]}).json()["items"]
            == []
        )
        own = current_task(member, task["id"])
        assert set(own["objective"]) == {"id", "title", "horizon_type", "start_date", "due_date"}
        assert "tasks:self" in member.get("/api/v1/auth/me").json()["permissions"]
    with person_client(client, "manager@example.invalid") as manager:
        response = manager.patch(
            "/api/v1/tasks/" + task["id"],
            json={"title": "Synthetic denied", "description": "", "expected_version": 1},
        )
        assert response.status_code == 403, response.text
        command(
            manager,
            "tasks/" + task["id"] + "/stage-transitions",
            {"to_stage_id": terminal, "expected_version": 1},
            403,
        )
        command(
            manager,
            "tasks/" + task["id"] + "/due-date-changes",
            {"due_date": "2028-02-25", "expected_version": 1, "reason": "Synthetic manager date"},
        )


def test_real_child_request_and_history_pagination(core):
    from test_identity import person_client

    client, _, task, _, _, person, _ = core
    result = add_child(client, task)
    child, task = result["subtask"], result["task"]
    create_person(
        client,
        role="lider",
        department=person["department_id"],
        email="childleader@example.invalid",
    )
    with person_client(client, "childleader@example.invalid") as leader:
        proposal = command(
            leader,
            "subtasks/" + child["id"] + "/due-date-requests",
            {
                "proposed_due_date": "2028-02-16",
                "expected_task_version": 2,
                "expected_subtask_version": 1,
                "reason": "Synthetic child proposal",
            },
            201,
        )
    command(
        client,
        "due-date-requests/" + proposal["id"] + "/approve",
        {"expected_version": 1, "reason": "Synthetic child approval"},
    )
    updated = client.get("/api/v1/subtasks/" + child["id"]).json()
    assert updated["due_date"] == "2028-02-16" and updated["original_due_date"] == "2028-02-15"
    assert updated["version"] == 2 and current_task(client, task["id"])["version"] == 3
    events = []
    cursor = None
    while True:
        page = client.get(
            "/api/v1/tasks/" + task["id"] + "/history",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
        ).json()
        events.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(events) == 3 and len({event["id"] for event in events}) == 3
    assert events[-1]["event_type"] == "subtask_due_date_changed"
    command(
        client,
        "due-date-requests/" + proposal["id"] + "/reject",
        {"expected_version": 2, "reason": "Synthetic terminal mutation"},
        409,
    )


def test_real_occupied_stage_and_evidence_gate(core):
    client, _, task, _, _, _, terminal = core
    body = workflow_body()
    for stage in body["stages"]:
        stage["expected_version"] = 1
        if stage["kind"] == "completed":
            stage["requires_evidence"] = True
    for edge in body["transitions"]:
        edge["expected_version"] = 1
    body["stages"].append(
        {
            "code": "fixture_middle",
            "name": "Synthetic middle",
            "kind": "open",
            "position": 2,
            "is_initial": False,
            "is_active": True,
            "requires_reason": False,
            "requires_evidence": False,
            "reason": "Synthetic middle stage",
        }
    )
    for source, target in [("fixture_open", "fixture_middle"), ("fixture_middle", "fixture_done")]:
        body["transitions"].append(
            {
                "from_code": source,
                "to_code": target,
                "allowed_roles": ["admin", "lider", "colaborador"],
                "is_active": True,
            }
        )
    graph = command(client, "workflow", body, 201)
    middle = next(stage for stage in graph["stages"] if stage["code"] == "fixture_middle")
    command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": 1},
        422,
    )
    task = command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"to_stage_id": middle["id"], "expected_version": 1},
    )
    response = client.patch(
        "/api/v1/workflow-stages/" + middle["id"],
        json={
            **{
                key: middle[key]
                for key in ["name", "position", "requires_reason", "requires_evidence"]
            },
            "is_active": False,
            "expected_version": 1,
            "reason": "Synthetic occupied deactivation",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "OCCUPIED_STAGE"
    assert current_task(client, task["id"])["stage_id"] == middle["id"]


def test_real_open_assignment_blocks_admin_transfer_and_mass_assignment(core):
    client, _, task, _, _, person, _ = core
    other = create_department(client, "transfer_target")
    body = {key: person[key] for key in ["display_name", "role", "is_active"]}
    body.update(department_id=other, expected_version=1, reason="Synthetic prohibited transfer")
    response = client.patch("/api/v1/users/" + person["id"], json=body)
    assert response.status_code == 409, response.text
    command(
        client,
        "tasks/" + task["id"] + "/assignments",
        {
            "assignee_id": person["id"],
            "expected_version": 1,
            "reason": "Synthetic unchanged assignment",
        },
    )
    for forbidden in [
        "original_due_date",
        "due_date",
        "completed_at",
        "stage_id",
        "assignee_id",
        "objective_id",
        "version",
    ]:
        response = client.patch(
            "/api/v1/tasks/" + task["id"],
            json={
                "title": "Synthetic forbidden patch",
                "description": "",
                "expected_version": 2,
                forbidden: task.get(forbidden),
            },
        )
        assert response.status_code == 422, (forbidden, response.text)
    assert current_task(client, task["id"])["version"] == 2


def test_backup_failure_prevents_f3_upgrade(tmp_path):
    from unittest.mock import patch

    from tools import f3_local

    with (
        patch.object(f3_local, "snapshot", return_value={}),
        patch.object(f3_local, "backup_restore", side_effect=RuntimeError("backup failed")),
        patch.object(f3_local, "upgrade") as upgrade,
        pytest.raises(RuntimeError, match="backup failed"),
    ):
        f3_local.controlled_upgrade(object(), tmp_path)
    upgrade.assert_not_called()


def test_restore_failure_prevents_f3_source_upgrade(tmp_path):
    from unittest.mock import patch

    from tools import f3_local

    with (
        patch.object(f3_local, "snapshot", return_value={}),
        patch.object(f3_local, "backup_restore", return_value={}),
        patch.object(
            f3_local, "restore_upgrade_rehearsal", side_effect=RuntimeError("restore failed")
        ),
        patch.object(f3_local, "upgrade") as upgrade,
        pytest.raises(RuntimeError, match="restore failed"),
    ):
        f3_local.controlled_upgrade(object(), tmp_path)
    upgrade.assert_not_called()


@pytest.mark.parametrize("value", [0, "2028-02-29T00:00:00Z", "20280229", "2028-W09-2"])
def test_civil_dates_reject_timestamp_and_alternate_forms(value):
    with pytest.raises(ValidationError):
        PlanCreate(
            title="Synthetic strict date",
            horizon_type="custom",
            start_date=value,
            due_date="2028-02-29",
        )


def test_f5_migration_preserves_existing_synthetic_f2_data_through_f3():
    import os

    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit local PostgreSQL authorization required")
    from sqlalchemy.orm import Session

    from app.models.identity import Department, HorizonType
    from tools import f2_local, f3_local, f5_local

    with f2_local.isolated_database() as name:
        f2_local.upgrade(name, f3_local.SOURCE)
        engine = f2_local.migration_engine(name)
        try:
            with Session(engine) as db, db.begin():
                db.add(Department(code="preserved", name="Synthetic preserved department"))
                db.add(HorizonType(code="custom", name="Synthetic preserved label", position=37))
            url = f3_local.MigrationSettings().migration_database_url.get_secret_value()
            with f3_local.local.role_connection(url, name) as connection:
                before = f3_local.snapshot(connection)
                f2_local.upgrade(name, f5_local.SOURCE)
                middle = f2_local.snapshot(connection)
                assert set(middle["tables"]) - set(before["tables"]) == f3_local.NEW_TABLES
                assert not any(middle["rows"][table] for table in f3_local.NEW_TABLES)
                for table, rows in before["rows"].items():
                    if table != "alembic_version":
                        assert middle["rows"][table] == rows
                f2_local.upgrade(name, f5_local.HEAD)
                after = f2_local.snapshot(connection)
                assert set(after["tables"]) - set(middle["tables"]) == {"evidence_files"}
                assert after["rows"]["evidence_files"] == []
                for table, rows in middle["rows"].items():
                    if table != "alembic_version":
                        assert after["rows"][table] == rows
                assert after["rows"]["alembic_version"] == ['{"version_num": "20261124_0004"}']
                f2_local.upgrade(name, f5_local.HEAD)
                assert f2_local.snapshot(connection) == after
        finally:
            engine.dispose()


def test_real_aggregate_weights_tasks_and_filtered_lists(core):
    client, _, task, plan, objective, person, terminal = core
    empty = command(
        client,
        "objectives",
        {
            "annual_plan_id": plan["id"],
            "department_id": person["department_id"],
            "title": "Synthetic separate objective",
            "horizon_type": "custom",
            "start_date": "2027-12-01",
            "due_date": "2028-02-29",
        },
        201,
    )
    assert empty["progress_percent"] is None
    for selected in [objective, objective, empty]:
        created = command(
            client,
            "tasks",
            {
                "objective_id": selected["id"],
                "assignee_id": person["id"],
                "title": "Synthetic weighted task",
                "start_date": "2027-12-10",
                "due_date": "2028-02-20",
            },
            201,
        )
    command(
        client,
        "tasks/" + created["id"] + "/stage-transitions",
        {"to_stage_id": terminal, "expected_version": 1},
    )
    assert client.get("/api/v1/annual-plans/" + plan["id"]).json()["progress_percent"] == 25
    for status, count in [("pending", 3), ("on_time", 1), ("late", 0), ("overdue", 0)]:
        items = client.get(
            "/api/v1/tasks", params={"annual_plan_id": plan["id"], "punctuality_status": status}
        ).json()["items"]
        assert len(items) == count
        assert all(item["punctuality_status"] == status for item in items)
    assert current_task(client, task["id"])["version"] == 1


def test_real_period_contraction_races_child_creation(core):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi.testclient import TestClient

    client, _, _, _, objective, person, _ = core
    barrier = Barrier(2)

    def execute(index):
        with TestClient(
            client.app, base_url=str(client.base_url), raise_server_exceptions=False
        ) as peer:
            peer.headers.update(dict(client.headers))
            barrier.wait(timeout=10)
            if index == 0:
                return peer.post(
                    "/api/v1/objectives/" + objective["id"] + "/period-changes",
                    json={
                        "horizon_type": "custom",
                        "start_date": "2027-12-01",
                        "due_date": "2028-02-25",
                        "expected_version": 1,
                        "reason": "Synthetic concurrent contraction",
                    },
                )
            return peer.post(
                "/api/v1/tasks",
                json={
                    "objective_id": objective["id"],
                    "assignee_id": person["id"],
                    "title": "Synthetic concurrent child",
                    "start_date": "2027-12-10",
                    "due_date": "2028-02-28",
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(execute, [0, 1]))
    assert [response.status_code for response in responses] in [[200, 422], [409, 201]], [
        r.text for r in responses
    ]


def test_real_request_approval_rollback_includes_decision(core, monkeypatch):
    from test_identity import person_client

    from app.core.errors import CommandError
    from app.services import operations

    client, _, task, _, _, person, _ = core
    create_person(
        client, role="lider", department=person["department_id"], email="atomic@example.invalid"
    )
    with person_client(client, "atomic@example.invalid") as peer:
        proposal = command(
            peer,
            "tasks/" + task["id"] + "/due-date-requests",
            {
                "proposed_due_date": "2028-02-25",
                "expected_task_version": 1,
                "reason": "Synthetic atomic proposal",
            },
            201,
        )
    original = operations.administrative_event

    def failing_event(*args, **kwargs):
        original(*args, **kwargs)
        raise CommandError(409, "SYNTHETIC_ATOMIC_FAILURE")

    monkeypatch.setattr(operations, "administrative_event", failing_event)
    command(
        client,
        "due-date-requests/" + proposal["id"] + "/approve",
        {"expected_version": 1, "reason": "Synthetic failed decision"},
        409,
    )
    assert client.get("/api/v1/due-date-requests/" + proposal["id"]).json()["status"] == "pending"
    assert current_task(client, task["id"])["version"] == 1
    assert len(client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]) == 1


@pytest.fixture
def core(api):
    client, factory = api
    authenticated(client)
    department = create_department(client, "core_fixture")
    person = create_person(client, department=department)
    for key, value in {
        "organization_name": "Synthetic F3",
        "organization_timezone": "America/Mexico_City",
        "evidence_max_bytes": 1024,
        "export_max_rows": 100,
    }.items():
        response = client.post(
            "/api/v1/settings",
            json={"key": key, "value": value, "reason": "Synthetic configuration"},
        )
        assert response.status_code == 201, response.text
    for position, code in enumerate(["annual", "semiannual", "quarterly", "monthly", "custom"]):
        assert (
            client.post(
                "/api/v1/horizon-types",
                json={
                    "code": code,
                    "name": "Synthetic " + code,
                    "position": position,
                    "reason": "Synthetic configuration",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/api/v1/priorities",
            json={
                "code": "normal",
                "name": "Synthetic normal",
                "position": 0,
                "reason": "Synthetic configuration",
            },
        ).status_code
        == 201
    )
    response = client.post("/api/v1/workflow", json=workflow_body())
    assert response.status_code == 201, response.text
    stages = client.get("/api/v1/workflow-stages").json()["items"]
    terminal = next(stage["id"] for stage in stages if stage["kind"] == "completed")
    response = client.post(
        "/api/v1/annual-plans",
        json={
            "title": "Synthetic cross-year plan",
            "horizon_type": "custom",
            "start_date": "2027-11-15",
            "due_date": "2028-02-29",
        },
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    response = client.post(
        "/api/v1/objectives",
        json={
            "annual_plan_id": plan["id"],
            "department_id": department,
            "title": "Synthetic objective",
            "horizon_type": "monthly",
            "start_date": "2027-12-01",
            "due_date": "2028-02-29",
        },
    )
    assert response.status_code == 201, response.text
    objective = response.json()
    response = client.post(
        "/api/v1/annual-plans/" + plan["id"] + "/status-changes",
        json={"status": "active", "expected_version": 1, "reason": "Synthetic activation"},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": objective["id"],
            "assignee_id": person["id"],
            "title": "Synthetic task",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert response.status_code == 201, response.text
    yield client, factory, response.json(), plan, objective, person, terminal


def test_real_core_creation_and_atomic_history(core):
    client, _, task, _, _, _, terminal = core
    assert task["original_due_date"] == task["due_date"]
    assert task["progress_percent"] == 0
    response = client.post(
        "/api/v1/tasks/" + task["id"] + "/stage-transitions",
        json={"to_stage_id": terminal, "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["progress_percent"] == 100
    assert response.json()["completed_at"] is not None
    events = client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]
    assert [event["event_type"] for event in events] == ["task_created", "stage_changed"]
    assert events[-1]["before_data"]["completed_at"] is None
    assert events[-1]["after_data"]["completed_at"] is not None


@pytest.mark.parametrize(
    "count,done,closed,expected",
    [
        (0, 0, False, 0),
        (0, 0, True, 100),
        (4, 1, False, 25),
        (4, 4, False, 100),
    ],
)
def test_progress(count, done, closed, expected):
    assert task_progress(done, count, closed) == expected


def test_local_midnight_and_original_lateness():
    record = SimpleNamespace(
        due_date=date(2027, 3, 15),
        original_due_date=date(2027, 3, 10),
        completed_at=datetime(2027, 3, 12, 18, tzinfo=UTC),
    )
    moment = datetime(2027, 3, 16, tzinfo=UTC)
    result = timeliness(record, moment, ZoneInfo("America/Mexico_City"))
    assert result == {
        "punctuality_status": "on_time",
        "baseline_punctuality_status": "late",
        "is_overdue": False,
        "due_date_delta_days": 5,
        "delay_days": 0,
        "baseline_delay_days": 2,
    }
    record.completed_at = None
    assert not timeliness(
        record, datetime(2027, 3, 16, 5, 59, tzinfo=UTC), ZoneInfo("America/Mexico_City")
    )["is_overdue"]
    assert timeliness(
        record, datetime(2027, 3, 16, 6, tzinfo=UTC), ZoneInfo("America/Mexico_City")
    )["is_overdue"]


def test_periods_and_mass_assignment():
    for start, due in [("2027-11-15", "2028-02-20"), ("2028-02-29", "2028-02-29")]:
        assert Period(horizon_type="custom", start_date=start, due_date=due)
    with pytest.raises(ValidationError):
        Period(horizon_type="annual", start_date="2028-03-01", due_date="2028-02-29")
    with pytest.raises(ValidationError):
        TaskUpdate(
            title="Synthetic", description="", expected_version=1, original_due_date="2028-01-01"
        )
