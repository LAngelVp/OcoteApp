from datetime import UTC, datetime
from fractions import Fraction
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Date, case, func, select

from app.core.errors import CommandError, ServiceUnavailable
from app.models.identity import (
    Department,
    HorizonType,
    Priority,
    SystemSetting,
    User,
    WorkflowStage,
    WorkflowTransition,
)
from app.models.operations import AnnualPlan, DueDateRequest, Objective, Subtask, Task, TaskHistory
from app.services.administration import HORIZONS, SETTING_KEYS, check_version, validate_workflow
from app.services.identity import audit


def permit(user, *roles):
    if user.role not in roles:
        raise CommandError(403, "FORBIDDEN")


def instant(db):
    return db.scalar(select(func.clock_timestamp())).astimezone(UTC)


def bump(db, record):
    record.version += 1
    record.updated_at = instant(db)


def state(record):
    values = {column.name: getattr(record, column.name) for column in record.__table__.columns}
    return jsonable_encoder(
        {
            key: value.astimezone(UTC) if isinstance(value, datetime) else value
            for key, value in values.items()
        }
    )


def administrative_event(db, request, user, record, before, command, reason=None):
    audit(
        db,
        request,
        "administration_changed",
        actor=user.id,
        entity=record.__tablename__,
        entity_id=record.id,
        before=before,
        after={**state(record), "command": command, "reason": reason},
    )


def history(db, request, user, task, before, event, reason=None, subtask=None, details=None):
    db.flush()
    db.add(
        TaskHistory(
            task_id=task.id,
            subtask_id=subtask.id if subtask else None,
            actor_id=user.id,
            event_type=event,
            before_data=before,
            after_data={**state(subtask or task), **jsonable_encoder(details or {})},
            reason=reason,
            request_id=UUID(request.state.request_id),
        )
    )
    db.flush()


def configuration(db):
    settings = {record.key: record.value for record in db.scalars(select(SystemSetting))}
    if set(settings) != SETTING_KEYS or set(db.scalars(select(HorizonType.code))) != HORIZONS:
        raise CommandError(409, "CONFIGURATION_INCOMPLETE")
    if not db.scalar(select(Priority.id).where(Priority.code == "normal", Priority.is_active)):
        raise CommandError(409, "CONFIGURATION_INCOMPLETE")
    validate_workflow(db)
    return settings


def timezone(db):
    value = db.scalar(
        select(SystemSetting.value).where(SystemSetting.key == "organization_timezone")
    )
    if not isinstance(value, str):
        raise ServiceUnavailable()
    return ZoneInfo(value)


def timeliness(record, moment: datetime, zone: ZoneInfo):
    actual = (record.completed_at or moment).astimezone(zone).date()

    def label(deadline):
        if record.completed_at:
            return "on_time" if actual <= deadline else "late"
        return "overdue" if actual > deadline else "pending"

    return {
        "punctuality_status": label(record.due_date),
        "baseline_punctuality_status": label(record.original_due_date),
        "is_overdue": record.completed_at is None and actual > record.due_date,
        "due_date_delta_days": (record.due_date - record.original_due_date).days,
        "delay_days": max(0, (actual - record.due_date).days),
        "baseline_delay_days": max(0, (actual - record.original_due_date).days),
    }


def task_progress(completed, total, closed):
    return Fraction(100 * completed, total) if total else Fraction(100 if closed else 0)


def scope(query, model, user):
    if model is AnnualPlan:
        permit(user, "admin", "gerente", "lider")
        if user.role == "lider":
            query = query.where(
                AnnualPlan.id.in_(
                    select(Objective.annual_plan_id).where(
                        Objective.department_id == user.department_id
                    )
                )
            )
    elif model is Objective:
        permit(user, "admin", "gerente", "lider")
        if user.role == "lider":
            query = query.where(Objective.department_id == user.department_id)
    else:
        if user.role == "lider":
            query = query.where(
                Task.objective_id.in_(
                    select(Objective.id).where(Objective.department_id == user.department_id)
                )
            )
        elif user.role == "colaborador":
            query = query.where(Task.assignee_id == user.id)
    return query


def visible(db, model, identity, user):
    record = db.scalar(scope(select(model).where(model.id == identity), model, user))
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def lock_rows(db, model, identities):
    return list(
        db.scalars(
            select(model)
            .where(model.id.in_(identities))
            .order_by(model.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def lock_context(
    db, user, *, plan=None, objective=None, task=None, subtask=None, department=None, assignee=None
):
    if subtask is not None:
        task = task or db.get(Task, subtask.task_id)
    if task is not None:
        objective = objective or db.get(Objective, task.objective_id)
    if objective is not None:
        department = objective.department_id
        plan = plan or db.get(AnnualPlan, objective.annual_plan_id)
    if department:
        lock_rows(db, Department, [department])
    users = {user.id}
    if task is not None:
        users.add(task.assignee_id)
    if assignee:
        users.add(assignee)
    lock_rows(db, User, users)
    lock_rows(db, AnnualPlan, [plan.id])
    if objective is not None:
        lock_rows(db, Objective, [objective.id])
    if task is not None:
        lock_rows(db, Task, [task.id])
        if task.assignee_id not in users:
            raise CommandError(409, "VERSION_CONFLICT")
        visible(db, Task, task.id, user)
    if subtask is not None:
        lock_rows(db, Subtask, [subtask.id])
    return plan, objective, task, subtask


def open_plan(plan, *, active=False):
    if plan.status == "closed" or (active and plan.status != "active"):
        raise CommandError(409, "PLAN_NOT_EDITABLE")


def open_task(plan, task):
    open_plan(plan, active=True)
    if task.completed_at is not None:
        raise CommandError(409, "TASK_COMPLETED")


def horizon(db, code, previous=None):
    if code == previous:
        return
    entry = db.scalar(select(HorizonType).where(HorizonType.code == code, HorizonType.is_active))
    if entry is None:
        raise CommandError(422, "INVALID_HORIZON")


def contained(start, original, due, parent):
    if not (
        parent.start_date <= start <= original <= parent.due_date
        and start <= due <= parent.due_date
    ):
        raise CommandError(422, "INVALID_INTERVAL")


def child_dates(task, child):
    if not (
        task.start_date <= child.start_date <= child.original_due_date <= task.original_due_date
        and child.start_date <= child.due_date <= task.due_date
    ):
        raise CommandError(422, "INVALID_INTERVAL")


def valid_assignee(db, identity, department):
    record = db.get(User, identity)
    if (
        not record
        or not record.is_active
        or record.department_id != department
        or record.role == "gerente"
    ):
        raise CommandError(422, "INVALID_ASSIGNEE")


def priority(db, identity=None):
    query = select(Priority).where(Priority.is_active)
    query = (
        query.where(Priority.id == identity) if identity else query.where(Priority.code == "normal")
    )
    record = db.scalar(query)
    if record is None:
        raise CommandError(422, "INVALID_PRIORITY")
    return record.id


def aggregate_progress(db, user, *, plan=None, objective=None):
    query = select(
        Task.id,
        Task.completed_at,
        func.count(Subtask.id),
        func.count(Subtask.id).filter(Subtask.status == "completed"),
    )
    query = query.join(Objective, Objective.id == Task.objective_id).outerjoin(
        Subtask, Subtask.task_id == Task.id
    )
    if plan:
        query = query.where(Objective.annual_plan_id == plan)
    if objective:
        query = query.where(Objective.id == objective)
    rows = db.execute(scope(query, Task, user).group_by(Task.id)).all()
    if not rows:
        return None
    return round(
        float(
            sum(
                (task_progress(done, count, closed is not None) for _, closed, count, done in rows),
                Fraction(),
            )
            / len(rows)
        ),
        2,
    )


def plan_view(db, record, user):
    return {**state(record), "progress_percent": aggregate_progress(db, user, plan=record.id)}


def objective_view(db, record, user):
    return {**state(record), "progress_percent": aggregate_progress(db, user, objective=record.id)}


def subtask_view(db, record, *, moment=None, zone=None):
    return {**state(record), **timeliness(record, moment or instant(db), zone or timezone(db))}


def task_view(db, record, user, *, counts=None, moment=None, zone=None):
    total, completed = (
        counts
        if counts is not None
        else db.execute(
            select(
                func.count(Subtask.id), func.count(Subtask.id).filter(Subtask.status == "completed")
            ).where(Subtask.task_id == record.id)
        ).one()
    )
    objective = db.get(Objective, record.objective_id)
    plan = db.get(AnnualPlan, objective.annual_plan_id)
    fields = ("id", "title", "horizon_type", "start_date", "due_date")
    selected_priority = db.get(Priority, record.priority_id)
    return {
        **state(record),
        **timeliness(record, moment or instant(db), zone or timezone(db)),
        "progress_percent": round(
            float(task_progress(completed, total, record.completed_at is not None)), 2
        ),
        "pending_closure": bool(total) and completed == total and record.completed_at is None,
        "objective": {field: getattr(objective, field) for field in fields},
        "annual_plan": {field: getattr(plan, field) for field in fields},
        "priority": {
            field: getattr(selected_priority, field) for field in ("id", "code", "name", "version")
        },
    }


def create_plan(db, user, body, request):
    permit(user, "admin", "gerente")
    configuration(db)
    horizon(db, body.horizon_type)
    record = AnnualPlan(**body.model_dump(), created_by=user.id)
    db.add(record)
    db.flush()
    administrative_event(db, request, user, record, {}, "plan_created")
    return plan_view(db, record, user)


def create_objective(db, user, body, request):
    permit(user, "admin", "gerente")
    configuration(db)
    plan = visible(db, AnnualPlan, body.annual_plan_id, user)
    lock_context(db, user, plan=plan, department=body.department_id)
    open_plan(plan)
    department = db.get(Department, body.department_id)
    if not department or not department.is_active:
        raise CommandError(422, "INVALID_DEPARTMENT")
    horizon(db, body.horizon_type)
    contained(body.start_date, body.due_date, body.due_date, plan)
    record = Objective(**body.model_dump(), created_by=user.id)
    db.add(record)
    db.flush()
    administrative_event(db, request, user, record, {}, "objective_created")
    return objective_view(db, record, user)


def update_planning(db, user, record, body, request, command):
    permit(user, "admin", "gerente")
    plan, _, _, _ = lock_context(
        db,
        user,
        plan=record if isinstance(record, AnnualPlan) else None,
        objective=record if isinstance(record, Objective) else None,
    )
    check_version(record, body.expected_version)
    open_plan(plan)
    before = state(record)
    if command == "period_changed":
        horizon(db, body.horizon_type, record.horizon_type)
        if isinstance(record, AnnualPlan):
            children = list(
                db.scalars(select(Objective).where(Objective.annual_plan_id == record.id))
            )
            if any(
                child.start_date < body.start_date or child.due_date > body.due_date
                for child in children
            ):
                raise CommandError(409, "DEPENDENCY_CONFLICT")
        else:
            contained(body.start_date, body.due_date, body.due_date, plan)
            children = list(db.scalars(select(Task).where(Task.objective_id == record.id)))
            if any(
                child.start_date < body.start_date
                or max(child.original_due_date, child.due_date) > body.due_date
                for child in children
            ):
                raise CommandError(409, "DEPENDENCY_CONFLICT")
    if command == "status_changed":
        if (record.status, body.status) not in {("draft", "active"), ("active", "closed")}:
            raise CommandError(409, "INVALID_PLAN_TRANSITION")
        if body.status == "active":
            objectives = list(
                db.scalars(select(Objective).where(Objective.annual_plan_id == plan.id))
            )
            if not objectives or any(
                not db.get(Department, obj.department_id).is_active for obj in objectives
            ):
                raise CommandError(409, "DEPENDENCY_CONFLICT")
            record.activated_at = instant(db)
        else:
            if db.scalar(
                select(Task.id)
                .join(Objective)
                .where(Objective.annual_plan_id == plan.id, Task.completed_at.is_(None))
                .limit(1)
            ):
                raise CommandError(409, "DEPENDENCY_CONFLICT")
            record.closed_at = instant(db)
    for field, value in body.model_dump(exclude={"expected_version", "reason"}).items():
        setattr(record, field, value)
    bump(db, record)
    db.flush()
    administrative_event(db, request, user, record, before, command, getattr(body, "reason", None))
    return (
        plan_view(db, record, user)
        if isinstance(record, AnnualPlan)
        else objective_view(db, record, user)
    )


def create_task(db, user, body, request):
    permit(user, "admin", "lider")
    configuration(db)
    objective = visible(db, Objective, body.objective_id, user)
    plan, _, _, _ = lock_context(db, user, objective=objective, assignee=body.assignee_id)
    open_plan(plan, active=True)
    if not db.get(Department, objective.department_id).is_active:
        raise CommandError(422, "INVALID_DEPARTMENT")
    valid_assignee(db, body.assignee_id, objective.department_id)
    contained(body.start_date, body.due_date, body.due_date, objective)
    stage = db.scalar(
        select(WorkflowStage).where(WorkflowStage.is_initial, WorkflowStage.is_active)
    )
    record = Task(
        **body.model_dump(exclude={"priority_id"}),
        priority_id=priority(db, body.priority_id),
        original_due_date=body.due_date,
        stage_id=stage.id,
        created_by=user.id,
    )
    db.add(record)
    db.flush()
    history(db, request, user, record, {}, "task_created")
    return task_view(db, record, user)


def task_context(db, user, identity, subtask=False):
    child = db.get(Subtask, identity) if subtask else None
    if subtask and child is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    task = visible(db, Task, child.task_id if child else identity, user)
    return lock_context(db, user, task=task, subtask=child)


def change_task(db, user, identity, body, request, command):
    task = visible(db, Task, identity, user)
    allowed = (
        ("admin", "gerente")
        if command == "due_date_changed"
        else (
            ("admin", "lider", "colaborador") if command == "stage_changed" else ("admin", "lider")
        )
    )
    permit(user, *allowed)
    plan, objective, task, _ = lock_context(
        db, user, task=task, assignee=getattr(body, "assignee_id", None)
    )
    open_task(plan, task)
    check_version(task, body.expected_version)
    before = state(task)
    if command == "stage_changed":
        target = db.get(WorkflowStage, body.to_stage_id)
        edge = db.scalar(
            select(WorkflowTransition).where(
                WorkflowTransition.from_stage_id == task.stage_id,
                WorkflowTransition.to_stage_id == body.to_stage_id,
                WorkflowTransition.is_active,
            )
        )
        if not target or not target.is_active or not edge or user.role not in edge.allowed_roles:
            raise CommandError(422, "INVALID_TRANSITION")
        if target.requires_evidence and not body.evidence_ids:
            raise CommandError(422, "EVIDENCE_REQUIRED")
        if body.evidence_ids:
            from app.services.evidence import available

            if len(body.evidence_ids) != len(set(body.evidence_ids)):
                raise CommandError(422, "INVALID_EVIDENCE")
            for identity in body.evidence_ids:
                available(db, user, identity, request, task_id=task.id)
        if target.requires_reason and body.reason is None:
            raise CommandError(422, "REASON_REQUIRED")
        if target.kind == "completed":
            if db.scalar(
                select(Subtask.id)
                .where(Subtask.task_id == task.id, Subtask.status != "completed")
                .limit(1)
            ):
                raise CommandError(409, "PENDING_SUBTASKS")
            task.completed_at = instant(db)
        task.stage_id = target.id
    elif command == "assignment_changed":
        valid_assignee(db, body.assignee_id, objective.department_id)
        task.assignee_id = body.assignee_id
    elif command == "task_updated":
        task.title, task.description = body.title, body.description
        if "priority_id" in body.model_fields_set:
            task.priority_id = priority(db, body.priority_id)
    else:
        setattr(
            task,
            "due_date" if command == "due_date_changed" else "start_date",
            body.due_date if command == "due_date_changed" else body.start_date,
        )
        contained(task.start_date, task.original_due_date, task.due_date, objective)
        for child in db.scalars(select(Subtask).where(Subtask.task_id == task.id)):
            try:
                child_dates(task, child)
            except CommandError:
                raise CommandError(409, "DEPENDENCY_CONFLICT") from None
    bump(db, task)
    details = None
    if command == "stage_changed":
        details = {
            "evidence_ids": body.evidence_ids,
            "stage_rules": {
                field: getattr(target, field)
                for field in ("id", "version", "kind", "requires_reason", "requires_evidence")
            },
            "transition_id": edge.id,
            "transition_version": edge.version,
        }
    history(
        db, request, user, task, before, command, getattr(body, "reason", None), details=details
    )
    return task_view(db, task, user)


def change_subtask(db, user, identity, body, request, command):
    plan, _, task, child = task_context(db, user, identity, subtask=command != "subtask_created")
    permit(
        user,
        *(
            ("admin", "gerente")
            if command == "subtask_due_date_changed"
            else (
                ("admin", "lider", "colaborador")
                if command == "subtask_completed"
                else ("admin", "lider")
            )
        ),
    )
    open_task(plan, task)
    if child:
        check_version(task, body.expected_task_version)
        check_version(child, body.expected_version)
        if child.status == "completed":
            raise CommandError(409, "SUBTASK_COMPLETED")
    else:
        check_version(task, body.expected_version)
    before = state(child) if child else {}
    if command == "subtask_created":
        child = Subtask(
            **body.model_dump(exclude={"expected_version"}),
            task_id=task.id,
            original_due_date=body.due_date,
            created_by=user.id,
        )
        db.add(child)
    elif command == "subtask_completed":
        child.status, child.completed_at = "completed", instant(db)
    elif command == "subtask_updated":
        child.title = body.title
    else:
        setattr(
            child,
            "due_date" if command == "subtask_due_date_changed" else "start_date",
            body.due_date if command == "subtask_due_date_changed" else body.start_date,
        )
    child_dates(task, child)
    if command != "subtask_created":
        bump(db, child)
    bump(db, task)
    history(db, request, user, task, before, command, getattr(body, "reason", None), child)
    return {"subtask": subtask_view(db, child), "task": task_view(db, task, user)}


def request_date(db, user, identity, body, request, *, subtask=False):
    permit(user, "admin", "gerente", "lider")
    plan, objective, task, child = task_context(db, user, identity, subtask)
    open_task(plan, task)
    check_version(task, body.expected_task_version)
    if child:
        check_version(child, body.expected_subtask_version)
        if child.status == "completed":
            raise CommandError(409, "SUBTASK_COMPLETED")
    target = child or task
    if target.due_date == body.proposed_due_date:
        raise CommandError(422, "UNCHANGED_DATE")
    if child:
        child_dates(
            task,
            SimpleNamespace(
                start_date=child.start_date,
                original_due_date=child.original_due_date,
                due_date=body.proposed_due_date,
            ),
        )
    else:
        contained(task.start_date, task.original_due_date, body.proposed_due_date, objective)
        if db.scalar(
            select(Subtask.id)
            .where(Subtask.task_id == task.id, Subtask.due_date > body.proposed_due_date)
            .limit(1)
        ):
            raise CommandError(409, "DEPENDENCY_CONFLICT")
    record = DueDateRequest(
        task_id=task.id,
        subtask_id=child.id if child else None,
        requested_by=user.id,
        proposed_due_date=body.proposed_due_date,
        previous_due_date=target.due_date,
        task_version_at_request=task.version,
        subtask_version_at_request=child.version if child else None,
        reason=body.reason,
    )
    db.add(record)
    db.flush()
    administrative_event(db, request, user, record, {}, "due_date_requested", body.reason)
    return state(record)


def visible_request(db, user, identity):
    permit(user, "admin", "gerente", "lider")
    record = db.get(DueDateRequest, identity)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    visible(db, Task, record.task_id, user)
    return record


def decide_date(db, user, identity, body, request, decision):
    record = visible_request(db, user, identity)
    if decision != "cancelled":
        permit(user, "admin", "gerente")
    if user.role == "lider" and record.requested_by != user.id:
        raise CommandError(403, "FORBIDDEN")
    plan, _, task, child = task_context(
        db, user, record.subtask_id or record.task_id, record.subtask_id is not None
    )
    lock_rows(db, DueDateRequest, [record.id])
    check_version(record, body.expected_version)
    if record.status != "pending":
        raise CommandError(409, "REQUEST_TERMINAL")
    before = state(record)
    result = {}
    if decision == "approved":
        if record.requested_by == user.id:
            raise CommandError(403, "SELF_APPROVAL_FORBIDDEN")
        open_task(plan, task)
        check_version(task, record.task_version_at_request)
        from app.schemas.operations import DueChange, SubtaskDueChange

        if child:
            check_version(child, record.subtask_version_at_request)
            result = change_subtask(
                db,
                user,
                child.id,
                SubtaskDueChange(
                    due_date=record.proposed_due_date,
                    reason=body.reason,
                    expected_version=child.version,
                    expected_task_version=task.version,
                ),
                request,
                "subtask_due_date_changed",
            )
        else:
            result = {
                "task": change_task(
                    db,
                    user,
                    task.id,
                    DueChange(
                        due_date=record.proposed_due_date,
                        reason=body.reason,
                        expected_version=task.version,
                    ),
                    request,
                    "due_date_changed",
                )
            }
    record.status, record.decided_by = decision, user.id
    record.decision_reason, record.decided_at = body.reason, instant(db)
    bump(db, record)
    db.flush()
    administrative_event(db, request, user, record, before, "due_date_decided", body.reason)
    return {"request": state(record), **result}


def task_query(
    user,
    *,
    annual_plan_id=None,
    department_id=None,
    objective_id=None,
    assignee_id=None,
    stage_id=None,
    priority_id=None,
):
    query = scope(select(Task), Task, user)
    if annual_plan_id:
        query = query.where(
            Task.objective_id.in_(
                select(Objective.id).where(Objective.annual_plan_id == annual_plan_id)
            )
        )
    if department_id:
        query = query.where(
            Task.objective_id.in_(
                select(Objective.id).where(Objective.department_id == department_id)
            )
        )
    for column, value in (
        (Task.objective_id, objective_id),
        (Task.assignee_id, assignee_id),
        (Task.stage_id, stage_id),
        (Task.priority_id, priority_id),
    ):
        if value is not None:
            query = query.where(column == value)
    return query


def punctuality_filter(query, status, db):
    zone = timezone(db).key
    local_today = func.timezone(zone, func.clock_timestamp()).cast(Date)
    local_completed = func.timezone(zone, Task.completed_at).cast(Date)
    computed = case(
        (
            Task.completed_at.is_not(None),
            case((local_completed <= Task.due_date, "on_time"), else_="late"),
        ),
        (local_today > Task.due_date, "overdue"),
        else_="pending",
    )
    return query.where(computed == status)
