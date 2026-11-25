from typing import Annotated, Literal
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.core.evidence import EvidenceSettings
from app.models.identity import WorkflowStage
from app.models.operations import AnnualPlan, EvidenceFile, Objective, Subtask, Task
from app.routers.operations import Limit, page
from app.services import evidence
from app.services import operations as service
from app.services.identity import CurrentUser, Database, audit

router = APIRouter(prefix="/api/v1", tags=["execution"])


def filters(
    annual_plan_id: UUID | None = None,
    department_id: UUID | None = None,
    objective_id: UUID | None = None,
    assignee_id: UUID | None = None,
    stage_id: UUID | None = None,
    priority_id: UUID | None = None,
    punctuality_status: Literal["on_time", "late", "pending", "overdue"] | None = None,
):
    return {
        "annual_plan_id": annual_plan_id,
        "department_id": department_id,
        "objective_id": objective_id,
        "assignee_id": assignee_id,
        "stage_id": stage_id,
        "priority_id": priority_id,
        "punctuality_status": punctuality_status,
    }


Filters = Annotated[dict, Depends(filters)]


def task_query(db, user, selected):
    query = service.task_query(
        user, **{key: value for key, value in selected.items() if key != "punctuality_status"}
    )
    if selected["punctuality_status"]:
        query = service.punctuality_filter(query, selected["punctuality_status"], db)
    return query


@router.get("/kanban")
def kanban(
    user: CurrentUser,
    db: Database,
    selected: Filters,
    limit: Limit = 25,
    lane_id: UUID | None = None,
    cursor: UUID | None = None,
):
    query = task_query(db, user, selected)
    stages = (
        select(WorkflowStage)
        .where(WorkflowStage.is_active)
        .order_by(WorkflowStage.position, WorkflowStage.id)
    )
    if lane_id:
        stages = stages.where(WorkflowStage.id == lane_id)
    columns = []
    for stage in db.scalars(stages):
        scoped = query.where(Task.stage_id == stage.id)
        count = db.scalar(select(func.count()).select_from(scoped.subquery()))
        rows, following = page(db, scoped, Task, limit, cursor)
        columns.append(
            {
                "stage": service.state(stage),
                "count": count,
                "items": [service.task_view(db, row, user) for row in rows],
                "next_cursor": following,
            }
        )
    return {"columns": columns}


@router.get("/timeline")
def timeline(
    kind: Literal["plan", "objective", "task", "subtask"],
    user: CurrentUser,
    db: Database,
    selected: Filters,
    limit: Limit = 50,
    cursor: UUID | None = None,
):
    task_selection = task_query(db, user, selected)
    task_ids = task_selection.with_only_columns(Task.id)
    if kind in {"plan", "objective"}:
        service.permit(user, "admin", "gerente", "lider")
        objectives = service.scope(select(Objective), Objective, user)
        for column, key in [
            (Objective.annual_plan_id, "annual_plan_id"),
            (Objective.department_id, "department_id"),
            (Objective.id, "objective_id"),
        ]:
            if selected[key]:
                objectives = objectives.where(column == selected[key])
        if any(
            selected[key]
            for key in ("assignee_id", "stage_id", "priority_id", "punctuality_status")
        ):
            objectives = objectives.where(
                Objective.id.in_(task_selection.with_only_columns(Task.objective_id))
            )
        if kind == "objective":
            model, query = Objective, objectives
        else:
            model, query = AnnualPlan, service.scope(select(AnnualPlan), AnnualPlan, user)
            if selected["annual_plan_id"]:
                query = query.where(AnnualPlan.id == selected["annual_plan_id"])
            if any(value for key, value in selected.items() if key != "annual_plan_id"):
                query = query.where(
                    AnnualPlan.id.in_(objectives.with_only_columns(Objective.annual_plan_id))
                )
    elif kind == "subtask":
        model, query = Subtask, select(Subtask).where(Subtask.task_id.in_(task_ids))
    else:
        model, query = Task, task_selection
    rows, following = page(db, query, model, limit, cursor)
    items = []
    for row in rows:
        value = service.state(row)
        task = row if kind == "task" else db.get(Task, row.task_id) if kind == "subtask" else None
        if task:
            objective = db.get(Objective, task.objective_id)
            value.update(
                scope_department_id=objective.department_id,
                scope_assignee_id=task.assignee_id,
                task_id=task.id,
            )
            value.update(service.timeliness(row, service.instant(db), service.timezone(db)))
        elif kind == "objective":
            value["scope_department_id"] = row.department_id
        items.append({**value, "row_type": kind})
    return {
        "items": items,
        "next_cursor": following,
        "organization_timezone": str(service.timezone(db)),
    }


@router.get("/tasks/{identity}/evidence")
def evidence_list(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 50, cursor: UUID | None = None
):
    service.visible(db, Task, identity, user)
    rows, following = page(
        db,
        select(EvidenceFile).where(EvidenceFile.task_id == identity),
        EvidenceFile,
        limit,
        cursor,
    )
    settings = EvidenceSettings()
    return {
        "items": [evidence.view(row) for row in rows],
        "next_cursor": following,
        "upload_limit_bytes": service.configuration(db)["evidence_max_bytes"],
        "uploads_configured": settings.evidence_storage_root is not None
        and settings.evidence_clamav_port is not None,
    }


@router.post("/tasks/{identity}/evidence", status_code=201)
async def upload(
    identity: UUID,
    request: Request,
    user: CurrentUser,
    db: Database,
    expected_version: Annotated[int, Query(ge=1)],
    file_name: Annotated[str, Header(alias="X-File-Name", max_length=1024)],
):
    name = unquote(file_name, errors="strict").strip()
    content = await request.body()
    return await run_in_threadpool(
        evidence.attach,
        db,
        user,
        identity,
        expected_version,
        content,
        name,
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower(),
        request,
    )


@router.get("/evidence/{identity}/content")
def download(identity: UUID, request: Request, user: CurrentUser, db: Database):
    record, path = evidence.available(db, user, identity, request)
    audit(
        db,
        request,
        "administration_changed",
        actor=user.id,
        entity="evidence_files",
        entity_id=record.id,
        after={"command": "evidence_download_requested", "task_id": str(record.task_id)},
    )
    db.flush()
    return FileResponse(
        path,
        media_type=record.media_type,
        filename=record.original_name,
        content_disposition_type="attachment",
    )
