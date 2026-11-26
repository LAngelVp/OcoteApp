from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, tuple_

from app.core.errors import CommandError
from app.models.identity import Priority
from app.models.operations import AnnualPlan, DueDateRequest, Objective, Subtask, Task, TaskHistory
from app.schemas.operations import (
    Assignment,
    ChildVersion,
    DateRequest,
    Decision,
    DueChange,
    ObjectiveCreate,
    ObjectiveUpdate,
    PeriodChange,
    PlanCreate,
    PlanUpdate,
    ScheduleChange,
    StageChange,
    StatusChange,
    SubtaskCreate,
    SubtaskDateRequest,
    SubtaskDueChange,
    SubtaskScheduleChange,
    SubtaskUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.services import operations as service
from app.services.identity import CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["operations"])
Limit = Annotated[int, Query(ge=1, le=100)]


def page(db, query, model, limit, cursor):
    if cursor:
        query = query.where(model.id > cursor)
    rows = list(db.scalars(query.order_by(model.id).limit(limit + 1)))
    return rows[:limit], rows[limit - 1].id if len(rows) > limit else None


@router.get("/annual-plans")
def plans(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    rows, following = page(
        db, service.scope(select(AnnualPlan), AnnualPlan, user), AnnualPlan, limit, cursor
    )
    return {
        "items": [service.plan_view(db, record, user) for record in rows],
        "next_cursor": following,
    }


@router.post("/annual-plans", status_code=201)
def create_plan(body: PlanCreate, request: Request, user: CurrentUser, db: Database):
    return service.create_plan(db, user, body, request)


@router.get("/annual-plans/{identity}")
def plan(identity: UUID, user: CurrentUser, db: Database):
    return service.plan_view(db, service.visible(db, AnnualPlan, identity, user), user)


@router.patch("/annual-plans/{identity}")
def update_plan(
    identity: UUID, body: PlanUpdate, request: Request, user: CurrentUser, db: Database
):
    return service.update_planning(
        db, user, service.visible(db, AnnualPlan, identity, user), body, request, "plan_updated"
    )


@router.post("/annual-plans/{identity}/period-changes")
def plan_period(
    identity: UUID, body: PeriodChange, request: Request, user: CurrentUser, db: Database
):
    return service.update_planning(
        db, user, service.visible(db, AnnualPlan, identity, user), body, request, "period_changed"
    )


@router.post("/annual-plans/{identity}/status-changes")
def plan_status(
    identity: UUID, body: StatusChange, request: Request, user: CurrentUser, db: Database
):
    return service.update_planning(
        db, user, service.visible(db, AnnualPlan, identity, user), body, request, "status_changed"
    )


@router.get("/objectives")
def objectives(
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
    annual_plan_id: UUID | None = None,
    department_id: UUID | None = None,
):
    query = service.scope(select(Objective), Objective, user)
    if annual_plan_id:
        query = query.where(Objective.annual_plan_id == annual_plan_id)
    if department_id:
        query = query.where(Objective.department_id == department_id)
    rows, following = page(db, query, Objective, limit, cursor)
    return {
        "items": [service.objective_view(db, record, user) for record in rows],
        "next_cursor": following,
    }


@router.post("/objectives", status_code=201)
def create_objective(body: ObjectiveCreate, request: Request, user: CurrentUser, db: Database):
    return service.create_objective(db, user, body, request)


@router.get("/objectives/{identity}")
def objective(identity: UUID, user: CurrentUser, db: Database):
    return service.objective_view(db, service.visible(db, Objective, identity, user), user)


@router.patch("/objectives/{identity}")
def update_objective(
    identity: UUID, body: ObjectiveUpdate, request: Request, user: CurrentUser, db: Database
):
    return service.update_planning(
        db, user, service.visible(db, Objective, identity, user), body, request, "objective_updated"
    )


@router.post("/objectives/{identity}/period-changes")
def objective_period(
    identity: UUID, body: PeriodChange, request: Request, user: CurrentUser, db: Database
):
    return service.update_planning(
        db, user, service.visible(db, Objective, identity, user), body, request, "period_changed"
    )


@router.get("/tasks")
def tasks(
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
    annual_plan_id: UUID | None = None,
    department_id: UUID | None = None,
    objective_id: UUID | None = None,
    assignee_id: UUID | None = None,
    stage_id: UUID | None = None,
    priority_id: UUID | None = None,
    punctuality_status: Literal["on_time", "late", "pending", "overdue"] | None = None,
):
    query = service.task_query(
        user,
        annual_plan_id=annual_plan_id,
        department_id=department_id,
        objective_id=objective_id,
        assignee_id=assignee_id,
        stage_id=stage_id,
        priority_id=priority_id,
    )
    if punctuality_status:
        query = service.punctuality_filter(query, punctuality_status, db)
    rows, following = page(db, query, Task, limit, cursor)
    if not rows:
        return {"items": [], "next_cursor": following}
    objectives = list(
        db.scalars(select(Objective).where(Objective.id.in_({row.objective_id for row in rows})))
    )
    _parents = list(
        db.scalars(
            select(AnnualPlan).where(AnnualPlan.id.in_({row.annual_plan_id for row in objectives}))
        )
    )
    _priorities = list(
        db.scalars(select(Priority).where(Priority.id.in_({row.priority_id for row in rows})))
    )
    counts = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            select(
                Subtask.task_id,
                func.count(Subtask.id),
                func.count(Subtask.id).filter(Subtask.status == "completed"),
            )
            .where(Subtask.task_id.in_([record.id for record in rows]))
            .group_by(Subtask.task_id)
        )
    }
    moment, zone = service.instant(db), service.timezone(db)
    result = {
        "items": [
            service.task_view(
                db, row, user, counts=counts.get(row.id, (0, 0)), moment=moment, zone=zone
            )
            for row in rows
        ],
        "next_cursor": following,
    }
    return result


@router.post("/tasks", status_code=201)
def create_task(body: TaskCreate, request: Request, user: CurrentUser, db: Database):
    return service.create_task(db, user, body, request)


@router.get("/tasks/{identity}")
def task(identity: UUID, user: CurrentUser, db: Database):
    return service.task_view(db, service.visible(db, Task, identity, user), user)


def task_command(path, schema, command, *, method="POST"):
    def execute(identity: UUID, body: schema, request: Request, user: CurrentUser, db: Database):
        return service.change_task(db, user, identity, body, request, command)

    router.add_api_route("/tasks/{identity}" + path, execute, methods=[method], name=command)


task_command("", TaskUpdate, "task_updated", method="PATCH")
task_command("/assignments", Assignment, "assignment_changed")
task_command("/stage-transitions", StageChange, "stage_changed")
task_command("/due-date-changes", DueChange, "due_date_changed")
task_command("/schedule-changes", ScheduleChange, "schedule_changed")


@router.get("/tasks/{identity}/subtasks")
def subtasks(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    service.visible(db, Task, identity, user)
    rows, following = page(
        db, select(Subtask).where(Subtask.task_id == identity), Subtask, limit, cursor
    )
    moment, zone = service.instant(db), service.timezone(db)
    return {
        "items": [service.subtask_view(db, row, moment=moment, zone=zone) for row in rows],
        "next_cursor": following,
    }


@router.post("/tasks/{identity}/subtasks", status_code=201)
def create_subtask(
    identity: UUID, body: SubtaskCreate, request: Request, user: CurrentUser, db: Database
):
    return service.change_subtask(db, user, identity, body, request, "subtask_created")


@router.get("/subtasks/{identity}")
def subtask(identity: UUID, user: CurrentUser, db: Database):
    record = db.get(Subtask, identity)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    service.visible(db, Task, record.task_id, user)
    return service.subtask_view(db, record)


def subtask_command(path, schema, command, *, method="POST"):
    def execute(identity: UUID, body: schema, request: Request, user: CurrentUser, db: Database):
        return service.change_subtask(db, user, identity, body, request, command)

    router.add_api_route("/subtasks/{identity}" + path, execute, methods=[method], name=command)


subtask_command("", SubtaskUpdate, "subtask_updated", method="PATCH")
subtask_command("/completion", ChildVersion, "subtask_completed")
subtask_command("/due-date-changes", SubtaskDueChange, "subtask_due_date_changed")
subtask_command("/schedule-changes", SubtaskScheduleChange, "subtask_schedule_changed")


@router.post("/tasks/{identity}/due-date-requests", status_code=201)
def request_task_date(
    identity: UUID, body: DateRequest, request: Request, user: CurrentUser, db: Database
):
    return service.request_date(db, user, identity, body, request)


@router.post("/subtasks/{identity}/due-date-requests", status_code=201)
def request_subtask_date(
    identity: UUID, body: SubtaskDateRequest, request: Request, user: CurrentUser, db: Database
):
    return service.request_date(db, user, identity, body, request, subtask=True)


@router.get("/due-date-requests")
def date_requests(
    user: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
):
    service.permit(user, "admin", "gerente", "lider")
    query = select(DueDateRequest).where(
        DueDateRequest.task_id.in_(service.scope(select(Task.id), Task, user))
    )
    if status:
        query = query.where(DueDateRequest.status == status)
    rows, following = page(db, query, DueDateRequest, limit, cursor)
    return {"items": [service.state(record) for record in rows], "next_cursor": following}


@router.get("/due-date-requests/{identity}")
def date_request(identity: UUID, user: CurrentUser, db: Database):
    return service.state(service.visible_request(db, user, identity))


def decision_command(path, decision):
    def execute(identity: UUID, body: Decision, request: Request, user: CurrentUser, db: Database):
        return service.decide_date(db, user, identity, body, request, decision)

    router.add_api_route(
        "/due-date-requests/{identity}/" + path, execute, methods=["POST"], name=decision
    )


decision_command("approve", "approved")
decision_command("reject", "rejected")
decision_command("cancel", "cancelled")


@router.get("/tasks/{identity}/history")
def history(
    identity: UUID, user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    service.visible(db, Task, identity, user)
    query = select(TaskHistory).where(TaskHistory.task_id == identity)
    if cursor:
        previous = db.scalar(query.where(TaskHistory.id == cursor))
        if previous is None:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        query = query.where(
            tuple_(TaskHistory.created_at, TaskHistory.id) > (previous.created_at, previous.id)
        )
    rows = list(db.scalars(query.order_by(TaskHistory.created_at, TaskHistory.id).limit(limit + 1)))
    return {
        "items": [service.state(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }
