from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, text

from app.core.errors import CommandError
from app.core.security import PASSWORDS
from app.models.identity import (
    AuditEvent,
    Department,
    HorizonType,
    Priority,
    SystemSetting,
    User,
    WorkflowStage,
    WorkflowTransition,
)
from app.schemas.identity import (
    CatalogCreate,
    CatalogReorder,
    CatalogUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    PasswordReset,
    SettingCreate,
    SettingUpdate,
    StageCreate,
    StageUpdate,
    TransitionCreate,
    TransitionUpdate,
    UserCreate,
    UserUpdate,
    WorkflowInput,
)
from app.services import administration as service
from app.services.identity import (
    Administrator,
    CurrentUser,
    Database,
    audit,
    revoke,
    touch,
)

router = APIRouter(prefix="/api/v1", tags=["administration"])


def crud(path, model, create_schema, update_schema):
    def listing(
        actor: Administrator,
        db: Database,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: UUID | None = None,
    ):
        query = select(model).order_by(model.id).limit(limit + 1)
        if cursor:
            query = query.where(model.id > cursor)
        records = list(db.scalars(query))
        return {
            "items": [service.project(record) for record in records[:limit]],
            "next_cursor": records[limit - 1].id if len(records) > limit else None,
        }

    def detail(identity: UUID, actor: Administrator, db: Database):
        record = db.get(model, identity)
        if record is None:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        return service.project(record)

    def create(body: create_schema, request: Request, actor: Administrator, db: Database):
        return service.create_record(db, model, body, actor, request)

    def update(
        identity: UUID, body: update_schema, request: Request, actor: Administrator, db: Database
    ):
        return service.update_record(db, model, identity, body, actor, request)

    router.add_api_route(path, listing, methods=["GET"], name=model.__tablename__ + "_list")
    router.add_api_route(
        path + "/{identity}", detail, methods=["GET"], name=model.__tablename__ + "_detail"
    )
    router.add_api_route(
        path, create, methods=["POST"], status_code=201, name=model.__tablename__ + "_create"
    )
    router.add_api_route(
        path + "/{identity}", update, methods=["PATCH"], name=model.__tablename__ + "_update"
    )


crud("/departments", Department, DepartmentCreate, DepartmentUpdate)
crud("/users", User, UserCreate, UserUpdate)
crud("/priorities", Priority, CatalogCreate, CatalogUpdate)
crud("/horizon-types", HorizonType, CatalogCreate, CatalogUpdate)
crud("/workflow-stages", WorkflowStage, StageCreate, StageUpdate)
crud("/workflow-transitions", WorkflowTransition, TransitionCreate, TransitionUpdate)


@router.post("/priorities/reorder")
def reorder_priorities(body: CatalogReorder, request: Request, actor: Administrator, db: Database):
    return service.reorder_catalog(db, Priority, body, actor, request)


@router.post("/horizon-types/reorder")
def reorder_horizons(body: CatalogReorder, request: Request, actor: Administrator, db: Database):
    return service.reorder_catalog(db, HorizonType, body, actor, request)


@router.post("/workflow", status_code=201)
def workflow(body: WorkflowInput, request: Request, actor: Administrator, db: Database):
    return service.configure_workflow(db, body, actor, request)


@router.get("/settings")
def settings(actor: Administrator, db: Database):
    return {
        "items": [
            service.project(record)
            for record in db.scalars(select(SystemSetting).order_by(SystemSetting.key))
        ]
    }


@router.get("/settings/{key}")
def setting(key: str, actor: Administrator, db: Database):
    if key not in service.SETTING_KEYS:
        raise CommandError(403, "SETTING_NOT_EDITABLE")
    record = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return service.project(record)


@router.post("/settings", status_code=201)
def create_setting(body: SettingCreate, request: Request, actor: Administrator, db: Database):
    return service.create_setting(db, body, actor, request)


@router.patch("/settings/{key}")
def update_setting(
    key: str, body: SettingUpdate, request: Request, actor: Administrator, db: Database
):
    return service.update_setting(db, key, body, actor, request)


@router.post("/users/{identity}/reset-password", status_code=204)
def reset_password(
    identity: UUID, body: PasswordReset, request: Request, actor: Administrator, db: Database
):
    record = service.get_record(db, User, identity)
    service.check_version(record, body.expected_version)
    record.password_hash = PASSWORDS.hash(body.new_password.get_secret_value())
    record.token_version += 1
    touch(record)
    revoke(db, user_id=record.id)
    audit(db, request, "password_changed", actor=actor.id, entity="users", entity_id=record.id)


@router.get("/catalogs/departments")
def departments(user: CurrentUser, db: Database):
    query = select(Department).where(Department.is_active).order_by(Department.code).limit(100)
    if user.role in {"lider", "colaborador"}:
        query = query.where(Department.id == user.department_id)
    return {
        "items": [
            {"id": record.id, "code": record.code, "name": record.name}
            for record in db.scalars(query)
        ]
    }


@router.get("/catalogs/assignees")
def assignees(user: CurrentUser, db: Database, department_id: UUID | None = None):
    query = (
        select(User)
        .join(Department, Department.id == User.department_id)
        .where(User.is_active, Department.is_active, User.role != "gerente")
        .order_by(User.id)
        .limit(100)
    )
    if user.role in {"lider", "colaborador"}:
        if department_id is not None and department_id != user.department_id:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        query = query.where(User.department_id == user.department_id)
    if user.role == "colaborador":
        query = query.where(User.id == user.id)
    if department_id is not None:
        query = query.where(User.department_id == department_id)
    return {
        "items": [
            {
                "id": record.id,
                "display_name": record.display_name,
                "department_id": record.department_id,
            }
            for record in db.scalars(query)
        ]
    }


def catalog(model, user, db):
    return {
        "items": [
            {"id": record.id, "code": record.code, "name": record.name, "position": record.position}
            for record in db.scalars(
                select(model).where(model.is_active).order_by(model.position).limit(100)
            )
        ]
    }


@router.get("/catalogs/priorities")
def priorities(user: CurrentUser, db: Database):
    return catalog(Priority, user, db)


@router.get("/catalogs/horizons")
def horizons(user: CurrentUser, db: Database):
    return catalog(HorizonType, user, db)


@router.get("/catalogs/workflow")
def workflow_catalog(user: CurrentUser, db: Database):
    stages = list(
        db.scalars(
            select(WorkflowStage)
            .where(WorkflowStage.is_active)
            .order_by(WorkflowStage.position)
            .limit(100)
        )
    )
    edges = list(
        db.scalars(
            select(WorkflowTransition)
            .where(
                WorkflowTransition.is_active, WorkflowTransition.allowed_roles.contains([user.role])
            )
            .order_by(WorkflowTransition.id)
            .limit(1000)
        )
    )
    return {
        "stages": [
            {
                "id": stage.id,
                "name": stage.name,
                "code": stage.code,
                "kind": stage.kind,
                "position": stage.position,
                "is_initial": stage.is_initial,
                "requires_reason": stage.requires_reason,
                "requires_evidence": stage.requires_evidence,
            }
            for stage in stages
        ],
        "transitions": [
            {"id": edge.id, "from_stage_id": edge.from_stage_id, "to_stage_id": edge.to_stage_id}
            for edge in edges
        ],
    }


@router.get("/configuration-status")
def configuration_status(actor: Administrator, db: Database):
    keys = set(db.scalars(select(SystemSetting.key)))
    codes = set(db.scalars(select(HorizonType.code)))
    normal = db.scalar(select(Priority.id).where(Priority.code == "normal", Priority.is_active))
    try:
        service.validate_workflow(db)
        workflow_valid = True
    except CommandError:
        workflow_valid = False
    return {
        "complete": keys == service.SETTING_KEYS
        and codes == service.HORIZONS
        and normal is not None
        and workflow_valid,
        "missing_settings": sorted(service.SETTING_KEYS - keys),
        "missing_horizons": sorted(service.HORIZONS - codes),
        "normal_present": normal is not None,
        "workflow_valid": workflow_valid,
    }


@router.get("/audit-events")
def audit_events(
    actor: Administrator,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
):
    query = select(AuditEvent).order_by(AuditEvent.id).limit(limit + 1)
    if cursor:
        query = query.where(AuditEvent.id > cursor)
    records = list(db.scalars(query))
    return {
        "items": [
            {
                name: getattr(record, name)
                for name in (
                    "id",
                    "created_at",
                    "actor_id",
                    "event_type",
                    "entity_type",
                    "entity_id",
                    "before_data",
                    "after_data",
                    "request_id",
                    "outcome",
                )
            }
            for record in records[:limit]
        ],
        "next_cursor": records[limit - 1].id if len(records) > limit else None,
    }


RELEASE_PROJECTION = (
    "id,created_at,application_version,source_revision,target_revision,phase,status,"
    "result_code,version"
)


@router.get("/releases")
@router.get("/release-history")
def releases(
    actor: Administrator,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
):
    query = "SELECT " + RELEASE_PROJECTION + " FROM release_history"
    if cursor:
        query += " WHERE id > :cursor"
    records = list(
        db.execute(
            text(query + " ORDER BY id LIMIT :limit"), {"limit": limit + 1, "cursor": cursor}
        ).mappings()
    )
    return {
        "items": [dict(record) for record in records[:limit]],
        "next_cursor": records[limit - 1]["id"] if len(records) > limit else None,
    }


@router.get("/releases/{identity}")
@router.get("/release-history/{identity}", include_in_schema=False)
def release(identity: UUID, actor: Administrator, db: Database):
    record = (
        db.execute(
            text("SELECT " + RELEASE_PROJECTION + " FROM release_history WHERE id=:identity"),
            {"identity": identity},
        )
        .mappings()
        .one_or_none()
    )
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return dict(record)
