import os
from datetime import UTC, datetime, timedelta

import pytest
from test_identity import api as api
from test_identity import tokens as tokens
from test_operations import core as core

from app.core.errors import CommandError
from app.services.collaboration import assert_acyclic, impeded_seconds


@pytest.mark.parametrize("permitted", [False, True])
def test_f9_recurrence_defers_schedule_mutation_until_versioned_save(monkeypatch, permitted):
    from datetime import date
    from types import SimpleNamespace
    from uuid import uuid4

    from fastapi.encoders import jsonable_encoder

    from app.models.collaboration import ServicePrincipal, TemplateVersion
    from app.models.identity import User
    from app.services import collaboration

    owner = SimpleNamespace(id=uuid4(), role="admin", department_id=None)
    principal = SimpleNamespace(id=uuid4())
    schedule = SimpleNamespace(
        id=uuid4(),
        owner_user_id=owner.id,
        service_principal_id=principal.id,
        objective_id=uuid4(),
        template_version_id=uuid4(),
        assignee_id=uuid4(),
        version=2,
        enabled=True,
        next_due_at=date(2027, 12, 19),
        timezone="UTC",
        calendar_snapshot={},
        configuration_revision_id=uuid4(),
        frequency="daily",
        interval=1,
        start_date=date(2027, 12, 19),
        end_date=None,
        occurrence_count=2,
        end_policy="last_day",
        non_business_policy="keep",
        missed_policy="catch_up",
    )
    objective = SimpleNamespace(id=schedule.objective_id)
    template_version = SimpleNamespace(
        template_id=uuid4(), payload={}, payload_hash=collaboration.canonical_hash({})
    )
    queries = iter([schedule, None, object(), None] if permitted else [schedule, None])
    database = SimpleNamespace(
        scalar=lambda query: next(queries),
        get=lambda model, identity: {
            User: owner,
            ServicePrincipal: principal,
            TemplateVersion: template_version if permitted else None,
        }.get(model),
    )
    monkeypatch.setattr(collaboration, "require_module", lambda *arguments: None)
    monkeypatch.setattr(
        collaboration, "resource", lambda *arguments: (objective, object(), objective)
    )
    monkeypatch.setattr(collaboration.operation, "lock_context", lambda *arguments, **options: None)
    monkeypatch.setattr(collaboration.operation, "lock_rows", lambda *arguments: None)
    monkeypatch.setattr(
        collaboration.operation, "instant", lambda database: datetime(2027, 12, 20, tzinfo=UTC)
    )
    monkeypatch.setattr(
        collaboration.operation, "state", lambda record: jsonable_encoder(vars(record))
    )
    monkeypatch.setattr(collaboration, "recurrence_context_approved", lambda *arguments: permitted)
    monkeypatch.setattr(
        collaboration,
        "occurrence_dates",
        lambda *arguments, **options: iter([(date(2027, 12, 21), date(2027, 12, 21), False)]),
    )
    monkeypatch.setattr(
        collaboration.operation,
        "bump",
        lambda database, record: setattr(record, "version", record.version + 1),
    )
    saves = []

    def save(database, user, request, record, before, command, reason):
        if command == "recurrence_started":
            record.id, record.version = uuid4(), 1
        if command != "recurrence_run":
            assert schedule.enabled is True and schedule.version == 2
            assert schedule.next_due_at == date(2027, 12, 19)
        saves.append(command)

    monkeypatch.setattr(collaboration, "save_record", save)
    body = SimpleNamespace(
        expected_version=2,
        idempotency_key=uuid4(),
        through_date=date(2027, 12, 20),
        reason="Synthetic recurrence pause",
        model_dump=lambda **options: {},
    )
    result = collaboration.run_schedule(
        database,
        owner,
        schedule.id,
        body,
        SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4()))),
    )
    assert schedule.enabled is permitted and schedule.version == 3
    assert schedule.next_due_at == date(2027, 12, 21 if permitted else 19)
    assert result["job"]["state"] == ("succeeded" if permitted else "paused")
    assert saves == ["recurrence_started", "recurrence_finished", "recurrence_run"]


def test_f9_api_dependency_impediment_and_concurrency(core):
    client, _factory, task, _plan, objective, person, _terminal = core
    reason = "Synthetic F9 isolated authorization"
    second = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": objective["id"],
            "assignee_id": person["id"],
            "title": "Synthetic successor",
            "description": "",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert second.status_code == 201, second.text
    successor = second.json()
    context = client.get("/api/v1/tasks/" + successor["id"] + "/dependencies").json()
    body = {
        "predecessor_task_id": task["id"],
        "expected_version": successor["version"],
        "expected_predecessor_version": task["version"],
        "expected_plan_version": context["plan_version"],
        "active": True,
        "reason": reason,
    }
    response = client.put("/api/v1/tasks/" + successor["id"] + "/dependencies", json=body)
    assert response.status_code == 200, response.text
    assert (
        client.put("/api/v1/tasks/" + successor["id"] + "/dependencies", json=body).status_code
        == 409
    )
    reverse = {
        "predecessor_task_id": successor["id"],
        "expected_version": task["version"],
        "expected_predecessor_version": response.json()["task_version"],
        "expected_plan_version": response.json()["plan_version"],
        "active": True,
        "reason": reason,
    }
    cycle = client.put("/api/v1/tasks/" + task["id"] + "/dependencies", json=reverse)
    assert cycle.status_code == 409 and cycle.json()["code"] == "DEPENDENCY_CYCLE", cycle.text
    opened = client.post(
        "/api/v1/tasks/" + task["id"] + "/impediments",
        json={
            "expected_version": task["version"],
            "owner_user_id": person["id"],
            "severity": "high",
            "kind": "external",
            "required_area": None,
            "reason": reason,
        },
    )
    assert opened.status_code == 201, opened.text
    impediment = opened.json()["impediment"]
    current = client.get("/api/v1/tasks/" + task["id"]).json()
    assert current["collaboration"]["open_impediments"] == 1
    assert current["stage_id"] == task["stage_id"] and current["due_date"] == task["due_date"]
    resolved = client.post(
        "/api/v1/tasks/" + task["id"] + "/impediments/" + impediment["id"] + "/resolution",
        json={
            "expected_version": impediment["version"],
            "expected_task_version": current["version"],
            "resolution": "Synthetic issue resolved",
            "reason": reason,
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert (
        client.get("/api/v1/tasks/" + task["id"]).json()["collaboration"]["open_impediments"] == 0
    )


def test_f9_api_typed_metadata_plain_comments_search_and_saved_views(core):
    from uuid import uuid4

    client, _factory, task, _plan, _objective, _person, _terminal = core
    reason = "Synthetic F9 typed metadata operation"
    definitions, values = {}, {}
    for kind, value in (
        ("text", "Synthetic searchable metadata"),
        ("number", 12.125),
        ("boolean", False),
        ("date", "2027-12-14"),
        ("url", "https://example.invalid/synthetic"),
        ("select", None),
        ("multi_select", None),
    ):
        identity = str(uuid4())
        options = (
            [
                {
                    "id": None,
                    "expected_version": 0,
                    "code": "synthetic",
                    "label": "Synthetic",
                    "position": 0,
                    "is_active": True,
                }
            ]
            if kind in {"select", "multi_select"}
            else []
        )
        response = client.put(
            "/api/v1/collaboration/custom-fields/" + identity,
            json={
                "entity_type": "task",
                "key": "synthetic_" + kind,
                "label": "Synthetic " + kind,
                "data_type": kind,
                "constraints": {},
                "scope_kind": "organization",
                "department_id": None,
                "required_stage_ids": [],
                "required_on_create": False,
                "active": True,
                "options": options,
                "expected_version": 0,
                "reason": reason,
            },
        )
        assert response.status_code == 200, response.text
        definitions[kind] = response.json()
        if kind in {"select", "multi_select"}:
            value = response.json()["options"][0]["id"]
            if kind == "multi_select":
                value = [value]
        values[identity] = value
    path = "/api/v1/collaboration/task/" + task["id"]
    response = client.put(
        path + "/metadata",
        json={"expected_version": task["version"], "reason": reason, "custom_fields": values},
    )
    assert response.status_code == 200, response.text
    current_version = response.json()["resource_version"]
    assert len(response.json()["values"]) == 7
    bad = client.put(
        path + "/metadata",
        json={
            "expected_version": current_version,
            "reason": reason,
            "custom_fields": {definitions["boolean"]["id"]: 1},
        },
    )
    assert bad.status_code == 422, bad.text
    comment = client.post(
        path + "/comments",
        json={
            "expected_version": 0,
            "expected_resource_version": current_version,
            "body": "<b>ocotesyntheticplaintext</b>",
            "mention_ids": [],
            "parent_comment_id": None,
            "annulled": False,
            "reason": reason,
        },
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["comment"]["body"] == "<b>ocotesyntheticplaintext</b>"
    revisions = client.get(path + "/comments/" + comment.json()["comment"]["id"] + "/revisions")
    assert (
        revisions.status_code == 200
        and revisions.json()["items"][0]["body"] == "<b>ocotesyntheticplaintext</b>"
    ), revisions.text
    found = client.post(
        "/api/v1/collaboration/search",
        json={"q": "ocotesyntheticplaintext", "entity_type": "comment"},
    )
    assert found.status_code == 200 and len(found.json()["items"]) == 1, found.text
    view_id = str(uuid4())
    saved = client.put(
        "/api/v1/collaboration/saved-views/" + view_id,
        json={
            "expected_version": 0,
            "reason": reason,
            "name": "Synthetic scoped view",
            "entity_type": "task",
            "scope_kind": "personal",
            "department_id": None,
            "active": True,
            "filters": {
                "entity_type": "task",
                "q": "",
                "custom_fields": [
                    {"definition_id": definitions["number"]["id"], "operator": "gte", "value": 10}
                ],
            },
        },
    )
    assert saved.status_code == 200, saved.text
    result = client.get("/api/v1/collaboration/saved-views/" + view_id + "/results")
    assert result.status_code == 200 and result.json()["items"][0]["id"] == task["id"], result.text


def test_f9_api_template_and_recurrence_are_idempotent_with_technical_actor(core, monkeypatch):
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import event, func, select

    from app.models.operations import TaskHistory
    from app.services import operations

    client, factory, _task, _plan, objective, person, _terminal = core
    database_errors = []

    def capture_database_error(context):
        original = context.original_exception
        diagnostic = getattr(original, "diag", None)
        database_errors.append(
            (
                getattr(original, "sqlstate", None),
                getattr(diagnostic, "constraint_name", None),
                getattr(diagnostic, "message_primary", None),
            )
        )

    event.listen(factory.kw["bind"], "handle_error", capture_database_error)
    reason = "Synthetic F9 generation only in UUID"
    monkeypatch.setattr(
        operations, "instant", lambda database: datetime(2027, 12, 20, 12, tzinfo=UTC)
    )
    user = client.get("/api/v1/auth/me").json()
    calendar = client.post(
        "/api/v1/admin/calendars",
        json={
            "expected_version": 0,
            "reason": reason,
            "current_password": "Synthetic-password-123!",
            "name": "Synthetic F9 calendar",
            "scope_kind": "organization",
            "department_id": None,
            "weekday_mask": 31,
            "inheritance": "replace",
        },
    )
    assert calendar.status_code == 201, calendar.text
    template = client.put(
        "/api/v1/collaboration/templates/" + str(uuid4()),
        json={
            "expected_version": 0,
            "reason": reason,
            "entity_type": "task",
            "name": "Synthetic F9 template",
            "scope_kind": "organization",
            "department_id": None,
            "is_active": True,
            "payload": {
                "title": "Synthetic generated task",
                "description": "",
                "horizon_type": "custom",
                "priority_id": None,
                "duration_days": 2,
                "subtasks": [],
            },
        },
    )
    assert template.status_code == 200, template.text
    principal_id = str(uuid4())
    principal = client.put(
        "/api/v1/collaboration/service-principals/" + principal_id,
        json={
            "expected_version": 0,
            "reason": reason,
            "name": "Synthetic F9 principal",
            "department_ids": [person["department_id"]],
            "approved_scopes": ["tasks:create"],
            "is_active": True,
        },
    )
    assert principal.status_code == 200, principal.text
    schedule_id = str(uuid4())
    body = {
        "expected_version": 0,
        "reason": reason,
        "template_version_id": template.json()["template_version"]["id"],
        "owner_user_id": user["id"],
        "service_principal_id": principal_id,
        "objective_id": objective["id"],
        "assignee_id": person["id"],
        "calendar_id": calendar.json()["id"],
        "enabled": False,
        "frequency": "daily",
        "interval": 1,
        "start_date": "2027-12-19",
        "end_date": None,
        "occurrence_count": 2,
        "end_policy": "last_day",
        "non_business_policy": "keep",
        "missed_policy": "catch_up",
    }
    schedule = client.put("/api/v1/collaboration/recurrence-schedules/" + schedule_id, json=body)
    assert schedule.status_code == 200 and schedule.json()["enabled"] is False, schedule.text
    body.update(expected_version=1, enabled=True)
    enabled = client.put("/api/v1/collaboration/recurrence-schedules/" + schedule_id, json=body)
    assert enabled.status_code == 200, enabled.text
    run = {
        "expected_version": enabled.json()["version"],
        "reason": reason,
        "idempotency_key": str(uuid4()),
        "through_date": "2027-12-20",
        "limit": 100,
    }
    first = client.post(
        "/api/v1/collaboration/recurrence-schedules/" + schedule_id + "/runs", json=run
    )
    assert first.status_code == 200 and len(first.json()["generated_ids"]) == 2, (
        first.text,
        database_errors,
    )
    repeat = client.post(
        "/api/v1/collaboration/recurrence-schedules/" + schedule_id + "/runs", json=run
    )
    assert repeat.status_code == 200 and repeat.json()["job"]["id"] == first.json()["job"]["id"], (
        repeat.text
    )
    with factory() as database:
        assert (
            database.scalar(
                select(func.count())
                .select_from(TaskHistory)
                .where(
                    TaskHistory.actor_id.is_(None),
                    TaskHistory.actor_service_id == principal_id,
                    TaskHistory.event_type == "recurrence_generated",
                )
            )
            == 2
        )
    body.update(expected_version=0, enabled=False)
    paused_id = str(uuid4())
    response = client.put("/api/v1/collaboration/recurrence-schedules/" + paused_id, json=body)
    assert response.status_code == 200, response.text
    body.update(expected_version=1, enabled=True)
    response = client.put("/api/v1/collaboration/recurrence-schedules/" + paused_id, json=body)
    assert response.status_code == 200, response.text
    response = client.put(
        "/api/v1/collaboration/service-principals/" + principal_id,
        json={
            "expected_version": principal.json()["version"],
            "reason": reason,
            "name": "Synthetic F9 principal",
            "department_ids": [person["department_id"]],
            "approved_scopes": ["tasks:create"],
            "is_active": False,
        },
    )
    assert response.status_code == 200, response.text
    from tools.f11_worker import recurrence_tick as tick

    report = tick(factory, 1)
    assert report == {"processed": 0, "generated": 0, "paused": 1, "conflicts": 0, "failures": 0}


@pytest.mark.parametrize("role", ["colaborador", "lider", "gerente"])
def test_f9_api_role_and_department_scope_cannot_be_bypassed(core, role):
    from uuid import uuid4

    from test_identity import create_department, create_person, person_client

    client, _factory, task, plan, _objective, person, _terminal = core
    reason = "Synthetic F9 role and scope verification"
    other_department = create_department(client, "f9_other")
    other_user = create_person(
        client, department=other_department, email="other-f9@example.invalid"
    )
    other_objective = client.post(
        "/api/v1/objectives",
        json={
            "annual_plan_id": plan["id"],
            "department_id": other_department,
            "title": "Private other department",
            "horizon_type": "custom",
            "start_date": "2027-12-01",
            "due_date": "2028-02-29",
        },
    )
    assert other_objective.status_code == 201, other_objective.text
    other_task = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": other_objective.json()["id"],
            "assignee_id": other_user["id"],
            "title": "Hidden other department F9",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert other_task.status_code == 201, other_task.text
    actor = (
        person
        if role == "colaborador"
        else create_person(
            client,
            role=role,
            department=person["department_id"] if role == "lider" else None,
            email=role + "-f9@example.invalid",
        )
    )
    scoped = person_client(client, actor["email"])
    hidden = other_task.json()["id"]
    expected = 200 if role == "gerente" else 404
    for path in (
        "/tasks/" + hidden + "/dependencies",
        "/tasks/" + hidden + "/impediments",
        "/collaboration/task/" + hidden + "/metadata",
        "/collaboration/task/" + hidden + "/comments",
    ):
        response = scoped.get("/api/v1" + path)
        assert response.status_code == expected, response.text
    response = scoped.get(
        "/api/v1/collaboration/task/" + hidden + "/comments/" + str(uuid4()) + "/revisions"
    )
    assert response.status_code == 404, response.text
    if role != "lider":
        context = client.get("/api/v1/tasks/" + task["id"] + "/dependencies").json()
        response = scoped.put(
            "/api/v1/tasks/" + task["id"] + "/dependencies",
            json={
                "predecessor_task_id": hidden,
                "expected_version": task["version"],
                "expected_predecessor_version": other_task.json()["version"],
                "expected_plan_version": context["plan_version"],
                "active": True,
                "reason": reason,
            },
        )
        assert response.status_code == 403, response.text
    if role == "colaborador":
        response = scoped.put(
            "/api/v1/collaboration/task/" + task["id"] + "/metadata",
            json={"expected_version": task["version"], "reason": reason, "tag_ids": []},
        )
        assert response.status_code == 403, response.text
        response = scoped.post(
            "/api/v1/collaboration/search", json={"q": "", "entity_type": "task"}
        )
        assert response.status_code == 200 and [row["id"] for row in response.json()["items"]] == [
            task["id"]
        ], response.text
        assert response.json()["counts"] == {"task": 1}
    if role == "gerente":
        response = scoped.post(
            "/api/v1/tasks/" + task["id"] + "/impediments",
            json={
                "owner_user_id": person["id"],
                "expected_version": task["version"],
                "severity": "medium",
                "kind": "external",
                "required_area": None,
                "reason": reason,
            },
        )
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("edges", [[], [(1, 2)], [(1, 2), (1, 3), (2, 4), (3, 4)]])
def test_f9_dag_accepts_acyclic_graphs(edges):
    assert_acyclic(edges)


@pytest.mark.parametrize(
    "edges",
    [[(1, 1)], [(1, 2), (2, 1)], [(1, 2), (2, 3), (3, 4), (4, 1)], [(1, 2), (1, 2)]],
)
def test_f9_dag_rejects_cycles_self_references_and_duplicates(edges):
    with pytest.raises(CommandError):
        assert_acyclic(edges)


def test_f9_dag_handles_long_paths_without_recursion_limit():
    edges = [(index, index + 1) for index in range(5000)]
    assert_acyclic(edges)
    with pytest.raises(CommandError):
        assert_acyclic([*edges, (5000, 0)])


def test_f9_impediment_duration_is_union_not_a_score():
    start = datetime(2026, 11, 25, tzinfo=UTC)
    moment = start + timedelta(hours=5)
    assert (
        impeded_seconds(
            [
                (start, start + timedelta(hours=2)),
                (start + timedelta(hours=1), start + timedelta(hours=3)),
                (start + timedelta(hours=4), None),
            ],
            moment,
        )
        == 4 * 3600
    )
    assert impeded_seconds([], moment) == 0


@pytest.mark.parametrize(
    "kind,value",
    [
        ("number", True),
        ("number", "12"),
        ("number", 1.12345),
        ("number", float("inf")),
        ("number", 100000000000000),
        ("boolean", 1),
        ("boolean", "true"),
        ("date", "2026-2-01"),
        ("date", "2026-02-30"),
        ("text", {}),
        ("text", "x" * 2001),
        ("url", "javascript:alert(1)"),
        ("url", "https://user:secret@example.invalid"),
        ("select", "unknown"),
        ("multi_select", []),
    ],
)
def test_f9_custom_fields_reject_coercion_and_invalid_values(kind, value):
    from types import SimpleNamespace

    from app.services.collaboration import typed_value

    with pytest.raises(CommandError):
        typed_value(SimpleNamespace(data_type=kind, constraints={}), value)


def test_f9_custom_fields_preserve_boolean_false_decimal_and_plain_text():
    from decimal import Decimal
    from types import SimpleNamespace

    from app.services.collaboration import plain_text, typed_value

    assert (
        typed_value(SimpleNamespace(data_type="boolean", constraints={}), False)["boolean_value"]
        is False
    )
    assert typed_value(SimpleNamespace(data_type="number", constraints={}), 12.1234)[
        "number_value"
    ] == Decimal("12.1234")
    assert (
        plain_text("<script>literal text, not HTML</script>")
        == "<script>literal text, not HTML</script>"
    )
    with pytest.raises(CommandError):
        plain_text("text\x00control")


def test_f9_monthly_recurrence_retains_anchor_and_explicit_business_policy():
    from itertools import islice

    from app.schemas.collaboration import RecurrenceRule
    from app.services.collaboration import occurrence_dates

    rule = RecurrenceRule(
        frequency="monthly",
        interval=1,
        start_date="2028-01-31",
        end_date=None,
        occurrence_count=3,
        end_policy="last_day",
        non_business_policy="next",
        missed_policy="catch_up",
    )
    calendar = {"weekday_mask": 31, "holidays": ["2028-02-29"]}
    rows = list(islice(occurrence_dates(rule, calendar), 4))
    assert [row[0].isoformat() for row in rows] == ["2028-01-31", "2028-02-29", "2028-03-31"]
    assert rows[1][1].isoformat() == "2028-03-01"
    assert rows == list(occurrence_dates(rule, calendar))


@pytest.mark.parametrize(
    "revoked",
    [
        None,
        "enabled",
        "plan",
        "owner",
        "principal",
        "scope",
        "template",
        "assignee",
        "department",
        "subtasks",
    ],
)
def test_f9_recurrence_pauses_revoked_context_without_generating(revoked):
    from types import SimpleNamespace

    from app.services.collaboration import recurrence_context_approved

    schedule = SimpleNamespace(enabled=revoked != "enabled")
    plan = SimpleNamespace(status="closed" if revoked == "plan" else "active")
    objective = SimpleNamespace(department_id="own")
    owner = SimpleNamespace(is_active=revoked != "owner", role="lider", department_id="own")
    principal = SimpleNamespace(
        is_active=revoked != "principal",
        department_ids=["other" if revoked == "scope" else "own"],
        approved_scopes=["tasks:create"],
    )
    template = SimpleNamespace(
        is_active=revoked != "template", entity_type="task", department_id=None
    )
    version = SimpleNamespace(payload={"subtasks": ["synthetic"] if revoked == "subtasks" else []})
    assignee = SimpleNamespace(
        is_active=revoked != "assignee",
        role="colaborador",
        department_id="other" if revoked == "department" else "own",
    )
    assert recurrence_context_approved(
        schedule, plan, objective, owner, principal, template, version, assignee
    ) is (revoked is None)


def test_f9_scope_is_inside_dependency_and_mention_queries():
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.models.operations import Objective, Task
    from app.services.collaboration import readers_query, visible_dependencies

    identity, department = uuid4(), uuid4()
    user = SimpleNamespace(id=identity, role="colaborador", department_id=department)
    task = Task(id=uuid4(), assignee_id=identity)
    sql = str(visible_dependencies(None, user, task).compile(dialect=postgresql.dialect()))
    assert sql.count("tasks.assignee_id =") == 2
    assert "task_dependencies.predecessor_task_id IN" in sql
    assert "task_dependencies.successor_task_id IN" in sql
    objective = Objective(id=uuid4(), department_id=department)
    readers = str(
        readers_query(objective, objective).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "colaborador" not in readers
    assert "users.is_active" in readers


def test_f9_recurrence_resume_keeps_count_and_month_anchor():
    from datetime import date

    from app.schemas.collaboration import RecurrenceRule
    from app.services.collaboration import occurrence_dates

    rule = RecurrenceRule(
        frequency="monthly",
        interval=1,
        start_date="2028-01-31",
        end_date=None,
        occurrence_count=3,
        end_policy="skip",
        non_business_policy="keep",
        missed_policy="catch_up",
    )
    rows = list(
        occurrence_dates(rule, {"weekday_mask": 31, "holidays": []}, after=date(2028, 1, 31))
    )
    assert [(row[0].isoformat(), row[2]) for row in rows] == [
        ("2028-02-29", True),
        ("2028-03-31", False),
    ]


def test_f9_template_shape_refuses_wrong_children_and_filter_injection():
    from pydantic import ValidationError

    from app.schemas.collaboration import Blueprint, SearchFilters
    from app.services.collaboration import validate_blueprint

    node = {
        "title": "Synthetic",
        "description": "",
        "horizon_type": "custom",
        "priority_id": None,
        "duration_days": 10,
        "subtasks": [],
    }
    valid = Blueprint(**node)
    assert validate_blueprint(valid, "task")["title"] == "Synthetic"
    invalid = Blueprint(**node, objectives=[node])
    with pytest.raises(CommandError):
        validate_blueprint(invalid, "task")
    with pytest.raises(ValidationError):
        SearchFilters(sql="SELECT * FROM users")


def test_f9_search_collaborator_scope_precedes_ranking_and_counting():
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.schemas.collaboration import SearchFilters
    from app.services.collaboration import saved_view_query, search_union

    user = SimpleNamespace(id=uuid4(), role="colaborador", department_id=uuid4())
    database = SimpleNamespace(info={"f8_flags": {"comments": False}})
    query = search_union(database, user, SearchFilters(q="term"))
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert "tasks.assignee_id =" in sql
    assert "to_tsvector" in sql and "ts_rank_cd" in sql
    assert "annual_plans.title" not in sql and "objectives.title" not in sql
    views = str(saved_view_query(user).compile(dialect=postgresql.dialect()))
    assert "saved_views.owner_id =" in views
    assert "saved_views.scope_kind =" not in views


def test_f9_revision_is_additive_empty_and_runtime_has_no_delete_or_truncate(monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "alembic/versions/20261125_0008_collaboration.py"
    spec = importlib.util.spec_from_file_location("f9_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    statements = []
    monkeypatch.setattr(revision.op, "execute", statements.append)
    revision.upgrade()
    assert revision.down_revision == "20261125_0007"
    assert len(revision.TABLES) == 18
    assert revision.IDENTITY.lstrip().startswith("id UUID")
    typed_guard = next(
        statement for statement in statements if "guard_f9_typed_value()" in statement
    )
    assert "IF NOT (CASE definition.data_type" in typed_guard
    assert "ELSE false END) THEN" in typed_guard
    assert not any(
        ord(character) < 32 and character not in "\r\n\t"
        for statement in statements
        for character in statement
    )
    assert not any(
        statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE "))
        for statement in statements
    )
    assert all(
        "DELETE" not in statement and "TRUNCATE" not in statement
        for statement in statements
        if statement.startswith("GRANT ")
    )
    assert all(
        f"REVOKE ALL ON {table} FROM ocote_runtime" in statements for table in revision.TABLES
    )


def test_f9_release_refuses_seeds_and_historical_changes():
    import json
    from copy import deepcopy

    from tools import f9_release

    before = {
        "tables": ["alembic_version", "historical"],
        "rows": {
            "alembic_version": [json.dumps({"version_num": f9_release.SOURCE})],
            "historical": [json.dumps({"id": "preserve", "value": "original"})],
        },
    }
    after = deepcopy(before)
    after["tables"] += list(f9_release.ADDED)
    after["rows"].update({name: [] for name in f9_release.ADDED})
    after["rows"]["alembic_version"] = [json.dumps({"version_num": f9_release.HEAD})]
    f9_release.upgraded(before, after)
    after["rows"]["tags"] = [json.dumps({"id": "unauthorized"})]
    with pytest.raises(RuntimeError, match="defaults"):
        f9_release.upgraded(before, after)
    after["rows"]["tags"] = []
    after["rows"]["historical"] = [json.dumps({"id": "preserve", "value": "modified"})]
    with pytest.raises(RuntimeError, match="Historical value"):
        f9_release.upgraded(before, after)


def test_f9_preview_rejects_missing_required_values_without_writing(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services import collaboration

    identity = uuid4()
    definition = SimpleNamespace(
        id=identity,
        data_type="boolean",
        constraints={},
        required_on_create=True,
        required_stage_ids=[],
    )
    database = SimpleNamespace(
        scalars=lambda statement: [definition], scalar=lambda statement: None
    )
    monkeypatch.setattr(collaboration, "require_module", lambda *arguments: None)
    node = SimpleNamespace(custom_fields={identity: False}, tag_ids=[])
    collaboration.validate_template_metadata(database, "task", uuid4(), node)
    node.custom_fields = {}
    with pytest.raises(CommandError) as failure:
        collaboration.validate_template_metadata(database, "task", uuid4(), node)
    assert failure.value.code == "CUSTOM_FIELD_REQUIRED"
    node.custom_fields = {identity: "false"}
    with pytest.raises(CommandError):
        collaboration.validate_template_metadata(database, "task", uuid4(), node)


def test_f9_operator_missing_storage_has_an_authorization_error(tmp_path):
    from tools import f9_local

    with pytest.raises(CommandError) as failure:
        f9_local.authorization(path=tmp_path / "absent" / "administrator.dpapi")
    assert failure.value.code == "LOCAL_AUTHORIZATION_STORAGE_UNAVAILABLE"


def test_f9_worker_identity_is_stable_bounded_and_scope_is_not_elevated():
    from datetime import date
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.services.collaboration import schedule_scope
    from tools.f9_worker import checked_budget, idempotency_key, tick

    schedule = SimpleNamespace(id=uuid4(), next_due_at=date(2027, 12, 1))
    assert idempotency_key(schedule, date(2027, 12, 20), 100) == idempotency_key(
        schedule, date(2027, 12, 20), 100
    )
    assert idempotency_key(schedule, date(2027, 12, 20), 100) != idempotency_key(
        schedule, date(2027, 12, 21), 100
    )
    assert checked_budget("100") == 100
    for budget in (True, 0, 101):
        with pytest.raises(CommandError):
            tick(None, budget)
    actor = SimpleNamespace(id=uuid4(), actor_service_id=uuid4(), role="colaborador")
    query = str(schedule_scope(actor).compile(dialect=postgresql.dialect()))
    assert "owner_user_id =" in query and "service_principal_id =" in query


def test_f9_operator_seal_context_ttl_and_no_overwrite(tmp_path):
    from tools import f8_local, f9_local

    assert f9_local.OPERATOR_CONTEXT != f8_local.OPERATOR_CONTEXT
    assert f9_local.PURPOSE != f8_local.PURPOSE
    path = tmp_path / "private-f9" / "administrator.dpapi"
    f9_local.save_authorization("synthetic-f9-test-only", path=path, issued_at=1000)
    try:
        assert (
            f9_local.authorized_password(path=path, current_time=4599) == "synthetic-f9-test-only"
        )
        for moment in (999, 4600, float("nan"), True):
            with pytest.raises(CommandError):
                f9_local.authorized_password(path=path, current_time=moment)
        with pytest.raises(CommandError):
            f9_local.save_authorization("synthetic-f9-test-only", path=path, issued_at=1001)
    finally:
        path.unlink(missing_ok=True)


def test_f9_pg_runner_revokes_after_failure_and_redacts(monkeypatch, capsys):
    from types import SimpleNamespace

    from tools import f9_local

    revoked = []
    monkeypatch.setattr(
        f9_local,
        "authorization",
        lambda: {
            "password": "synthetic-secret-f9",
            "expires_at": f9_local.time.time() + 60,
        },
    )
    monkeypatch.setattr(f9_local, "revoke", lambda: revoked.append(True))
    monkeypatch.setattr(
        f9_local.subprocess,
        "run",
        lambda *arguments, **options: SimpleNamespace(
            stdout="failure synthetic-secret-f9",
            stderr="synthetic-secret-f9",
            returncode=1,
        ),
    )
    assert f9_local.run_pg_tests("f9") == 1
    output = capsys.readouterr()
    assert "synthetic-secret-f9" not in output.out + output.err
    assert revoked == [True]


@pytest.mark.parametrize("failed_stage", [0, 1, None])
def test_f9_final_runner_never_releases_before_all_pg_gates_and_always_revokes(
    monkeypatch, failed_stage, tmp_path
):
    from tools import f9_local

    calls = []
    monkeypatch.setattr(
        f9_local,
        "authorization",
        lambda: {"password": "synthetic", "expires_at": f9_local.time.time() + 1800},
    )

    def run(arguments, payload):
        calls.append(arguments)
        return int(failed_stage is not None and len(calls) - 1 == failed_stage)

    monkeypatch.setattr(f9_local, "run_authorized", run)
    drained, revoked = [], []
    monkeypatch.setattr(f9_local, "drain_api", lambda: drained.append(True))
    monkeypatch.setattr(f9_local, "revoke", lambda: revoked.append(True))
    assert f9_local.run_final_gates(tmp_path / "private-final") == int(failed_stage is not None)
    assert len(calls) == (3 if failed_stage is None else failed_stage + 1)
    assert drained == ([True] if failed_stage is None else [])
    assert revoked == [True]
    assert calls[0][-2].endswith("upgrade_from0007_noop_empty_and_preserves")


@pytest.mark.parametrize(
    "case", ["ok", "absent", "wildcard", "ipv6", "multiple", "foreign", "race", "still_listening"]
)
def test_f9_native_drain_validates_owner_and_rechecks_listener(monkeypatch, case):
    from tools import f9_local

    baseline = [("127.0.0.1", 12345)]
    initial = {
        "absent": [],
        "wildcard": [("0.0.0.0", 12345)],
        "ipv6": [("::1", 12345)],
        "multiple": baseline + [("127.0.0.1", 67890)],
    }.get(case, baseline)
    calls, stopped = [], []

    def listeners():
        calls.append(True)
        if len(calls) == 1:
            return initial
        if case == "race":
            return [("127.0.0.1", 67890)]
        return baseline if len(calls) == 2 or case == "still_listening" else []

    class Process:
        def __init__(self, pid):
            assert pid == 12345

        def __enter__(self):
            return self

        def __exit__(self, *_error):
            pass

        def verified(self):
            return case != "foreign"

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(f9_local, "api_listeners", listeners)
    monkeypatch.setattr(f9_local, "APIProcess", Process)
    if case in {"ok", "absent"}:
        f9_local.drain_api()
    else:
        with pytest.raises(CommandError, match="API_DRAIN_NOT_VERIFIED"):
            f9_local.drain_api()
    assert stopped == ([True] if case in {"ok", "still_listening"} else [])


def test_f9_native_owner_requires_workspace_python_and_application():
    from tools import f9_local

    python = str(f9_local.BACKEND_DIR / ".venv/Scripts/python.exe")
    command = python + " -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    assert f9_local.api_owner_matches(python, command)
    assert not f9_local.api_owner_matches("C:/unrelated/python.exe", "uvicorn app.main:app")
    assert not f9_local.api_owner_matches(python, command.replace("app.main:app", "other:app"))
    assert not f9_local.api_owner_matches(python.replace("python.exe", "other.exe"), command)
    factory = "python -m uvicorn app.main:create_app --factory --app-dir backend"
    workspace = str(f9_local.BACKEND_DIR.parent)
    assert f9_local.api_owner_matches("C:/Python/python.exe", factory, workspace)
    assert not f9_local.api_owner_matches("C:/Python/python.exe", factory, "C:/unrelated")
    assert not f9_local.api_owner_matches(
        "C:/Python/python.exe", factory.replace(" --factory", ""), workspace
    )


@pytest.mark.skipif(os.environ.get("OCOTE_RUN_PG_TESTS") != "1", reason="Explicit isolated PG gate")
def test_f9_postgres_upgrade_from0007_noop_empty_and_preserves():
    from uuid import uuid4

    from sqlalchemy import MetaData, Table, func, inspect, select, text

    from app.models import collaboration
    from tools.f2_local import isolated_database, migration_engine, upgrade

    with isolated_database() as name:
        upgrade(name, "20261125_0007")
        engine = migration_engine(name)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO departments(id,code,name) VALUES"
                        "(:id,'f9_preserve','Synthetic UUID-only preservation')"
                    ),
                    {"id": uuid4()},
                )
            with engine.connect() as connection:
                names = inspect(connection).get_table_names(schema="public")
                previous = {
                    table: Table(table, MetaData(), autoload_with=connection)
                    for table in names
                    if table != "alembic_version"
                }
                before = {
                    name: list(connection.execute(select(table)).tuples())
                    for name, table in previous.items()
                }
            upgrade(name, "20261125_0008")
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "20261125_0008"
                )
                for table_name, table in previous.items():
                    assert list(connection.execute(select(table)).tuples()) == before[table_name]
                installed = inspect(connection).get_table_names(schema="public")
                assert len(installed) == 50
                for model in vars(collaboration).values():
                    if (
                        isinstance(model, type)
                        and model.__module__ == collaboration.__name__
                        and hasattr(model, "__table__")
                    ):
                        assert connection.scalar(select(func.count()).select_from(model)) == 0
                first = connection.execute(
                    text(
                        "SELECT table_name,column_name,data_type "
                        "FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2"
                    )
                )
                signature = list(first)
            upgrade(name, "20261125_0008")
            with engine.connect() as connection:
                assert (
                    list(
                        connection.execute(
                            text(
                                "SELECT table_name,column_name,data_type "
                                "FROM information_schema.columns "
                                "WHERE table_schema='public' ORDER BY 1,2"
                            )
                        )
                    )
                    == signature
                )
        finally:
            engine.dispose()


def test_f9_postgres_triggers_constraints_and_privileges(core):
    from types import SimpleNamespace
    from uuid import UUID, uuid4

    from sqlalchemy import select, text
    from sqlalchemy.exc import DBAPIError

    from app.models.collaboration import Comment, CommentRevision, TaskDependency, TaskImpediment
    from app.models.identity import User
    from app.services.operations import administrative_event, bump

    client, factory, first, _, objective, person, terminal = core
    second = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": objective["id"],
            "assignee_id": person["id"],
            "title": "Synthetic F9 successor",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert second.status_code == 201, second.text
    first_id, second_id = UUID(first["id"]), UUID(second.json()["id"])
    with factory() as db:
        actor = db.scalar(select(User).where(User.role == "admin"))
        request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))

        def persist(record):
            db.add(record)
            db.flush()
            administrative_event(db, request, actor, record, {}, "f9_isolated_probe")
            db.flush()
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            db.execute(text("SET CONSTRAINTS ALL DEFERRED"))

        edge = TaskDependency(
            predecessor_task_id=first_id,
            successor_task_id=second_id,
            created_by=actor.id,
            active=True,
        )
        persist(edge)
        for predecessor, successor in (
            (second_id, first_id),
            (first_id, first_id),
            (first_id, second_id),
        ):
            with pytest.raises(DBAPIError):
                with db.begin_nested():
                    db.add(
                        TaskDependency(
                            predecessor_task_id=predecessor,
                            successor_task_id=successor,
                            created_by=actor.id,
                            active=True,
                        )
                    )
                    db.flush()
        with pytest.raises(DBAPIError, match="PENDING_PREDECESSORS"):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE tasks SET completed_at=clock_timestamp(),stage_id=:stage,"
                        "version=version+1,updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"stage": terminal, "id": second_id},
                )
        edge.active = False
        bump(db, edge)
        persist(edge)
        impediment = TaskImpediment(
            task_id=first_id,
            owner_user_id=UUID(person["id"]),
            reason="Synthetic isolated blocking reason",
            severity="high",
            kind="internal",
            opened_at=datetime.now(UTC),
        )
        persist(impediment)
        with pytest.raises(DBAPIError, match="OPEN_IMPEDIMENTS"):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE tasks SET completed_at=clock_timestamp(),stage_id=:stage,"
                        "version=version+1,updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"stage": terminal, "id": first_id},
                )
        impediment.closed_at = datetime.now(UTC)
        impediment.resolution = "Synthetic isolated resolution"
        bump(db, impediment)
        persist(impediment)
        parent = None
        for depth in range(5):
            comment = Comment(
                task_id=first_id, author_id=actor.id, parent_comment_id=parent, current_revision=1
            )
            db.add(comment)
            db.flush()
            db.add(
                CommentRevision(
                    comment_id=comment.id,
                    author_id=actor.id,
                    revision_no=1,
                    body="Synthetic depth " + str(depth + 1),
                    reason="Synthetic isolated comment",
                    annulment=False,
                )
            )
            persist(comment)
            parent = comment.id
        for resource in (first_id, second_id):
            with pytest.raises(DBAPIError, match="COMMENT_DEPTH_OR_RESOURCE"):
                with db.begin_nested():
                    db.add(
                        Comment(
                            task_id=resource,
                            author_id=actor.id,
                            parent_comment_id=parent,
                            current_revision=1,
                        )
                    )
                    db.flush()
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text("UPDATE task_dependencies SET version=version+2 WHERE id=:id"),
                    {"id": edge.id},
                )
        for table in (
            "task_dependencies",
            "comments",
            "comment_revisions",
            "custom_field_values",
            "recurrence_occurrences",
            "service_principals",
            "transactional_outbox",
        ):
            assert db.scalar(
                text("SELECT has_table_privilege(current_user,:table,'SELECT,INSERT')"),
                {"table": table},
            )
            assert not db.scalar(
                text("SELECT has_table_privilege(current_user,:table,'DELETE,TRUNCATE,TRIGGER')"),
                {"table": table},
            )
        db.rollback()
