from uuid import UUID, uuid4

from app.core.errors import CommandError
from app.core.evidence import validate_content
from app.models.operations import EvidenceFile, Task
from app.services import operations as service
from app.services.administration import check_version
from app.services.identity import audit


def store(request, db, *, department_id=None, captured=None, historical=False):
    from app.services.object_integrations import configured_store

    return getattr(request.app.state, "evidence_store", None) or configured_store(
        db, request, department_id=department_id, captured=captured, historical=historical
    )


def view(record):
    return {
        field: getattr(record, field)
        for field in (
            "id",
            "created_at",
            "task_id",
            "uploaded_by",
            "original_name",
            "media_type",
            "size_bytes",
            "sha256",
        )
    }


def attach(db, user, identity, expected_version, content, name, media_type, request):
    service.permit(user, "admin", "lider", "colaborador")
    settings = service.configuration(db)
    plan, objective, task, _ = service.task_context(db, user, identity)
    service.open_task(plan, task)
    check_version(task, expected_version)
    validate_content(content, name, media_type, settings["evidence_max_bytes"])
    storage = store(request, db, department_id=objective.department_id)
    if hasattr(storage, "allowed_mime") and media_type not in storage.allowed_mime:
        raise CommandError(415, "INVALID_EVIDENCE_TYPE")
    key, digest, scan_version = storage.publish(content)
    db.info.setdefault("rollback_files", []).append(storage.path(key))
    record = EvidenceFile(
        id=uuid4(),
        task_id=task.id,
        uploaded_by=user.id,
        original_name=name,
        storage_key=key,
        storage_config_id=getattr(storage, "configuration_id", None),
        storage_config_version=getattr(storage, "configuration_version", None),
        media_type=media_type,
        size_bytes=len(content),
        sha256=digest,
        scan_engine="clamav",
        scan_version=scan_version,
        scanned_at=service.instant(db),
    )
    before = service.state(task)
    db.add(record)
    service.bump(db, task)
    db.flush()
    from app.models.operations import TaskHistory

    db.add(
        TaskHistory(
            task_id=task.id,
            actor_id=user.id,
            event_type="evidence_added",
            before_data={"version": before["version"]},
            after_data={
                "evidence_id": str(record.id),
                "version": task.version,
                "sha256": digest,
                "size_bytes": len(content),
            },
            request_id=UUID(request.state.request_id),
        )
    )
    audit(
        db,
        request,
        "administration_changed",
        actor=user.id,
        entity="evidence_files",
        entity_id=record.id,
        after={"task_id": str(task.id), "sha256": digest, "command": "evidence_added"},
    )
    db.flush()
    return {"evidence": view(record), "task": service.task_view(db, task, user)}


def available(db, user, identity, request, task_id=None):
    record = db.get(EvidenceFile, identity)
    if record is None or (task_id is not None and record.task_id != task_id):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    service.visible(db, Task, record.task_id, user)
    path = store(request, db, captured=record.storage_config_id, historical=True).available(
        record.storage_key, record.size_bytes, record.sha256
    )
    return record, path
