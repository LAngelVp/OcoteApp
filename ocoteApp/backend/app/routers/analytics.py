from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.models.evaluations import Evaluation
from app.routers.operations import Limit
from app.schemas.analytics import (
    EvaluationCreate,
    EvaluationExport,
    EvaluationFinalize,
    SeriesQuery,
    SummaryQuery,
    TaskExport,
)
from app.schemas.operations import Versioned
from app.services import analytics as service
from app.services import evaluations as evaluation
from app.services import exports
from app.services import operations as operation
from app.services.identity import CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/analytics/summary")
def summary(user: CurrentUser, db: Database, filters: Annotated[SummaryQuery, Query()]):
    limit, cursor = filters.limit, filters.cursor
    rows, moment, zone = service.collect(db, user, filters)
    groups = {}
    for row in rows:
        groups.setdefault(row["department"]["id"], []).append(row)
    departments = [
        {**members[0]["department"], **service.summarize(members)}
        for identity, members in sorted(groups.items())
        if cursor is None or identity > str(cursor)
    ]
    return {
        **service.metadata(user, filters, moment, zone),
        "metrics": service.summarize(rows),
        "items": departments[:limit],
        "next_cursor": departments[limit - 1]["id"] if len(departments) > limit else None,
    }


@router.get("/analytics/series")
def series(user: CurrentUser, db: Database, filters: Annotated[SeriesQuery, Query()]):
    limit, cursor = filters.limit, filters.cursor
    rows, moment, zone = service.collect(db, user, filters)
    points = service.monthly_series(rows, filters.period_start, filters.period_end)
    remaining = [row for row in points if cursor is None or row["month"] > cursor]
    return {
        **service.metadata(user, filters, moment, zone),
        "series": points,
        "items": remaining[:limit],
        "next_cursor": remaining[limit - 1]["month"] if len(remaining) > limit else None,
    }


@router.get("/evaluations")
def evaluations(
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
    annual_plan_id: UUID | None = None,
    department_id: UUID | None = None,
    status: Annotated[str | None, Query(pattern="^(draft|final)$")] = None,
):
    query = evaluation.scope(select(Evaluation), user)
    for column, value in (
        (Evaluation.annual_plan_id, annual_plan_id),
        (Evaluation.department_id, department_id),
        (Evaluation.status, status),
    ):
        if value is not None:
            query = query.where(column == value)
    if cursor:
        query = query.where(Evaluation.id > cursor)
    records = list(db.scalars(query.order_by(Evaluation.id).limit(limit + 1)))
    return {
        "items": [operation.state(record) for record in records[:limit]],
        "next_cursor": records[limit - 1].id if len(records) > limit else None,
    }


@router.post("/evaluations", status_code=201)
def create_evaluation(body: EvaluationCreate, request: Request, user: CurrentUser, db: Database):
    return evaluation.create(db, user, body, request)


@router.get("/evaluations/{identity}")
def evaluation_detail(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    return evaluation.view(db, evaluation.visible(db, user, identity), limit=limit, cursor=cursor)


@router.post("/evaluations/{identity}/recalculate")
def recalculate_evaluation(
    identity: UUID, body: Versioned, request: Request, user: CurrentUser, db: Database
):
    return evaluation.update(db, user, identity, body, request)


@router.post("/evaluations/{identity}/finalize")
def finalize_evaluation(
    identity: UUID, body: EvaluationFinalize, request: Request, user: CurrentUser, db: Database
):
    return evaluation.update(db, user, identity, body, request, finalize=True)


@router.post("/exports/tasks")
def export_tasks(body: TaskExport, request: Request, user: CurrentUser, db: Database):
    return exports.prepare(db, user, body, request)


@router.post("/exports/evaluations/{identity}")
def export_evaluation(
    identity: UUID, body: EvaluationExport, request: Request, user: CurrentUser, db: Database
):
    return exports.prepare(db, user, body, request, evaluation_id=identity)
