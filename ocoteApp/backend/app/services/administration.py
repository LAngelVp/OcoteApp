from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text

from app.core.errors import CommandError
from app.core.security import PASSWORDS
from app.models.identity import (
    Department,
    HorizonType,
    Priority,
    SystemSetting,
    User,
    WorkflowStage,
    WorkflowTransition,
)
from app.services.identity import audit, revoke, touch, user_view

HORIZONS = {"annual", "semiannual", "quarterly", "monthly", "custom"}
SETTING_KEYS = {
    "organization_name",
    "organization_timezone",
    "evidence_max_bytes",
    "export_max_rows",
}


def project(record):
    if isinstance(record, User):
        return {
            **user_view(record),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
    fields = {
        "id",
        "created_at",
        "updated_at",
        "version",
        "code",
        "name",
        "is_active",
        "position",
        "kind",
        "is_initial",
        "requires_evidence",
        "requires_reason",
        "from_stage_id",
        "to_stage_id",
        "allowed_roles",
        "key",
        "value",
        "updated_by",
    }
    return {
        name: getattr(record, name) for name in record.__table__.columns.keys() if name in fields
    }


def get_record(db, model, identity):
    record = db.scalar(select(model).where(model.id == identity).with_for_update())
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def check_version(record, expected):
    if record.version != expected:
        raise CommandError(409, "VERSION_CONFLICT")


def department_for_user(db, role, department_id):
    if department_id is None:
        if role not in {"admin", "gerente"}:
            raise CommandError(422, "DEPARTMENT_REQUIRED")
    else:
        department = db.get(Department, department_id)
        if department is None or not department.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")


def has_rows(db, table):
    if table not in {"tasks", "evaluations", "objectives", "annual_plans"}:
        raise ValueError("Invalid temporal boundary")
    if db.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + table}) is None:
        return False
    return bool(db.scalar(text(f"SELECT EXISTS(SELECT 1 FROM public.{table})")))


def validate_setting(key, value):
    if key not in SETTING_KEYS:
        raise CommandError(403, "SETTING_NOT_EDITABLE")
    if key in {"organization_name", "organization_timezone"}:
        maximum = 160 if key == "organization_name" else 100
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
            raise CommandError(422, "INVALID_SETTING")
        if key == "organization_timezone":
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise CommandError(422, "INVALID_SETTING") from None
    elif type(value) is not int or not 1 <= value <= (
        10485760 if key == "evidence_max_bytes" else 10000
    ):
        raise CommandError(422, "INVALID_SETTING")


def check_roles(roles, active):
    if len(roles) != len(set(roles)) or set(roles) - {"admin", "lider", "colaborador"}:
        raise CommandError(422, "INVALID_TRANSITION_ROLES")
    if not roles or (active and "admin" not in roles):
        raise CommandError(422, "INVALID_TRANSITION_ROLES")


def validate_graph(stages, edges, *, allow_empty=False):
    active = {stage.id: stage for stage in stages if stage.is_active}
    if not active and allow_empty:
        return
    initial = [stage for stage in active.values() if stage.is_initial]
    terminal = [stage for stage in active.values() if stage.kind == "completed"]
    if len(initial) != 1 or len(terminal) != 1:
        raise CommandError(409, "WORKFLOW_INCOMPLETE")
    if initial[0].kind != "open" or initial[0].requires_evidence or initial[0].requires_reason:
        raise CommandError(422, "INVALID_INITIAL_STAGE")
    parents = {identity: set() for identity in active}
    all_stages = {stage.id: stage for stage in stages}
    for edge in edges:
        check_roles(edge.allowed_roles, edge.is_active)
        if edge.from_stage_id == edge.to_stage_id:
            raise CommandError(422, "INVALID_TRANSITION")
        if all_stages[edge.from_stage_id].kind == "completed":
            raise CommandError(422, "TERMINAL_HAS_NO_EXIT")
        if edge.is_active:
            if edge.from_stage_id not in active or edge.to_stage_id not in active:
                raise CommandError(409, "INACTIVE_STAGE")
            parents[edge.to_stage_id].add(edge.from_stage_id)
    reachable, pending = {terminal[0].id}, [terminal[0].id]
    while pending:
        for parent in parents[pending.pop()]:
            if parent not in reachable:
                reachable.add(parent)
                pending.append(parent)
    if reachable != set(active):
        raise CommandError(409, "WORKFLOW_HAS_NO_TERMINAL_PATH")


def validate_workflow(db, *, allow_empty=False):
    db.flush()
    validate_graph(
        list(db.scalars(select(WorkflowStage))),
        list(db.scalars(select(WorkflowTransition))),
        allow_empty=allow_empty,
    )


def validate_record(db, record):
    if isinstance(record, User):
        department_for_user(db, record.role, record.department_id)
    elif isinstance(record, HorizonType):
        if record.code not in HORIZONS:
            raise CommandError(422, "INVALID_HORIZON")
        if record.code == "custom" and not record.is_active:
            raise CommandError(409, "PROTECTED_CATALOG_ENTRY")
    elif isinstance(record, Priority) and record.code == "normal" and not record.is_active:
        raise CommandError(409, "PROTECTED_CATALOG_ENTRY")
    elif isinstance(record, WorkflowStage):
        if (record.is_initial or record.kind == "completed") and not record.is_active:
            raise CommandError(409, "PROTECTED_STAGE")
        if (
            not record.is_active
            and has_rows(db, "tasks")
            and db.scalar(
                text("SELECT EXISTS(SELECT 1 FROM tasks WHERE stage_id=:id)"), {"id": record.id}
            )
        ):
            raise CommandError(409, "OCCUPIED_STAGE")
        if record.is_initial and (
            record.kind != "open" or record.requires_reason or record.requires_evidence
        ):
            raise CommandError(422, "INVALID_INITIAL_STAGE")
    elif isinstance(record, WorkflowTransition):
        check_roles(record.allowed_roles, record.is_active)
        source, target = (
            db.get(WorkflowStage, record.from_stage_id),
            db.get(WorkflowStage, record.to_stage_id),
        )
        if not source or not target or source.id == target.id or source.kind == "completed":
            raise CommandError(422, "INVALID_TRANSITION")
        if record.is_active and (not source.is_active or not target.is_active):
            raise CommandError(422, "INACTIVE_STAGE")


def audit_change(db, request, actor, record, before, reason):
    after = project(record)
    if isinstance(record, User):
        before = {
            key: value for key, value in before.items() if key not in {"email", "display_name"}
        }
        after = {key: value for key, value in after.items() if key not in {"email", "display_name"}}
    from fastapi.encoders import jsonable_encoder

    audit(
        db,
        request,
        "administration_changed",
        actor=actor.id,
        entity=record.__tablename__,
        entity_id=record.id,
        before=jsonable_encoder(before),
        after=jsonable_encoder({**after, "reason": reason}),
    )


def create_record(db, model, body, actor, request):
    values = body.model_dump(exclude={"reason", "password"})
    if model is User:
        values["password_hash"] = PASSWORDS.hash(body.password.get_secret_value())
    record = model(**values)
    validate_record(db, record)
    db.add(record)
    db.flush()
    if model in {WorkflowStage, WorkflowTransition}:
        validate_workflow(db, allow_empty=True)
    audit_change(db, request, actor, record, {}, body.reason)
    return project(record)


def update_record(db, model, identity, body, actor, request):
    record = get_record(db, model, identity)
    check_version(record, body.expected_version)
    before = project(record)
    if isinstance(record, Department) and not body.is_active:
        if db.scalar(
            select(User.id).where(User.department_id == record.id, User.is_active).limit(1)
        ):
            raise CommandError(409, "DEPARTMENT_HAS_ACTIVE_USERS")
        if has_rows(db, "objectives") and db.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM objectives ob JOIN annual_plans ap "
                "ON ap.id=ob.annual_plan_id WHERE ob.department_id=:id AND ap.status <> 'closed')"
            ),
            {"id": record.id},
        ):
            raise CommandError(409, "DEPENDENCY_CONFLICT")
    if isinstance(record, User):
        security_changed = any(
            getattr(record, field) != getattr(body, field)
            for field in ("role", "department_id", "is_active")
        )
        if (
            record.role == "admin"
            and record.is_active
            and (body.role != "admin" or not body.is_active)
        ):
            if (
                db.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == "admin", User.is_active)
                )
                <= 1
            ):
                raise CommandError(409, "LAST_ACTIVE_ADMIN")
        if security_changed:
            if has_rows(db, "tasks") and db.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM tasks "
                    "WHERE assignee_id=:id AND completed_at IS NULL)"
                ),
                {"id": record.id},
            ):
                raise CommandError(409, "USER_HAS_OPEN_TASKS")
            record.token_version += 1
    for field, value in body.model_dump(exclude={"reason", "expected_version"}).items():
        setattr(record, field, value)
    touch(record)
    validate_record(db, record)
    if isinstance(record, User) and security_changed:
        revoke(db, user_id=record.id)
    db.flush()
    if model in {WorkflowStage, WorkflowTransition}:
        validate_workflow(db, allow_empty=True)
    audit_change(db, request, actor, record, before, body.reason)
    return project(record)


def reorder_catalog(db, model, body, actor, request):
    if model not in {Priority, HorizonType}:
        raise ValueError("Invalid catalog")
    if len({entry.id for entry in body.items}) != len(body.items) or len(
        {entry.position for entry in body.items}
    ) != len(body.items):
        raise CommandError(422, "INVALID_CATALOG_ORDER")
    records = [get_record(db, model, entry.id) for entry in body.items]
    for record, entry in zip(records, body.items, strict=True):
        check_version(record, entry.expected_version)
    for record, entry in zip(records, body.items, strict=True):
        before = project(record)
        record.position = entry.position
        touch(record)
        audit_change(db, request, actor, record, before, body.reason)
    db.flush()
    return {"items": [project(record) for record in records]}


def configure_workflow(db, body, actor, request):
    existing = {stage.code: stage for stage in db.scalars(select(WorkflowStage))}
    codes = [stage.code for stage in body.stages]
    if len(codes) != len(set(codes)) or set(existing) - set(codes):
        raise CommandError(409, "WORKFLOW_CONFLICT")
    stages = {}
    for entry in body.stages:
        stage = existing.get(entry.code)
        if stage is None:
            if entry.expected_version is not None:
                raise CommandError(409, "VERSION_CONFLICT")
            stage = WorkflowStage(
                id=uuid4(), **entry.model_dump(exclude={"reason", "expected_version"})
            )
            db.add(stage)
        else:
            check_version(stage, entry.expected_version)
            if stage.kind != entry.kind or stage.is_initial != entry.is_initial:
                raise CommandError(409, "IMMUTABLE_WORKFLOW_SEMANTICS")
            for field, value in entry.model_dump(
                exclude={"reason", "expected_version", "code", "kind", "is_initial"}
            ).items():
                setattr(stage, field, value)
            touch(stage)
        validate_record(db, stage)
        stages[entry.code] = stage
    db.flush()
    old_edges = {
        (edge.from_stage_id, edge.to_stage_id): edge
        for edge in db.scalars(select(WorkflowTransition))
    }
    seen = set()
    for entry in body.transitions:
        if entry.from_code not in stages or entry.to_code not in stages:
            raise CommandError(422, "INVALID_TRANSITION")
        pair = stages[entry.from_code].id, stages[entry.to_code].id
        if pair in seen:
            raise CommandError(409, "DUPLICATE_TRANSITION")
        seen.add(pair)
        edge = old_edges.get(pair)
        if edge is None:
            if entry.expected_version is not None:
                raise CommandError(409, "VERSION_CONFLICT")
            edge = WorkflowTransition(
                from_stage_id=pair[0],
                to_stage_id=pair[1],
                allowed_roles=entry.allowed_roles,
                is_active=entry.is_active,
            )
            db.add(edge)
        else:
            check_version(edge, entry.expected_version)
            edge.allowed_roles, edge.is_active = entry.allowed_roles, entry.is_active
            touch(edge)
        validate_record(db, edge)
    if set(old_edges) - seen:
        raise CommandError(409, "WORKFLOW_CONFLICT")
    validate_workflow(db)
    audit(
        db,
        request,
        "administration_changed",
        actor=actor.id,
        entity="workflow",
        after={"reason": body.reason, "stages": len(stages), "transitions": len(seen)},
    )
    return {
        "stages": [project(stage) for stage in stages.values()],
        "transitions": [project(edge) for edge in db.scalars(select(WorkflowTransition))],
    }


def create_setting(db, body, actor, request):
    validate_setting(body.key, body.value)
    record = SystemSetting(key=body.key, value=body.value, updated_by=actor.id)
    db.add(record)
    db.flush()
    audit_change(db, request, actor, record, {}, body.reason)
    return project(record)


def update_setting(db, key, body, actor, request):
    validate_setting(key, body.value)
    record = db.scalar(select(SystemSetting).where(SystemSetting.key == key).with_for_update())
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if key == "organization_timezone" and (has_rows(db, "tasks") or has_rows(db, "evaluations")):
        raise CommandError(409, "TIMEZONE_LOCKED")
    before = project(record)
    record.value, record.updated_by = body.value, actor.id
    touch(record)
    db.flush()
    audit_change(db, request, actor, record, before, body.reason)
    return project(record)
