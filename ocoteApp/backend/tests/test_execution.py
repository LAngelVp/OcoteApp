from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from test_evidence import PDF, version
from test_identity import api as api
from test_identity import create_person, person_client
from test_identity import tokens as tokens
from test_operations import command
from test_operations import core as core

from app.core.errors import CommandError
from app.core.evidence import EvidenceStore
from app.models.operations import EvidenceFile, Task
from tools.f1_local import private_directory


@pytest.fixture
def execution(core, tmp_path):
    client, factory, task, plan, objective, person, terminal = core
    private_directory(tmp_path)
    for name in ("quarantine", "objects"):
        private_directory(tmp_path / name)
    client.app.state.evidence_store = EvidenceStore(tmp_path, lambda content: version())
    yield client, factory, task, terminal, tmp_path, person


def upload(
    client, task, content=PDF, version_number=None, name="synthetic.pdf", media="application/pdf"
):
    return client.post(
        "/api/v1/tasks/" + task["id"] + "/evidence",
        params={"expected_version": version_number or task["version"]},
        headers={"Content-Type": media, "X-File-Name": name},
        content=content,
    )


def test_real_f5_upload_download_transition_history_and_immutability(execution):
    client, factory, task, terminal, root, _ = execution
    stage = next(
        row
        for row in client.get("/api/v1/workflow-stages").json()["items"]
        if row["id"] == terminal
    )
    patch = {key: stage[key] for key in ("name", "position", "is_active", "requires_reason")}
    patch.update(
        requires_evidence=True,
        expected_version=stage["version"],
        reason="Synthetic evidence requirement",
    )
    response = client.patch("/api/v1/workflow-stages/" + terminal, json=patch)
    assert response.status_code == 200, response.text
    command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"expected_version": 1, "to_stage_id": terminal},
        422,
    )
    response = upload(client, task)
    assert response.status_code == 201, response.text
    result = response.json()
    evidence, updated = result["evidence"], result["task"]
    assert updated["version"] == 2 and updated["original_due_date"] == task["original_due_date"]
    assert "storage_key" not in response.text and "scan_version" not in response.text
    assert upload(client, task).status_code == 409
    assert len(list((root / "objects").iterdir())) == 1
    listed = client.get("/api/v1/tasks/" + task["id"] + "/evidence").json()
    assert listed["items"][0]["id"] == evidence["id"]
    content = client.get("/api/v1/evidence/" + evidence["id"] + "/content")
    assert content.content == PDF and content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["content-disposition"].startswith("attachment")
    closed = command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"expected_version": 2, "to_stage_id": terminal, "evidence_ids": [evidence["id"]]},
    )
    assert closed["completed_at"] and upload(client, closed).status_code == 409
    history = client.get("/api/v1/tasks/" + task["id"] + "/history").json()["items"]
    moved = next(row for row in history if row["event_type"] == "stage_changed")
    assert moved["after_data"]["evidence_ids"] == [evidence["id"]]
    assert moved["after_data"]["stage_rules"]["requires_evidence"] is True
    assert client.delete("/api/v1/evidence/" + evidence["id"] + "/content").status_code == 405
    with pytest.raises(DBAPIError), factory.begin() as db:
        db.execute(text("DELETE FROM evidence_files"))


def test_real_f5_upload_failure_leaves_no_rows_versions_or_files(execution):
    client, factory, task, _, root, _ = execution
    assert upload(client, task, PDF * 100).status_code == 413
    assert upload(client, task, b"<html/>").status_code == 415

    def infected(content):
        raise CommandError(422, "MALWARE_DETECTED")

    client.app.state.evidence_store.scanner = infected
    assert upload(client, task).status_code == 422

    def unknown(content):
        raise CommandError(503, "EVIDENCE_STORAGE_OR_SCANNER_UNAVAILABLE")

    client.app.state.evidence_store.scanner = unknown
    response = upload(client, task)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["request_id"] and str(root) not in response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvidenceFile)) == 0
        assert db.get(Task, task["id"]).version == 1
    assert list((root / "objects").iterdir()) == []
    assert list((root / "quarantine").iterdir()) == []


def test_real_f5_commit_failure_compensates_file_and_version(execution):
    client, factory, task, _, root, _ = execution

    def fail_commit(db):
        if db.info.get("rollback_files"):
            raise RuntimeError("Synthetic commit failure")

    event.listen(factory.class_, "before_commit", fail_commit)
    try:
        assert upload(client, task).status_code == 500
    finally:
        event.remove(factory.class_, "before_commit", fail_commit)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EvidenceFile)) == 0
        assert db.get(Task, task["id"]).version == 1
    assert list((root / "objects").iterdir()) == []


def test_real_f5_role_scope_and_foreign_evidence_are_closed(execution):
    client, _, task, terminal, _, person = execution
    own = upload(client, task)
    assert own.status_code == 201, own.text
    evidence = own.json()["evidence"]
    create_person(client, role="gerente", email="manager@example.invalid")
    create_person(client, department=person["department_id"], email="other@example.invalid")
    with person_client(client, "manager@example.invalid") as manager:
        assert upload(manager, task).status_code == 403
        assert manager.get("/api/v1/evidence/" + evidence["id"] + "/content").status_code == 200
    with person_client(client, "other@example.invalid") as other:
        assert other.get("/api/v1/evidence/" + evidence["id"] + "/content").status_code == 404
        assert other.get("/api/v1/tasks/" + task["id"] + "/evidence").status_code == 404
        assert other.get("/api/v1/kanban").json()["columns"][0]["count"] == 0
        assert other.get("/api/v1/timeline", params={"kind": "task"}).json()["items"] == []
        assert other.get("/api/v1/timeline", params={"kind": "plan"}).status_code == 403
    command(
        client,
        "tasks/" + task["id"] + "/stage-transitions",
        {"expected_version": 2, "to_stage_id": terminal, "evidence_ids": [str(uuid4())]},
        404,
    )


def test_real_f5_kanban_and_timeline_share_scope_filters_and_originals(execution):
    client, _, task, _, _, _ = execution
    board = client.get("/api/v1/kanban", params={"limit": 1}).json()
    assert len(board["columns"]) == 2
    assert sorted(column["count"] for column in board["columns"]) == [0, 1]
    assert sum(len(column["items"]) for column in board["columns"]) == 1
    for kind in ("plan", "objective", "task"):
        response = client.get("/api/v1/timeline", params={"kind": kind})
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == 1
    items = client.get("/api/v1/timeline", params={"kind": "task"}).json()["items"]
    assert items[0]["original_due_date"] == task["original_due_date"]
    assert (
        client.get("/api/v1/kanban", params={"assignee_id": str(uuid4())}).json()["columns"][0][
            "count"
        ]
        == 0
    )
