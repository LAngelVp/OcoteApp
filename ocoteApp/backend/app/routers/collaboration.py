from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.models.collaboration import TaskImpediment
from app.schemas.collaboration import (
    CommentWrite,
    DependencyWrite,
    EntityType,
    FieldWrite,
    ImpedimentWrite,
    InstantiateTemplate,
    MetadataWrite,
    PrincipalWrite,
    RecurrenceRun,
    RecurrenceWrite,
    ResolveImpediment,
    SavedViewWrite,
    SearchFilters,
    TagWrite,
    TemplateWrite,
)
from app.services import collaboration as service
from app.services import operations as operation
from app.services.enterprise import require_module, require_page_size
from app.services.identity import CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["collaboration"])
Limit = Annotated[int, Query(ge=1, le=100)]
CommentEntity = Literal["task", "objective"]


def page(db, query, model, limit, cursor):
    require_page_size(db, limit)
    if cursor:
        query = query.where(model.id > cursor)
    rows = list(db.scalars(query.order_by(model.id).limit(limit + 1)))
    return rows[:limit], rows[limit - 1].id if len(rows) > limit else None


@router.get("/tasks/{identity}/dependencies")
def dependencies(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    require_module(db, "dependencies")
    task, plan, _objective = service.resource(db, user, "task", identity)
    rows, following = page(
        db, service.visible_dependencies(db, user, task), service.TaskDependency, limit, cursor
    )
    return {
        "items": [operation.state(row) for row in rows],
        "next_cursor": following,
        "task_version": task.version,
        "plan_version": plan.version,
    }


@router.put("/tasks/{identity}/dependencies")
def dependency(
    identity: UUID, body: DependencyWrite, request: Request, user: CurrentUser, db: Database
):
    return service.write_dependency(db, user, identity, body, request)


@router.get("/tasks/{identity}/impediments")
def impediments(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    require_module(db, "impediments")
    task, _plan, _objective = service.resource(db, user, "task", identity)
    rows, following = page(
        db,
        select(TaskImpediment).where(TaskImpediment.task_id == identity),
        TaskImpediment,
        limit,
        cursor,
    )
    return {
        "items": [operation.state(row) for row in rows],
        "next_cursor": following,
        "task_version": task.version,
    }


@router.post("/tasks/{identity}/impediments", status_code=201)
def open_impediment(
    identity: UUID, body: ImpedimentWrite, request: Request, user: CurrentUser, db: Database
):
    return service.open_impediment(db, user, identity, body, request)


@router.post("/tasks/{identity}/impediments/{impediment_id}/resolution")
def resolve_impediment(
    identity: UUID,
    impediment_id: UUID,
    body: ResolveImpediment,
    request: Request,
    user: CurrentUser,
    db: Database,
):
    return service.resolve_impediment(db, user, identity, impediment_id, body, request)


@router.get("/collaboration/{entity_type}/{identity}/mentions")
def mentions(
    entity_type: CommentEntity,
    identity: UUID,
    user: CurrentUser,
    db: Database,
    q: Annotated[str, Query(max_length=120)] = "",
    limit: Limit = 5,
):
    return {"items": service.mentions(db, user, entity_type, identity, q, limit)}


@router.get("/collaboration/{entity_type}/{identity}/comments")
def comments(
    entity_type: CommentEntity,
    identity: UUID,
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
):
    require_module(db, "comments")
    target, _plan, objective = service.resource(db, user, entity_type, identity)
    rows, following = page(
        db, service.comment_query(target, entity_type), service.Comment, limit, cursor
    )
    return {
        "items": [
            service.comment_view(db, row, user, entity_type, target, objective) for row in rows
        ],
        "next_cursor": following,
        "resource_version": target.version,
    }


@router.get("/collaboration/{entity_type}/{identity}/comments/{comment_id}/revisions")
def comment_revisions(
    entity_type: CommentEntity,
    identity: UUID,
    comment_id: UUID,
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
):
    rows, following = page(
        db,
        service.comment_revisions_query(db, user, entity_type, identity, comment_id),
        service.CommentRevision,
        limit,
        cursor,
    )
    return {"items": [operation.state(row) for row in rows], "next_cursor": following}


@router.post("/collaboration/{entity_type}/{identity}/comments", status_code=201)
def create_comment(
    entity_type: CommentEntity,
    identity: UUID,
    body: CommentWrite,
    request: Request,
    user: CurrentUser,
    db: Database,
):
    return service.write_comment(db, user, entity_type, identity, None, body, request)


@router.put("/collaboration/{entity_type}/{identity}/comments/{comment_id}")
def update_comment(
    entity_type: CommentEntity,
    identity: UUID,
    comment_id: UUID,
    body: CommentWrite,
    request: Request,
    user: CurrentUser,
    db: Database,
):
    return service.write_comment(db, user, entity_type, identity, comment_id, body, request)


@router.get("/collaboration/{entity_type}/{identity}/metadata")
def metadata(entity_type: EntityType, identity: UUID, user: CurrentUser, db: Database):
    return service.metadata_view(db, user, entity_type, identity)


@router.get("/collaboration/metadata-schema/{entity_type}")
def metadata_schema(
    entity_type: EntityType, user: CurrentUser, db: Database, department_id: UUID | None = None
):
    return service.metadata_schema(db, user, entity_type, department_id)


@router.put("/collaboration/{entity_type}/{identity}/metadata")
def write_metadata(
    entity_type: EntityType,
    identity: UUID,
    body: MetadataWrite,
    request: Request,
    user: CurrentUser,
    db: Database,
):
    return service.write_metadata(db, user, entity_type, identity, body, request)


@router.get("/collaboration/custom-fields")
def fields(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "custom_fields")
    rows, following = page(
        db,
        service.catalog_query(service.CustomFieldDefinition, user),
        service.CustomFieldDefinition,
        limit,
        cursor,
    )
    return {"items": [service.field_view(db, row) for row in rows], "next_cursor": following}


@router.post("/collaboration/custom-fields/{identity}/preflight")
def field_preflight(identity: UUID, body: FieldWrite, user: CurrentUser, db: Database):
    return {"impacted_count": service.field_preflight(db, user, identity, body)}


@router.put("/collaboration/custom-fields/{identity}")
def write_field(
    identity: UUID, body: FieldWrite, request: Request, user: CurrentUser, db: Database
):
    return service.write_field(db, user, identity, body, request)


@router.get("/collaboration/tags")
def tags(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "tags")
    rows, following = page(db, service.catalog_query(service.Tag, user), service.Tag, limit, cursor)
    return {"items": [operation.state(row) for row in rows], "next_cursor": following}


@router.put("/collaboration/tags/{identity}")
def write_tag(identity: UUID, body: TagWrite, request: Request, user: CurrentUser, db: Database):
    return service.write_tag(db, user, identity, body, request)


@router.get("/collaboration/templates")
def templates(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "templates")
    rows, following = page(
        db, service.catalog_query(service.Template, user), service.Template, limit, cursor
    )
    items = []
    for row in rows:
        version = db.scalar(
            select(service.TemplateVersion).where(
                service.TemplateVersion.template_id == row.id,
                service.TemplateVersion.template_version == row.current_version,
            )
        )
        items.append({**operation.state(row), "template_version": operation.state(version)})
    return {"items": items, "next_cursor": following}


@router.put("/collaboration/templates/{identity}")
def write_template(
    identity: UUID, body: TemplateWrite, request: Request, user: CurrentUser, db: Database
):
    return service.write_template(db, user, identity, body, request)


@router.post("/collaboration/templates/preview")
def preview_template(body: InstantiateTemplate, user: CurrentUser, db: Database):
    template, version, rows = service.preview_template(db, user, body)
    return {
        "template_id": template.id,
        "template_version_id": version.id,
        "items": [{**row, "blueprint": row["blueprint"].model_dump(mode="json")} for row in rows],
    }


@router.post("/collaboration/templates/instantiate", status_code=201)
def instantiate_template(
    body: InstantiateTemplate, request: Request, user: CurrentUser, db: Database
):
    return service.instantiate_template(db, user, body, request)


@router.get("/collaboration/service-principals")
def principals(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "recurrence")
    operation.permit(user, "admin", "lider")
    query = select(service.ServicePrincipal)
    if user.role == "lider":
        query = query.where(
            service.ServicePrincipal.is_active,
            service.ServicePrincipal.department_ids.any(user.department_id),
        )
    rows, following = page(db, query, service.ServicePrincipal, limit, cursor)
    return {
        "items": [
            operation.state(row)
            if user.role == "admin"
            else {
                "id": row.id,
                "name": row.name,
                "approved_scopes": row.approved_scopes,
                "version": row.version,
            }
            for row in rows
        ],
        "next_cursor": following,
    }


@router.get("/collaboration/calendar-context/{objective_id}")
def calendar_context(objective_id: UUID, user: CurrentUser, db: Database):
    from app.services.enterprise import calendar_effective

    require_module(db, "recurrence")
    require_module(db, "calendar")
    objective, _plan, _objective = service.resource(db, user, "objective", objective_id)
    selected, _identities = calendar_effective(db, objective.department_id)
    return {
        "id": selected.id,
        "name": selected.name,
        "version": selected.version,
        "timezone": str(operation.timezone(db)),
    }


@router.put("/collaboration/service-principals/{identity}")
def write_principal(
    identity: UUID, body: PrincipalWrite, request: Request, user: CurrentUser, db: Database
):
    return service.write_principal(db, user, identity, body, request)


@router.get("/collaboration/recurrence-schedules")
def schedules(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "recurrence")
    rows, following = page(
        db, service.schedule_scope(user), service.RecurrenceSchedule, limit, cursor
    )
    return {"items": [operation.state(row) for row in rows], "next_cursor": following}


@router.put("/collaboration/recurrence-schedules/{identity}")
def write_schedule(
    identity: UUID, body: RecurrenceWrite, request: Request, user: CurrentUser, db: Database
):
    return service.save_schedule(db, user, identity, body, request)


@router.post("/collaboration/recurrence-schedules/{identity}/runs")
def run_schedule(
    identity: UUID, body: RecurrenceRun, request: Request, user: CurrentUser, db: Database
):
    return service.run_schedule(db, user, identity, body, request)


@router.post("/collaboration/search")
def search(
    body: SearchFilters,
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: Annotated[str, Query(max_length=1024)] | None = None,
):
    return service.search(db, user, body, limit, cursor)


@router.get("/collaboration/saved-views")
def saved_views(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    require_module(db, "saved_views")
    rows, following = page(db, service.saved_view_query(user), service.SavedView, limit, cursor)
    return {"items": [operation.state(row) for row in rows], "next_cursor": following}


@router.put("/collaboration/saved-views/{identity}")
def save_view(
    identity: UUID, body: SavedViewWrite, request: Request, user: CurrentUser, db: Database
):
    return service.save_view(db, user, identity, body, request)


@router.get("/collaboration/saved-views/{identity}/results")
def view_results(
    identity: UUID,
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: Annotated[str, Query(max_length=1024)] | None = None,
):
    from app.core.errors import CommandError

    require_module(db, "saved_views")
    record = db.scalar(service.saved_view_query(user).where(service.SavedView.id == identity))
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if not record.active or record.filter_schema_version != 1:
        raise CommandError(409, "SAVED_VIEW_INACTIVE_OR_UNSUPPORTED")
    return service.search(db, user, SearchFilters.model_validate(record.filters), limit, cursor)
