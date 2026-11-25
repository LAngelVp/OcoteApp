from collections import Counter
from datetime import date
from fractions import Fraction

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.errors import CommandError
from app.models.identity import Department, HorizonType, Priority, User, WorkflowStage
from app.models.operations import AnnualPlan, Objective, Subtask, Task, TaskHistory
from app.services import operations as operation
from app.services.operations import task_progress

CALCULATION_VERSION = "1.0"
MAX_COHORT = 10000
MAX_SERIES_MONTHS = 1200


def collect(db, user, filters, *, maximum=MAX_COHORT):
    operation.permit(user, "admin", "gerente", "lider")
    if user.role == "lider" and filters.department_id not in {None, user.department_id}:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    counts = (
        select(
            Subtask.task_id,
            func.count(Subtask.id).label("total"),
            func.count(Subtask.id).filter(Subtask.status == "completed").label("done"),
        )
        .group_by(Subtask.task_id)
        .subquery()
    )
    changes = (
        select(TaskHistory.task_id, func.count().label("total"))
        .where(TaskHistory.event_type == "due_date_changed")
        .group_by(TaskHistory.task_id)
        .subquery()
    )
    plan_horizon, objective_horizon = aliased(HorizonType), aliased(HorizonType)
    query = (
        select(
            Task,
            Objective,
            AnnualPlan,
            Department,
            User,
            WorkflowStage,
            Priority,
            func.coalesce(counts.c.total, 0),
            func.coalesce(counts.c.done, 0),
            func.coalesce(changes.c.total, 0),
            plan_horizon.name,
            objective_horizon.name,
        )
        .join(Objective, Objective.id == Task.objective_id)
        .join(AnnualPlan, AnnualPlan.id == Objective.annual_plan_id)
        .join(Department, Department.id == Objective.department_id)
        .join(User, User.id == Task.assignee_id)
        .join(WorkflowStage, WorkflowStage.id == Task.stage_id)
        .join(Priority, Priority.id == Task.priority_id)
        .join(plan_horizon, plan_horizon.code == AnnualPlan.horizon_type)
        .join(objective_horizon, objective_horizon.code == Objective.horizon_type)
        .outerjoin(counts, counts.c.task_id == Task.id)
        .outerjoin(changes, changes.c.task_id == Task.id)
    )
    query = operation.scope(query, Task, user)
    for column, value in (
        (AnnualPlan.id, filters.annual_plan_id),
        (Department.id, filters.department_id),
        (User.id, filters.assignee_id),
        (WorkflowStage.kind, filters.status),
    ):
        if value is not None:
            query = query.where(column == value)
    if filters.period_start:
        query = query.where(
            Task.original_due_date.between(filters.period_start, filters.period_end)
        )
    if filters.punctuality_status:
        query = operation.punctuality_filter(query, filters.punctuality_status, db)
    moment = db.scalar(select(func.transaction_timestamp()))
    zone = operation.timezone(db)
    records = db.execute(query.order_by(Task.id).limit(maximum + 1)).all()
    if len(records) > maximum:
        raise CommandError(413, "COHORT_TOO_LARGE")
    result = []
    for (
        task,
        _objective,
        _plan,
        department,
        person,
        stage,
        _priority,
        total,
        done,
        changed,
        plan_label,
        objective_label,
    ) in records:
        row = operation.task_view(db, task, user, counts=(total, done), moment=moment, zone=zone)
        result.append(
            jsonable_encoder(
                {
                    **row,
                    "progress_percent": float(
                        task_progress(done, total, task.completed_at is not None)
                    ),
                    "subtasks_total": total,
                    "subtasks_completed": done,
                    "due_date_change_count": changed,
                    "department": {"id": department.id, "name": department.name},
                    "assignee": {"id": person.id, "display_name": person.display_name},
                    "stage": {"id": stage.id, "name": stage.name, "kind": stage.kind},
                    "annual_plan": {**row["annual_plan"], "horizon_name": plan_label},
                    "objective": {**row["objective"], "horizon_name": objective_label},
                }
            )
        )
    return result, moment, zone


def metadata(user, filters, moment, zone):
    effective = filters.model_dump(
        mode="json", exclude_none=True, exclude={"limit", "cursor", "format"}
    )
    if user.role == "lider":
        effective["department_id"] = str(user.department_id)
    return {
        "schema_version": "1.0",
        "calculation_version": CALCULATION_VERSION,
        "snapshot_at": moment,
        "organization_timezone": str(zone),
        "filters": effective,
        "scope": {
            "role": user.role,
            "department_id": user.department_id if user.role == "lider" else None,
        },
    }


def summarize(rows):
    total = len(rows)
    completed = sum(row["completed_at"] is not None for row in rows)
    current = Counter(row["punctuality_status"] for row in rows)
    baseline = Counter(row["baseline_punctuality_status"] for row in rows)

    def rate(value):
        return float(Fraction(100 * value, total)) if total else None

    def average(key):
        return float(Fraction(sum(row[key] for row in rows), total)) if total else None

    progress = sum(
        (
            task_progress(
                row["subtasks_completed"], row["subtasks_total"], row["completed_at"] is not None
            )
            for row in rows
        ),
        Fraction(),
    )
    return {
        "task_count": total,
        "completed_count": completed,
        "open_count": total - completed,
        "blocked_count": sum(row["stage"]["kind"] == "blocked" for row in rows),
        "pending_closure_count": sum(row["pending_closure"] for row in rows),
        "progress_percent": float(progress / total) if total else None,
        "completion_rate": rate(completed),
        "on_time_rate": rate(current["on_time"]),
        "baseline_on_time_rate": rate(baseline["on_time"]),
        "punctuality_counts": {
            key: current[key] for key in ("on_time", "late", "pending", "overdue")
        },
        "baseline_punctuality_counts": {
            key: baseline[key] for key in ("on_time", "late", "pending", "overdue")
        },
        "average_delay_days": average("delay_days"),
        "average_baseline_delay_days": average("baseline_delay_days"),
        "average_due_date_delta_days": average("due_date_delta_days"),
        "rescheduled_count": sum(
            bool(row["due_date_change_count"] or row["due_date_delta_days"]) for row in rows
        ),
        "due_date_change_count": sum(row["due_date_change_count"] for row in rows),
    }


def monthly_series(rows, start=None, end=None):
    grouped = {}
    for row in rows:
        grouped.setdefault(str(row["original_due_date"])[:7], []).append(row)
    if not grouped and (start is None or end is None):
        return []
    first = start or date.fromisoformat(min(grouped) + "-01")
    last = end or date.fromisoformat(max(grouped) + "-01")
    if (last.year - first.year) * 12 + last.month - first.month + 1 > MAX_SERIES_MONTHS:
        raise CommandError(413, "COHORT_TOO_LARGE")
    month = date(first.year, first.month, 1)
    result = []
    while (month.year, month.month) <= (last.year, last.month):
        key = month.isoformat()[:7]
        result.append({"month": key, **summarize(grouped.get(key, []))})
        if month.year == 9999 and month.month == 12:
            break
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return result
