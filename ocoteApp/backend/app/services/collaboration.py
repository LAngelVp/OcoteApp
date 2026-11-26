import base64
import hashlib
import json
from calendar import monthrange
from collections import defaultdict, deque
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, cast, func, literal, literal_column, or_, select, union_all

from app.core.errors import CommandError
from app.models.collaboration import (
    Comment,
    CommentMention,
    CommentRevision,
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldValue,
    EntityTag,
    JobRun,
    OutboxEvent,
    RecurrenceOccurrence,
    RecurrenceSchedule,
    SavedView,
    ServicePrincipal,
    Tag,
    TaskDependency,
    TaskImpediment,
    Template,
    TemplateVersion,
)
from app.models.enterprise import CalendarConfig, CalendarHoliday
from app.models.identity import Department, User, WorkflowStage
from app.models.operations import AnnualPlan, Objective, Task
from app.services import operations as operation
from app.services.administration import check_version
from app.services.enterprise import enabled, require_module, require_page_size


def assert_acyclic(edges):
    successors, incoming = defaultdict(set), defaultdict(int)
    for predecessor, successor in edges:
        if predecessor == successor:
            raise CommandError(422, "DEPENDENCY_SELF_REFERENCE")
        if successor in successors[predecessor]:
            raise CommandError(409, "DEPENDENCY_DUPLICATE")
        successors[predecessor].add(successor)
        incoming.setdefault(predecessor, 0)
        incoming[successor] += 1
    ready = deque(identity for identity, count in incoming.items() if count == 0)
    visited = 0
    while ready:
        predecessor = ready.popleft()
        visited += 1
        for successor in successors[predecessor]:
            incoming[successor] -= 1
            if incoming[successor] == 0:
                ready.append(successor)
    if visited != len(incoming):
        raise CommandError(409, "DEPENDENCY_CYCLE")


def impeded_seconds(intervals, moment):
    ordered = sorted((opened, closed or moment) for opened, closed in intervals)
    total, previous_end = 0.0, None
    for opened, closed in ordered:
        if opened.tzinfo is None or closed.tzinfo is None or closed < opened:
            raise CommandError(422, "INVALID_IMPEDIMENT_INTERVAL")
        start = max(opened, previous_end) if previous_end else opened
        total += max(0, (closed - start).total_seconds())
        previous_end = max(previous_end, closed) if previous_end else closed
    return total


def plain_text(value, *, limit=10000):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= limit
        or any(ord(character) < 32 and character not in "\r\n\t" for character in value)
    ):
        raise CommandError(422, "INVALID_PLAIN_TEXT")
    return value.strip()


def typed_value(definition, value, options=()):
    result = dict.fromkeys(
        ("text_value", "number_value", "date_value", "boolean_value", "option_id", "option_ids")
    )
    kind = definition.data_type
    constraints = definition.constraints or {}
    try:
        if kind in {"text", "url"}:
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError
            if kind == "text":
                if (
                    not constraints.get("min_length", 0)
                    <= len(value)
                    <= min(2000, constraints.get("max_length", 2000))
                ):
                    raise ValueError
            else:
                parts = urlsplit(value)
                if (
                    parts.scheme != "https"
                    or not parts.hostname
                    or parts.username is not None
                    or parts.password is not None
                    or "\\" in value
                    or len(value) > 2048
                    or any(character.isspace() or ord(character) < 32 for character in value)
                    or (parts.port is not None and not 1 <= parts.port <= 65535)
                ):
                    raise ValueError
            result["text_value"] = value
        elif kind == "boolean":
            if type(value) is not bool:
                raise ValueError
            result["boolean_value"] = value
        elif kind == "number":
            if type(value) not in {int, float, Decimal}:
                raise ValueError
            number = Decimal(str(value))
            if (
                not number.is_finite()
                or number.as_tuple().exponent < -4
                or abs(number) >= Decimal("100000000000000")
            ):
                raise ValueError
            if "min" in constraints and number < Decimal(str(constraints["min"])):
                raise ValueError
            if "max" in constraints and number > Decimal(str(constraints["max"])):
                raise ValueError
            result["number_value"] = number
        elif kind == "date":
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError
            result["date_value"] = date.fromisoformat(value)
        else:
            active = {str(option.id) for option in options if option.is_active}
            selected = value if kind == "multi_select" else [value]
            if (
                kind not in {"select", "multi_select"}
                or not isinstance(selected, list)
                or not 1 <= len(selected) <= 50
                or any(
                    not isinstance(identity, str) or identity not in active for identity in selected
                )
                or len(set(selected)) != len(selected)
            ):
                raise ValueError
            identities = [UUID(identity) for identity in selected]
            result["option_ids" if kind == "multi_select" else "option_id"] = (
                identities if kind == "multi_select" else identities[0]
            )
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise CommandError(422, "CUSTOM_FIELD_TYPE_OR_CONSTRAINT") from None
    return result


def occurrence_dates(rule, calendar, *, after=None):
    holidays = set(calendar["holidays"])

    def business(day):
        return (
            bool(calendar["weekday_mask"] & (1 << day.weekday()))
            and day.isoformat() not in holidays
        )

    position = 0
    if after is not None and after >= rule.start_date:
        if rule.frequency in {"daily", "weekly"}:
            position = (after - rule.start_date).days // (
                rule.interval * (7 if rule.frequency == "weekly" else 1)
            )
        else:
            position = (
                (after.year - rule.start_date.year) * 12 + after.month - rule.start_date.month
            ) // (rule.interval * (12 if rule.frequency == "yearly" else 1))
    while rule.occurrence_count is None or position < rule.occurrence_count:
        try:
            skipped = False
            if rule.frequency in {"daily", "weekly"}:
                scheduled = rule.start_date + timedelta(
                    days=position * rule.interval * (7 if rule.frequency == "weekly" else 1)
                )
            else:
                month = (
                    rule.start_date.month
                    - 1
                    + position * rule.interval * (12 if rule.frequency == "yearly" else 1)
                )
                year = rule.start_date.year + month // 12
                last = monthrange(year, month % 12 + 1)[1]
                skipped = rule.start_date.day > last and rule.end_policy == "skip"
                scheduled = date(year, month % 12 + 1, min(rule.start_date.day, last))
            if rule.end_date is not None and scheduled > rule.end_date:
                break
            if after is not None and scheduled <= after:
                position += 1
                continue
            effective = scheduled
            if not business(scheduled) and rule.non_business_policy != "keep":
                if rule.non_business_policy == "skip":
                    skipped = True
                else:
                    direction = 1 if rule.non_business_policy == "next" else -1
                    for _offset in range(366):
                        if business(effective):
                            break
                        effective += timedelta(days=direction)
                    else:
                        raise CommandError(422, "CALENDAR_NO_BUSINESS_DAY")
            yield scheduled, effective, skipped
            position += 1
        except (ValueError, OverflowError):
            raise CommandError(422, "RECURRENCE_DATE_OUT_OF_RANGE") from None


ENTITY_MODELS = {"plan": AnnualPlan, "objective": Objective, "task": Task}


def resource(db, user, entity_type, identity, *, write=False, roles=()):
    model = ENTITY_MODELS[entity_type]
    record = operation.visible(db, model, identity, user)
    if write:
        if roles:
            operation.permit(user, *roles)
        plan, objective, task, _child = operation.lock_context(db, user, **{entity_type: record})
        if task:
            operation.open_task(plan, task)
        else:
            operation.open_plan(plan)
    else:
        objective = (
            db.get(Objective, record.objective_id)
            if entity_type == "task"
            else record
            if entity_type == "objective"
            else None
        )
        plan = record if entity_type == "plan" else db.get(AnnualPlan, objective.annual_plan_id)
    return record, plan, objective


def save_record(db, user, request, record, before, command, reason):
    db.add(record)
    db.flush()
    operation.administrative_event(db, request, user, record, before, command, reason)
    db.flush()


def outbox(db, user, entity_type, record, objective, event):
    entry = OutboxEvent(
        event_id=uuid4(),
        event_type=event,
        schema_version=1,
        task_id=record.id if entity_type == "task" else None,
        objective_id=record.id if entity_type == "objective" else None,
        actor_id=None if getattr(user, "actor_service_id", None) else user.id,
        actor_service_id=getattr(user, "actor_service_id", None),
        department_id=objective.department_id,
        payload={"resource_id": str(record.id), "version": record.version},
    )
    db.add(entry)
    db.flush()
    return entry


def journal(db, user, request, record, before, event, reason, *, entity_type="task"):
    operation.bump(db, record)
    if entity_type == "task":
        operation.history(db, request, user, record, before, event, reason)
    else:
        save_record(db, user, request, record, before, event, reason)


def visible_dependencies(db, user, task):
    allowed = operation.scope(select(Task.id), Task, user)
    return select(TaskDependency).where(
        or_(
            TaskDependency.predecessor_task_id == task.id,
            TaskDependency.successor_task_id == task.id,
        ),
        TaskDependency.predecessor_task_id.in_(allowed),
        TaskDependency.successor_task_id.in_(allowed),
    )


def write_dependency(db, user, identity, body, request):
    require_module(db, "dependencies")
    operation.permit(user, "admin", "lider")
    successor = operation.visible(db, Task, identity, user)
    predecessor = operation.visible(db, Task, body.predecessor_task_id, user)
    own = db.get(Objective, successor.objective_id)
    other = db.get(Objective, predecessor.objective_id)
    if (own.department_id, own.annual_plan_id) != (other.department_id, other.annual_plan_id):
        raise CommandError(422, "DEPENDENCY_SCOPE_MISMATCH")
    operation.lock_rows(db, Department, [own.department_id])
    operation.lock_rows(db, User, {user.id, successor.assignee_id, predecessor.assignee_id})
    plan = db.get(AnnualPlan, own.annual_plan_id)
    operation.lock_rows(db, AnnualPlan, [plan.id])
    operation.lock_rows(db, Objective, {own.id, other.id})
    operation.lock_rows(db, Task, {successor.id, predecessor.id})
    operation.visible(db, Task, successor.id, user)
    operation.visible(db, Task, predecessor.id, user)
    operation.open_task(plan, successor)
    operation.open_task(plan, predecessor)
    check_version(successor, body.expected_version)
    check_version(predecessor, body.expected_predecessor_version)
    check_version(plan, body.expected_plan_version)
    edges = list(
        db.scalars(
            select(TaskDependency).where(
                TaskDependency.successor_task_id.in_(
                    select(Task.id).join(Objective).where(Objective.annual_plan_id == plan.id)
                ),
                TaskDependency.active,
            )
        )
    )
    record = db.scalar(
        select(TaskDependency).where(
            TaskDependency.predecessor_task_id == predecessor.id,
            TaskDependency.successor_task_id == successor.id,
        )
    )
    if record and record.active == body.active:
        raise CommandError(409, "DEPENDENCY_DUPLICATE")
    if not record and not body.active:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    graph = [
        (edge.predecessor_task_id, edge.successor_task_id)
        for edge in edges
        if record is None or edge.id != record.id
    ]
    if body.active:
        graph.append((predecessor.id, successor.id))
    assert_acyclic(graph)
    before = operation.state(record) if record else {}
    if record:
        operation.bump(db, record)
        record.active = body.active
    else:
        record = TaskDependency(
            predecessor_task_id=predecessor.id,
            successor_task_id=successor.id,
            created_by=user.id,
            active=True,
        )
    save_record(db, user, request, record, before, "dependency_changed", body.reason)
    plan_before, task_before = operation.state(plan), operation.state(successor)
    operation.bump(db, plan)
    save_record(db, user, request, plan, plan_before, "dependency_changed", body.reason)
    journal(db, user, request, successor, task_before, "dependency_changed", body.reason)
    outbox(db, user, "task", successor, own, "dependency_changed")
    return {
        "dependency": operation.state(record),
        "task_version": successor.version,
        "plan_version": plan.version,
    }


def open_impediment(db, user, identity, body, request):
    require_module(db, "impediments")
    task, _plan, objective = resource(
        db, user, "task", identity, write=True, roles=("admin", "lider", "colaborador")
    )
    check_version(task, body.expected_version)
    if user.role == "colaborador" and body.owner_user_id != user.id:
        raise CommandError(403, "FORBIDDEN")
    operation.valid_assignee(db, body.owner_user_id, objective.department_id)
    owner = db.get(User, body.owner_user_id)
    if owner.role == "colaborador" and owner.id != task.assignee_id:
        raise CommandError(422, "INVALID_IMPEDIMENT_OWNER")
    before = operation.state(task)
    record = TaskImpediment(
        task_id=task.id,
        owner_user_id=body.owner_user_id,
        reason=body.reason,
        severity=body.severity,
        kind=body.kind,
        required_area=body.required_area,
        opened_at=operation.instant(db),
        closed_at=None,
        resolution=None,
    )
    save_record(db, user, request, record, {}, "impediment_changed", body.reason)
    journal(db, user, request, task, before, "impediment_changed", body.reason)
    outbox(db, user, "task", task, objective, "impediment_changed")
    return {"impediment": operation.state(record), "task_version": task.version}


def resolve_impediment(db, user, identity, impediment_id, body, request):
    require_module(db, "impediments")
    task, _plan, objective = resource(
        db, user, "task", identity, write=True, roles=("admin", "lider", "colaborador")
    )
    check_version(task, body.expected_task_version)
    record = db.scalar(
        select(TaskImpediment)
        .where(TaskImpediment.id == impediment_id, TaskImpediment.task_id == task.id)
        .with_for_update()
    )
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if user.role == "colaborador" and record.owner_user_id != user.id:
        raise CommandError(403, "FORBIDDEN")
    check_version(record, body.expected_version)
    if record.closed_at is not None:
        raise CommandError(409, "IMPEDIMENT_ALREADY_RESOLVED")
    before, task_before = operation.state(record), operation.state(task)
    record.closed_at, record.resolution = operation.instant(db), body.resolution
    operation.bump(db, record)
    save_record(db, user, request, record, before, "impediment_changed", body.reason)
    journal(db, user, request, task, task_before, "impediment_changed", body.reason)
    outbox(db, user, "task", task, objective, "impediment_changed")
    return {"impediment": operation.state(record), "task_version": task.version}


def completion_allowed(db, task):
    if db.scalar(
        select(TaskDependency.id)
        .join(Task, Task.id == TaskDependency.predecessor_task_id)
        .where(
            TaskDependency.successor_task_id == task.id,
            TaskDependency.active,
            Task.completed_at.is_(None),
        )
        .limit(1)
    ):
        raise CommandError(409, "PENDING_PREDECESSORS")
    if db.scalar(
        select(TaskImpediment.id)
        .where(TaskImpediment.task_id == task.id, TaskImpediment.closed_at.is_(None))
        .limit(1)
    ):
        raise CommandError(409, "OPEN_IMPEDIMENTS")


def readers_query(record, objective):
    return select(User).where(
        User.is_active,
        or_(
            User.role.in_(["admin", "gerente"]),
            and_(User.role == "lider", User.department_id == objective.department_id),
            and_(User.role == "colaborador", User.id == record.assignee_id)
            if isinstance(record, Task)
            else False,
        ),
    )


def mentions(db, user, entity_type, identity, query, limit):
    require_module(db, "comments")
    require_page_size(db, limit)
    record, _plan, objective = resource(db, user, entity_type, identity)
    if not query.strip():
        return []
    rows = db.scalars(
        readers_query(record, objective)
        .where(func.strpos(func.lower(User.display_name), query.strip().lower()) > 0)
        .order_by(User.display_name, User.id)
        .limit(limit)
    )
    return [{"id": row.id, "display_name": row.display_name} for row in rows]


def comment_query(record, entity_type):
    return select(Comment).where(getattr(Comment, entity_type + "_id") == record.id)


def comment_revisions_query(db, user, entity_type, identity, comment_id):
    require_module(db, "comments")
    target, _plan, _objective = resource(db, user, entity_type, identity)
    comment = db.scalar(comment_query(target, entity_type).where(Comment.id == comment_id))
    if comment is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return select(CommentRevision).where(CommentRevision.comment_id == comment.id)


def comment_view(db, record, user, entity_type, target, objective):
    revision = db.scalar(
        select(CommentRevision).where(
            CommentRevision.comment_id == record.id,
            CommentRevision.revision_no == record.current_revision,
        )
    )
    allowed = readers_query(target, objective).with_only_columns(User.id)
    mentioned = list(
        db.scalars(
            select(CommentMention.mentioned_user_id).where(
                CommentMention.comment_revision_id == revision.id,
                CommentMention.mentioned_user_id.in_(allowed),
            )
        )
    )
    visible_readers = list(
        db.scalars(select(User).where(User.id.in_(mentioned), User.id.in_(allowed)))
    )
    return {
        **operation.state(record),
        "body": None if record.annulled_at else revision.body,
        "mention_ids": [reader.id for reader in visible_readers],
        "mentions": [
            {"id": reader.id, "display_name": reader.display_name} for reader in visible_readers
        ],
        "can_edit": record.annulled_at is None
        and (user.id == record.author_id or user.role == "admin"),
    }


def write_comment(db, user, entity_type, identity, comment_id, body, request):
    require_module(db, "comments")
    target, _plan, objective = resource(db, user, entity_type, identity, write=True)
    check_version(target, body.expected_resource_version)
    readers = list(
        db.scalars(
            readers_query(target, objective).where(User.id.in_(body.mention_ids)).order_by(User.id)
        )
    )
    if len(readers) != len(body.mention_ids):
        raise CommandError(422, "MENTION_NOT_VISIBLE_OR_ACTIVE")
    text = plain_text(body.body)
    if any("@" + reader.display_name not in text for reader in readers):
        raise CommandError(422, "MENTION_TEXT_REQUIRED")
    if comment_id:
        record = db.scalar(
            comment_query(target, entity_type).where(Comment.id == comment_id).with_for_update()
        )
        if record is None:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        if user.id != record.author_id and user.role != "admin":
            raise CommandError(403, "FORBIDDEN")
        check_version(record, body.expected_version)
        if record.annulled_at or body.parent_comment_id != record.parent_comment_id:
            raise CommandError(409, "COMMENT_IMMUTABLE_OR_ANNULLED")
        before = operation.state(record)
        record.current_revision += 1
        record.annulled_at = operation.instant(db) if body.annulled else None
        operation.bump(db, record)
    else:
        if body.expected_version != 0 or body.annulled:
            raise CommandError(409, "VERSION_CONFLICT")
        depth, parent_id = 1, body.parent_comment_id
        while parent_id:
            parent = db.scalar(comment_query(target, entity_type).where(Comment.id == parent_id))
            if parent is None:
                raise CommandError(404, "RESOURCE_NOT_FOUND")
            depth, parent_id = depth + 1, parent.parent_comment_id
            if depth > 5:
                raise CommandError(422, "COMMENT_DEPTH_LIMIT")
        before = {}
        record = Comment(
            **{entity_type + "_id": target.id},
            author_id=user.id,
            parent_comment_id=body.parent_comment_id,
            current_revision=1,
            annulled_at=None,
        )
    task_before = operation.state(target)
    save_record(db, user, request, record, before, "comment_changed", body.reason)
    revision = CommentRevision(
        comment_id=record.id,
        author_id=user.id,
        revision_no=record.current_revision,
        body=text,
        reason=body.reason,
        annulment=body.annulled,
    )
    db.add(revision)
    db.flush()
    journal(
        db,
        user,
        request,
        target,
        task_before,
        "comment_changed",
        body.reason,
        entity_type=entity_type,
    )
    event = outbox(db, user, entity_type, target, objective, "comment_changed")
    for reader in readers:
        db.add(
            CommentMention(
                comment_revision_id=revision.id,
                mentioned_user_id=reader.id,
                notification_event_id=event.id,
            )
        )
    db.flush()
    return {
        "comment": comment_view(db, record, user, entity_type, target, objective),
        "resource_version": target.version,
    }


def applicable(model, department):
    return or_(
        model.scope_kind == "organization",
        and_(model.scope_kind == "department", model.department_id == department)
        if department is not None
        else False,
    )


def catalog_query(model, user):
    operation.permit(user, "admin", "gerente", "lider")
    query = select(model)
    return query.where(applicable(model, user.department_id)) if user.role == "lider" else query


def scope_write(db, user, body, *, template=False):
    operation.permit(user, *(("admin", "gerente", "lider") if template else ("admin",)))
    if user.role != "admin":
        if (
            not template
            or body.scope_kind != "department"
            or user.role == "gerente"
            and (getattr(body, "entity_type", None) == "task")
        ):
            raise CommandError(403, "FORBIDDEN")
        if user.role == "lider" and (
            body.department_id != user.department_id or body.entity_type != "task"
        ):
            raise CommandError(403, "FORBIDDEN")
    if body.department_id is not None:
        department = db.get(Department, body.department_id)
        if department is None or not department.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")


def mutable_record(db, model, identity, body, *, values):
    record = db.scalar(select(model).where(model.id == identity).with_for_update())
    if record:
        check_version(record, body.expected_version)
        before = operation.state(record)
        operation.bump(db, record)
        for field, value in values.items():
            setattr(record, field, value)
    else:
        if body.expected_version != 0:
            raise CommandError(409, "VERSION_CONFLICT")
        before, record = {}, model(id=identity, **values)
    return record, before


def write_tag(db, user, identity, body, request):
    require_module(db, "tags")
    scope_write(db, user, body)
    values = body.model_dump(exclude={"expected_version", "reason"})
    values["label"] = plain_text(body.label, limit=60)
    values["name_normalized"] = body.label.lower()
    existing = db.get(Tag, identity)
    if existing and any(
        getattr(existing, field) != values[field] for field in ("scope_kind", "department_id")
    ):
        raise CommandError(409, "IMMUTABLE_SCOPE")
    record, before = mutable_record(db, Tag, identity, body, values=values)
    save_record(db, user, request, record, before, "tag_changed", body.reason)
    return operation.state(record)


VALUE_COLUMNS = (
    "text_value",
    "number_value",
    "date_value",
    "boolean_value",
    "option_id",
    "option_ids",
)


def value_of(record):
    for column in VALUE_COLUMNS:
        value = getattr(record, column)
        if value is not None:
            if column == "date_value":
                return value.isoformat()
            if column == "option_id":
                return str(value)
            if column == "option_ids":
                return [str(identity) for identity in value]
            return value
    return None


def field_options(db, definition):
    return list(
        db.scalars(
            select(CustomFieldOption)
            .where(CustomFieldOption.definition_id == definition.id)
            .order_by(CustomFieldOption.position, CustomFieldOption.id)
        )
    )


def field_view(db, record):
    return {
        **operation.state(record),
        "options": [operation.state(option) for option in field_options(db, record)],
    }


def field_preflight(db, user, identity, body):
    require_module(db, "custom_fields")
    scope_write(db, user, body)
    if not body.active or not (body.required_on_create or body.required_stage_ids):
        return 0
    model = ENTITY_MODELS[body.entity_type]
    query = select(model.id)
    if model is AnnualPlan:
        query = query.where(AnnualPlan.status != "closed")
    elif model is Objective:
        query = query.join(AnnualPlan).where(AnnualPlan.status != "closed")
        if body.department_id:
            query = query.where(Objective.department_id == body.department_id)
    else:
        query = (
            query.join(Objective)
            .join(AnnualPlan)
            .where(AnnualPlan.status != "closed", Task.completed_at.is_(None))
        )
        if body.department_id:
            query = query.where(Objective.department_id == body.department_id)
        if not body.required_on_create:
            query = query.where(Task.stage_id.in_(body.required_stage_ids))
    entity_column = getattr(CustomFieldValue, body.entity_type + "_id")
    present = select(entity_column).where(
        CustomFieldValue.definition_id == identity,
        or_(*(getattr(CustomFieldValue, column).is_not(None) for column in VALUE_COLUMNS)),
    )
    return db.scalar(
        select(func.count()).select_from(query.where(~model.id.in_(present)).subquery())
    )


def write_field(db, user, identity, body, request):
    require_module(db, "custom_fields")
    scope_write(db, user, body)
    impacted = field_preflight(db, user, identity, body)
    if (
        body.active
        and (body.required_on_create or body.required_stage_ids)
        and (body.expected_impacted_count != impacted)
    ):
        raise CommandError(409, "CUSTOM_FIELD_PREFLIGHT_REQUIRED_OR_STALE")
    if body.required_stage_ids:
        stages = set(
            db.scalars(
                select(WorkflowStage.id).where(
                    WorkflowStage.id.in_(body.required_stage_ids), WorkflowStage.is_active
                )
            )
        )
        if stages != set(body.required_stage_ids):
            raise CommandError(422, "INVALID_REQUIRED_STAGE")
    count = db.scalar(
        select(func.count())
        .select_from(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.entity_type == body.entity_type,
            CustomFieldDefinition.scope_kind == body.scope_kind,
            CustomFieldDefinition.department_id == body.department_id,
            CustomFieldDefinition.active,
            CustomFieldDefinition.id != identity,
        )
    )
    if body.active and count >= 50:
        raise CommandError(409, "CUSTOM_FIELD_LIMIT")
    values = body.model_dump(
        exclude={"expected_version", "reason", "options", "expected_impacted_count", "constraints"}
    )
    values["constraints"] = body.constraints.model_dump(exclude_none=True)
    previous = db.get(CustomFieldDefinition, identity)
    if previous and any(
        getattr(previous, key) != values[key]
        for key in ("entity_type", "key", "data_type", "scope_kind", "department_id")
    ):
        raise CommandError(409, "CUSTOM_FIELD_IMMUTABLE_IDENTITY")
    record, before = mutable_record(db, CustomFieldDefinition, identity, body, values=values)
    save_record(db, user, request, record, before, "custom_field_changed", body.reason)
    existing = {option.id: option for option in field_options(db, record)}
    incoming = {option.id for option in body.options if option.id is not None}
    if not set(existing) <= incoming:
        raise CommandError(422, "ARCHIVE_OPTIONS_EXPLICITLY")
    for option in body.options:
        candidate = existing.get(option.id)
        if candidate and candidate.code != option.code:
            raise CommandError(409, "CUSTOM_FIELD_OPTION_IMMUTABLE_CODE")
        if option.id and not candidate and db.get(CustomFieldOption, option.id):
            raise CommandError(422, "INVALID_OPTION")
        entry, old = mutable_record(
            db,
            CustomFieldOption,
            option.id or uuid4(),
            option,
            values={
                "definition_id": record.id,
                **option.model_dump(exclude={"expected_version", "id"}),
            },
        )
        save_record(db, user, request, entry, old, "custom_field_option_changed", body.reason)
    return {**field_view(db, record), "impacted_count": impacted}


def metadata_view(db, user, entity_type, identity):
    record, _plan, objective = resource(db, user, entity_type, identity)
    department = objective.department_id if objective else None
    fields, values, tags, assigned = [], [], [], []
    if enabled(db, "custom_fields"):
        definitions = list(
            db.scalars(
                select(CustomFieldDefinition)
                .where(
                    CustomFieldDefinition.entity_type == entity_type,
                    applicable(CustomFieldDefinition, department),
                )
                .order_by(CustomFieldDefinition.key)
            )
        )
        fields = [field_view(db, definition) for definition in definitions]
        values = [
            {**operation.state(value), "value": value_of(value)}
            for value in db.scalars(
                select(CustomFieldValue).where(
                    getattr(CustomFieldValue, entity_type + "_id") == identity,
                    CustomFieldValue.definition_id.in_(
                        [definition.id for definition in definitions]
                    ),
                )
            )
        ]
    if enabled(db, "tags"):
        tags = [
            operation.state(tag)
            for tag in db.scalars(
                select(Tag).where(applicable(Tag, department)).order_by(Tag.label, Tag.id)
            )
        ]
        assigned = list(
            db.scalars(
                select(EntityTag.tag_id)
                .join(Tag)
                .where(
                    getattr(EntityTag, entity_type + "_id") == identity,
                    EntityTag.active,
                    applicable(Tag, department),
                )
            )
        )
    return {
        "resource_version": record.version,
        "fields": fields,
        "values": values,
        "tags": tags,
        "tag_ids": assigned,
    }


def metadata_schema(db, user, entity_type, department):
    operation.permit(user, *(("admin", "lider") if entity_type == "task" else ("admin", "gerente")))
    if entity_type == "plan":
        department = None
    elif department is None:
        raise CommandError(422, "DEPARTMENT_REQUIRED")
    if user.role == "lider" and department != user.department_id:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    fields = (
        [
            field_view(db, row)
            for row in db.scalars(
                select(CustomFieldDefinition).where(
                    CustomFieldDefinition.entity_type == entity_type,
                    CustomFieldDefinition.active,
                    applicable(CustomFieldDefinition, department),
                )
            )
        ]
        if enabled(db, "custom_fields")
        else []
    )
    tags = (
        [
            operation.state(row)
            for row in db.scalars(select(Tag).where(Tag.is_active, applicable(Tag, department)))
        ]
        if enabled(db, "tags")
        else []
    )
    return {"fields": fields, "tags": tags, "values": [], "tag_ids": []}


def task_indicators(db, user, task):
    values = {}
    if enabled(db, "dependencies"):
        permitted = operation.scope(select(Task.id).where(Task.completed_at.is_(None)), Task, user)
        values["pending_predecessors"] = db.scalar(
            select(func.count())
            .select_from(TaskDependency)
            .where(
                TaskDependency.successor_task_id == task.id,
                TaskDependency.active,
                TaskDependency.predecessor_task_id.in_(permitted),
            )
        )
    if enabled(db, "impediments"):
        intervals = list(
            db.execute(
                select(TaskImpediment.opened_at, TaskImpediment.closed_at).where(
                    TaskImpediment.task_id == task.id
                )
            ).all()
        )
        values["open_impediments"] = sum(closed is None for _opened, closed in intervals)
        values["impeded_seconds"] = impeded_seconds(intervals, operation.instant(db))
    return values


def ensure_required(db, entity_type, record, *, creating=False, stage_id=None):
    objective = (
        db.get(Objective, record.objective_id)
        if entity_type == "task"
        else record
        if entity_type == "objective"
        else None
    )
    department = objective.department_id if objective else None
    definitions = list(
        db.scalars(
            select(CustomFieldDefinition).where(
                CustomFieldDefinition.entity_type == entity_type,
                CustomFieldDefinition.active,
                applicable(CustomFieldDefinition, department),
            )
        )
    )
    for definition in definitions:
        required = (
            creating
            and definition.required_on_create
            or stage_id is not None
            and stage_id in definition.required_stage_ids
        )
        if not required:
            continue
        value = db.scalar(
            select(CustomFieldValue).where(
                CustomFieldValue.definition_id == definition.id,
                getattr(CustomFieldValue, entity_type + "_id") == record.id,
            )
        )
        if value is None or value_of(value) is None:
            raise CommandError(422, "CUSTOM_FIELD_REQUIRED")
        typed_value(definition, value_of(value), field_options(db, definition))


def store_metadata(db, user, entity_type, record, body, request):
    objective = (
        db.get(Objective, record.objective_id)
        if entity_type == "task"
        else record
        if entity_type == "objective"
        else None
    )
    department = objective.department_id if objective else None
    if "custom_fields" in body.model_fields_set:
        require_module(db, "custom_fields")
        for identity, value in sorted(body.custom_fields.items()):
            definition = db.scalar(
                select(CustomFieldDefinition)
                .where(
                    CustomFieldDefinition.id == identity,
                    CustomFieldDefinition.active,
                    CustomFieldDefinition.entity_type == entity_type,
                    applicable(CustomFieldDefinition, department),
                )
                .with_for_update()
            )
            if definition is None:
                raise CommandError(404, "RESOURCE_NOT_FOUND")
            values = (
                dict.fromkeys(VALUE_COLUMNS)
                if value is None
                else typed_value(definition, value, field_options(db, definition))
            )
            existing = db.scalar(
                select(CustomFieldValue)
                .where(
                    CustomFieldValue.definition_id == identity,
                    getattr(CustomFieldValue, entity_type + "_id") == record.id,
                )
                .with_for_update()
            )
            before = operation.state(existing) if existing else {}
            if existing:
                operation.bump(db, existing)
                for key, entry in values.items():
                    setattr(existing, key, entry)
            else:
                existing = CustomFieldValue(
                    definition_id=identity, **{entity_type + "_id": record.id}, **values
                )
            save_record(
                db,
                user,
                request,
                existing,
                before,
                "metadata_changed",
                getattr(body, "reason", None),
            )
    if "tag_ids" in body.model_fields_set:
        require_module(db, "tags")
        wanted = set(body.tag_ids)
        allowed = set(
            db.scalars(
                select(Tag.id).where(Tag.id.in_(wanted), Tag.is_active, applicable(Tag, department))
            )
        )
        if allowed != wanted:
            raise CommandError(422, "TAG_NOT_APPLICABLE_OR_ACTIVE")
        existing = {
            entry.tag_id: entry
            for entry in db.scalars(
                select(EntityTag)
                .where(getattr(EntityTag, entity_type + "_id") == record.id)
                .order_by(EntityTag.id)
                .with_for_update()
            )
        }
        for identity in sorted(wanted | set(existing)):
            entry = existing.get(identity)
            active = identity in wanted
            if entry and entry.active == active:
                continue
            before = operation.state(entry) if entry else {}
            if entry:
                entry.active = active
                operation.bump(db, entry)
            else:
                entry = EntityTag(
                    tag_id=identity,
                    assigned_by=user.id,
                    active=True,
                    **{entity_type + "_id": record.id},
                )
            save_record(
                db, user, request, entry, before, "metadata_changed", getattr(body, "reason", None)
            )


def write_metadata(db, user, entity_type, identity, body, request):
    record, _plan, _objective = resource(
        db,
        user,
        entity_type,
        identity,
        write=True,
        roles=("admin", "lider") if entity_type == "task" else ("admin", "gerente"),
    )
    check_version(record, body.expected_version)
    before = operation.state(record)
    store_metadata(db, user, entity_type, record, body, request)
    ensure_required(db, entity_type, record, stage_id=getattr(record, "stage_id", None))
    journal(
        db, user, request, record, before, "metadata_changed", body.reason, entity_type=entity_type
    )
    return metadata_view(db, user, entity_type, identity)


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def validate_blueprint(payload, entity_type):
    count = 0

    def visit(node, kind):
        nonlocal count
        count += 1
        if count > 100:
            raise CommandError(413, "TEMPLATE_ENTITY_LIMIT")
        if (
            (kind != "plan" and node.objectives)
            or (kind != "objective" and node.tasks)
            or (kind != "task" and node.subtasks)
        ):
            raise CommandError(422, "TEMPLATE_INVALID_HIERARCHY")
        for child in node.objectives:
            visit(child, "objective")
        for child in node.tasks:
            visit(child, "task")

    visit(payload, entity_type)
    data = payload.model_dump(mode="json")
    if len(json.dumps(data).encode()) > 65536:
        raise CommandError(413, "TEMPLATE_PAYLOAD_LIMIT")
    return data


def write_template(db, user, identity, body, request):
    require_module(db, "templates")
    scope_write(db, user, body, template=True)
    payload = validate_blueprint(body.payload, body.entity_type)
    previous = db.get(Template, identity)
    if previous and any(
        getattr(previous, field) != getattr(body, field)
        for field in ("entity_type", "scope_kind", "department_id")
    ):
        raise CommandError(409, "TEMPLATE_IMMUTABLE_SCOPE")
    values = body.model_dump(exclude={"expected_version", "reason", "payload"})
    values.update(
        name_normalized=body.name.lower(),
        created_by=user.id if previous is None else previous.created_by,
        current_version=previous.current_version + 1 if previous else 1,
    )
    record, before = mutable_record(db, Template, identity, body, values=values)
    save_record(db, user, request, record, before, "template_changed", body.reason)
    version = TemplateVersion(
        template_id=record.id,
        template_version=record.current_version,
        schema_version=1,
        payload=payload,
        payload_hash=canonical_hash(payload),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    return {**operation.state(record), "template_version": operation.state(version)}


def template_version(db, user, identity):
    version = db.get(TemplateVersion, identity)
    if version is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    template = db.scalar(catalog_query(Template, user).where(Template.id == version.template_id))
    if template is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if not template.is_active:
        raise CommandError(409, "TEMPLATE_INACTIVE")
    if version.payload_hash != canonical_hash(version.payload):
        raise CommandError(503, "TEMPLATE_INTEGRITY_FAILURE")
    return template, version


def validate_template_metadata(db, entity_type, department, node):
    definitions = list(
        db.scalars(
            select(CustomFieldDefinition).where(
                CustomFieldDefinition.entity_type == entity_type,
                CustomFieldDefinition.active,
                applicable(CustomFieldDefinition, department),
            )
        )
    )
    by_id = {definition.id: definition for definition in definitions}
    if node.custom_fields:
        require_module(db, "custom_fields")
    for identity, value in node.custom_fields.items():
        definition = by_id.get(identity)
        if definition is None:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        if value is not None:
            typed_value(definition, value, field_options(db, definition))
    stage = (
        db.scalar(
            select(operation.WorkflowStage).where(
                operation.WorkflowStage.is_initial, operation.WorkflowStage.is_active
            )
        )
        if entity_type == "task"
        else None
    )
    for definition in definitions:
        if (
            definition.required_on_create
            or stage is not None
            and stage.id in definition.required_stage_ids
        ) and node.custom_fields.get(definition.id) is None:
            raise CommandError(422, "CUSTOM_FIELD_REQUIRED")
    if node.tag_ids:
        require_module(db, "tags")
        allowed = set(
            db.scalars(
                select(Tag.id).where(
                    Tag.id.in_(node.tag_ids), Tag.is_active, applicable(Tag, department)
                )
            )
        )
        if allowed != set(node.tag_ids):
            raise CommandError(422, "TAG_NOT_APPLICABLE_OR_ACTIVE")


def preview_template(db, user, body):
    from app.schemas.collaboration import Blueprint

    require_module(db, "templates")
    template, version = template_version(db, user, body.template_version_id)
    operation.permit(
        user, *(("admin", "lider") if template.entity_type == "task" else ("admin", "gerente"))
    )
    operation.configuration(db)
    operation.horizon(db, body.horizon_type)
    if body.start_date > body.due_date:
        raise CommandError(422, "INVALID_INTERVAL")
    bindings = {binding.path: binding for binding in body.bindings}
    if len(bindings) != len(body.bindings):
        raise CommandError(422, "TEMPLATE_DUPLICATE_BINDING")
    payload = Blueprint.model_validate(version.payload)
    validate_blueprint(payload, template.entity_type)
    rows = []

    def visit(node, kind, path, start, due, parent_path=None):
        binding = bindings.get(path)
        if binding is None:
            raise CommandError(422, "TEMPLATE_BINDING_REQUIRED")
        if kind != "plan":
            department = (
                db.get(Department, binding.department_id) if binding.department_id else None
            )
            if department is None or not department.is_active:
                raise CommandError(422, "INVALID_DEPARTMENT")
            if template.department_id and template.department_id != department.id:
                raise CommandError(422, "TEMPLATE_SCOPE_MISMATCH")
            if user.role == "lider" and department.id != user.department_id:
                raise CommandError(404, "RESOURCE_NOT_FOUND")
        if kind == "task":
            operation.permit(user, "admin", "lider")
            operation.valid_assignee(db, binding.assignee_id, binding.department_id)
            operation.priority(db, node.priority_id)
        else:
            operation.horizon(db, body.horizon_type if path == "root" else node.horizon_type)
        validate_template_metadata(
            db, kind, binding.department_id if kind != "plan" else None, node
        )
        rows.append(
            {
                "path": path,
                "parent_path": parent_path,
                "entity_type": kind,
                "start_date": start,
                "due_date": due,
                "department_id": binding.department_id,
                "assignee_id": binding.assignee_id,
                "blueprint": node,
            }
        )
        for child_kind, children in (("objective", node.objectives), ("task", node.tasks)):
            for position, child in enumerate(children):
                child_path = (
                    "objectives." + str(position)
                    if kind == "plan"
                    else (path + ".tasks." if path != "root" else "tasks.") + str(position)
                )
                child_start = start + timedelta(days=child.start_offset_days)
                child_due = child_start + timedelta(days=child.duration_days - 1)
                if not start <= child_start <= child_due <= due:
                    raise CommandError(422, "INVALID_INTERVAL")
                visit(child, child_kind, child_path, child_start, child_due, path)
        for child in node.subtasks:
            child_start = start + timedelta(days=child.start_offset_days)
            if child_start + timedelta(days=child.duration_days - 1) > due:
                raise CommandError(422, "INVALID_INTERVAL")

    try:
        visit(payload, template.entity_type, "root", body.start_date, body.due_date)
    except OverflowError:
        raise CommandError(422, "TEMPLATE_DATE_OUT_OF_RANGE") from None
    if set(bindings) != {row["path"] for row in rows}:
        raise CommandError(422, "TEMPLATE_UNUSED_BINDING")
    if template.entity_type == "plan":
        if body.annual_plan_id is not None or body.objective_id is not None:
            raise CommandError(422, "TEMPLATE_INVALID_PARENT")
        if body.expected_version != 0:
            raise CommandError(409, "VERSION_CONFLICT")
        if any(row["entity_type"] == "task" for row in rows) and not body.activate_plan:
            raise CommandError(422, "TEMPLATE_ACTIVE_PLAN_REQUIRED")
    else:
        parent_kind = "plan" if template.entity_type == "objective" else "objective"
        parent_id = body.annual_plan_id if parent_kind == "plan" else body.objective_id
        if parent_id is None or (
            body.objective_id is not None
            if parent_kind == "plan"
            else body.annual_plan_id is not None
        ):
            raise CommandError(422, "TEMPLATE_INVALID_PARENT")
        parent, plan, parent_objective = resource(db, user, parent_kind, parent_id)
        check_version(parent, body.expected_version)
        operation.open_plan(plan, active=template.entity_type == "task")
        operation.contained(body.start_date, body.due_date, body.due_date, parent)
        if parent_objective and rows[0]["department_id"] != parent_objective.department_id:
            raise CommandError(422, "TEMPLATE_SCOPE_MISMATCH")
    return template, version, rows


def instantiate_template(db, user, body, request):
    from app.schemas.operations import (
        ObjectiveCreate,
        PlanCreate,
        StatusChange,
        SubtaskCreate,
        TaskCreate,
    )

    template, version, rows = preview_template(db, user, body)
    operation.lock_rows(
        db, Department, {row["department_id"] for row in rows if row["department_id"]}
    )
    operation.lock_rows(
        db, User, {user.id} | {row["assignee_id"] for row in rows if row["assignee_id"]}
    )
    if template.entity_type != "plan":
        parent_kind = "plan" if template.entity_type == "objective" else "objective"
        parent_id = body.annual_plan_id if parent_kind == "plan" else body.objective_id
        parent, plan, parent_objective = resource(db, user, parent_kind, parent_id, write=True)
        check_version(parent, body.expected_version)
        operation.open_plan(plan, active=template.entity_type == "task")
        operation.contained(body.start_date, body.due_date, body.due_date, parent)
        if parent_objective and rows[0]["department_id"] != parent_objective.department_id:
            raise CommandError(422, "TEMPLATE_SCOPE_MISMATCH")
    created = {}
    for row in rows:
        node, kind = row["blueprint"], row["entity_type"]
        values = {"title": node.title, "start_date": row["start_date"], "due_date": row["due_date"]}
        if node.custom_fields:
            values["custom_fields"] = node.custom_fields
        if node.tag_ids:
            values["tag_ids"] = node.tag_ids
        if kind != "task":
            values["horizon_type"] = (
                body.horizon_type if row["path"] == "root" else node.horizon_type
            )
        if kind == "plan":
            result = operation.create_plan(
                db, user, PlanCreate(**values), request, template_version_id=version.id
            )
        elif kind == "objective":
            parent_id = (
                created[row["parent_path"]]["id"] if row["parent_path"] else body.annual_plan_id
            )
            result = operation.create_objective(
                db,
                user,
                ObjectiveCreate(
                    **values,
                    annual_plan_id=parent_id,
                    department_id=row["department_id"],
                    description=node.description,
                ),
                request,
                template_version_id=version.id,
            )
        else:
            if template.entity_type == "plan":
                plan = db.get(AnnualPlan, created["root"]["id"])
                if plan.status == "draft":
                    operation.update_planning(
                        db,
                        user,
                        plan,
                        StatusChange(
                            expected_version=plan.version, status="active", reason=body.reason
                        ),
                        request,
                        "status_changed",
                    )
            parent_id = (
                created[row["parent_path"]]["id"] if row["parent_path"] else body.objective_id
            )
            result = operation.create_task(
                db,
                user,
                TaskCreate(
                    **values,
                    objective_id=parent_id,
                    assignee_id=row["assignee_id"],
                    description=node.description,
                    priority_id=node.priority_id,
                ),
                request,
                template_version_id=version.id,
            )
            task = db.get(Task, UUID(str(result["id"])))
            for child in node.subtasks:
                start = row["start_date"] + timedelta(days=child.start_offset_days)
                operation.change_subtask(
                    db,
                    user,
                    task.id,
                    SubtaskCreate(
                        expected_version=task.version,
                        title=child.title,
                        start_date=start,
                        due_date=start + timedelta(days=child.duration_days - 1),
                    ),
                    request,
                    "subtask_created",
                )
            result = operation.task_view(db, task, user)
        created[row["path"]] = result
    if template.entity_type == "plan" and body.activate_plan:
        plan = db.get(AnnualPlan, UUID(str(created["root"]["id"])))
        if plan.status == "draft":
            operation.update_planning(
                db,
                user,
                plan,
                StatusChange(expected_version=plan.version, status="active", reason=body.reason),
                request,
                "status_changed",
            )
        created["root"] = operation.plan_view(db, plan, user)
    return {"items": [{"path": path, "resource": entry} for path, entry in created.items()]}


def write_principal(db, user, identity, body, request):
    require_module(db, "recurrence")
    operation.permit(user, "admin")
    if len(set(body.department_ids)) != len(body.department_ids) or len(
        set(body.approved_scopes)
    ) != len(body.approved_scopes):
        raise CommandError(422, "PRINCIPAL_DUPLICATE_SCOPE")
    allowed = set(
        db.scalars(
            select(Department.id).where(
                Department.id.in_(body.department_ids), Department.is_active
            )
        )
    )
    if allowed != set(body.department_ids):
        raise CommandError(422, "INVALID_DEPARTMENT")
    previous = db.get(ServicePrincipal, identity)
    values = body.model_dump(exclude={"expected_version", "reason"})
    values.update(
        token_version=previous.token_version + 1 if previous else 1,
        created_by=previous.created_by if previous else user.id,
    )
    record, before = mutable_record(db, ServicePrincipal, identity, body, values=values)
    save_record(db, user, request, record, before, "principal_changed", body.reason)
    return operation.state(record)


def schedule_scope(user):
    principal = getattr(user, "actor_service_id", None)
    if principal is not None:
        return select(RecurrenceSchedule).where(
            RecurrenceSchedule.owner_user_id == user.id,
            RecurrenceSchedule.service_principal_id == principal,
        )
    operation.permit(user, "admin", "lider")
    query = select(RecurrenceSchedule)
    if user.role == "lider":
        query = query.where(
            RecurrenceSchedule.owner_user_id == user.id,
            RecurrenceSchedule.objective_id.in_(
                select(Objective.id).where(Objective.department_id == user.department_id)
            ),
        )
    return query


def save_schedule(db, user, identity, body, request):
    from app.services.enterprise import calendar_effective

    require_module(db, "recurrence")
    require_module(db, "calendar")
    require_module(db, "templates")
    operation.permit(user, "admin", "lider")
    previous = db.scalar(schedule_scope(user).where(RecurrenceSchedule.id == identity))
    if previous is None and db.get(RecurrenceSchedule, identity):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    objective, plan, _objective = resource(db, user, "objective", body.objective_id)
    operation.lock_context(db, user, objective=objective)
    if previous is not None:
        operation.lock_rows(db, RecurrenceSchedule, [identity])
        check_version(previous, body.expected_version)
    submitted = body.model_dump(mode="json", exclude={"expected_version", "reason", "enabled"})
    changed = previous is not None and any(
        operation.state(previous)[key] != value for key, value in submitted.items()
    )
    used = (
        previous is not None
        and db.scalar(
            select(RecurrenceOccurrence.id)
            .where(RecurrenceOccurrence.schedule_id == identity)
            .limit(1)
        )
        is not None
    )
    if used and changed:
        raise CommandError(409, "RECURRENCE_USED_RULE_IMMUTABLE")
    if previous is not None and not body.enabled and not changed:
        record, before = mutable_record(
            db, RecurrenceSchedule, identity, body, values={"enabled": False}
        )
        save_record(db, user, request, record, before, "recurrence_changed", body.reason)
        return operation.state(record)
    operation.open_plan(plan, active=True)
    if user.role == "lider" and body.owner_user_id != user.id:
        raise CommandError(403, "FORBIDDEN")
    owner = db.get(User, body.owner_user_id)
    if (
        owner is None
        or not owner.is_active
        or owner.role not in {"admin", "lider"}
        or owner.role == "lider"
        and owner.department_id != objective.department_id
    ):
        raise CommandError(422, "INVALID_RECURRENCE_OWNER")
    operation.valid_assignee(db, body.assignee_id, objective.department_id)
    principal = db.get(ServicePrincipal, body.service_principal_id)
    template, version = template_version(db, owner, body.template_version_id)
    if (
        principal is None
        or not principal.is_active
        or "tasks:create" not in principal.approved_scopes
        or objective.department_id not in principal.department_ids
        or template.entity_type != "task"
        or template.department_id not in {None, objective.department_id}
        or version.payload.get("subtasks")
        and "subtasks:create" not in principal.approved_scopes
    ):
        raise CommandError(422, "RECURRENCE_SCOPE_NOT_APPROVED")
    selected, calendar_ids = calendar_effective(db, objective.department_id)
    if selected.id != body.calendar_id:
        raise CommandError(422, "CALENDAR_SCOPE_MISMATCH")
    calendars = list(db.scalars(select(CalendarConfig).where(CalendarConfig.id.in_(calendar_ids))))
    holidays = list(
        db.scalars(
            select(CalendarHoliday).where(
                CalendarHoliday.calendar_id.in_(calendar_ids), CalendarHoliday.is_active
            )
        )
    )
    if previous is None and body.enabled:
        raise CommandError(422, "RECURRENCE_CREATE_DISABLED")
    if previous and previous.owner_user_id != body.owner_user_id:
        raise CommandError(409, "RECURRENCE_OWNER_IMMUTABLE")
    values = body.model_dump(exclude={"expected_version", "reason"})
    values.update(
        timezone=str(operation.timezone(db)),
        configuration_revision_id=selected.configuration_revision_id,
        calendar_snapshot={
            "weekday_mask": selected.weekday_mask,
            "holidays": sorted(holiday.holiday_date.isoformat() for holiday in holidays),
            "calendar_versions": [
                {
                    "id": str(calendar.id),
                    "version": calendar.version,
                    "configuration_revision_id": str(calendar.configuration_revision_id),
                }
                for calendar in calendars
            ],
        },
        next_due_at=body.start_date,
    )
    if used:
        for key in ("timezone", "configuration_revision_id", "calendar_snapshot"):
            values[key] = getattr(previous, key)
    if previous is not None and not changed:
        values["next_due_at"] = previous.next_due_at
    record, before = mutable_record(db, RecurrenceSchedule, identity, body, values=values)
    save_record(db, user, request, record, before, "recurrence_changed", body.reason)
    return operation.state(record)


def recurrence_context_approved(
    schedule, plan, objective, owner, principal, template, version, assignee
):
    return bool(
        schedule.enabled
        and plan.status == "active"
        and owner
        and owner.is_active
        and owner.role in {"admin", "lider"}
        and (owner.role == "admin" or owner.department_id == objective.department_id)
        and principal
        and principal.is_active
        and objective.department_id in principal.department_ids
        and "tasks:create" in principal.approved_scopes
        and template
        and template.is_active
        and template.entity_type == "task"
        and template.department_id in {None, objective.department_id}
        and version
        and (not version.payload.get("subtasks") or "subtasks:create" in principal.approved_scopes)
        and assignee
        and assignee.is_active
        and assignee.role != "gerente"
        and assignee.department_id == objective.department_id
    )


def run_schedule(db, user, identity, body, request):
    from app.schemas.collaboration import InstantiateTemplate, RecurrenceRule

    require_module(db, "recurrence")
    require_module(db, "templates")
    schedule = db.scalar(schedule_scope(user).where(RecurrenceSchedule.id == identity))
    if schedule is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if getattr(user, "actor_service_id", None) is not None:
        objective = db.get(Objective, schedule.objective_id)
        plan = db.get(AnnualPlan, objective.annual_plan_id)
    else:
        objective, plan, _objective = resource(db, user, "objective", schedule.objective_id)
    operation.lock_context(db, user, objective=objective)
    operation.lock_rows(db, RecurrenceSchedule, [identity])
    digest = canonical_hash(
        {
            "schedule_id": str(identity),
            **body.model_dump(mode="json", exclude={"expected_version", "reason"}),
        }
    )
    existing = db.scalar(
        select(JobRun).where(
            JobRun.kind == "recurrence",
            JobRun.owner_user_id == schedule.owner_user_id,
            JobRun.idempotency_key == body.idempotency_key,
        )
    )
    if existing:
        if existing.input_hash != digest:
            raise CommandError(409, "IDEMPOTENCY_KEY_REUSED")
        return {
            "job": operation.state(existing),
            "schedule": operation.state(schedule),
            "generated_ids": list(
                db.scalars(
                    select(RecurrenceOccurrence.task_id).where(
                        RecurrenceOccurrence.job_id == existing.id,
                        RecurrenceOccurrence.task_id.is_not(None),
                    )
                )
            ),
            "processed_count": 0,
            "replayed": True,
        }
    check_version(schedule, body.expected_version)
    today = operation.instant(db).astimezone(ZoneInfo(schedule.timezone)).date()
    if body.through_date > today:
        raise CommandError(422, "RECURRENCE_FUTURE_RUN")
    owner = db.get(User, schedule.owner_user_id)
    principal = db.get(ServicePrincipal, schedule.service_principal_id)
    if owner is None or principal is None:
        raise CommandError(503, "RECURRENCE_CONTEXT_INTEGRITY_FAILURE")
    version = db.get(TemplateVersion, schedule.template_version_id)
    template = (
        db.scalar(catalog_query(Template, owner).where(Template.id == version.template_id))
        if version and owner.role in {"admin", "lider"}
        else None
    )
    assignee = db.get(User, schedule.assignee_id)
    if version is not None and version.payload_hash != canonical_hash(version.payload):
        raise CommandError(503, "TEMPLATE_INTEGRITY_FAILURE")
    permitted = recurrence_context_approved(
        schedule, plan, objective, owner, principal, template, version, assignee
    )
    actor = SimpleNamespace(
        id=owner.id,
        role=owner.role,
        department_id=owner.department_id,
        actor_service_id=principal.id,
    )
    moment = operation.instant(db)
    job = JobRun(
        kind="recurrence",
        owner_user_id=owner.id,
        service_principal_id=principal.id,
        request_id=UUID(request.state.request_id),
        idempotency_key=body.idempotency_key,
        input_hash=digest,
        state="running",
        attempt=1,
        retry_of_id=None,
        lease_token=uuid4(),
        lease_until=moment + timedelta(minutes=5),
        next_run_at=None,
        configuration_revision_id=schedule.configuration_revision_id,
    )
    save_record(db, user, request, job, {}, "recurrence_started", body.reason)
    schedule_before = operation.state(schedule)
    generated, processed = [], 0
    next_due_at = schedule.next_due_at
    if permitted:
        rule = RecurrenceRule.model_validate(
            {key: operation.state(schedule)[key] for key in RecurrenceRule.model_fields}
        )
        last = db.scalar(
            select(func.max(RecurrenceOccurrence.scheduled_for)).where(
                RecurrenceOccurrence.schedule_id == identity
            )
        )
        iterator = occurrence_dates(rule, schedule.calendar_snapshot, after=last)
        processed, next_due_at = 0, None
        for scheduled, effective, skipped in iterator:
            if scheduled > body.through_date or processed >= body.limit:
                next_due_at = scheduled
                break
            task_id = None
            if effective < today and rule.missed_policy == "skip":
                skipped = True
            if not skipped:
                end = effective + timedelta(days=version.payload["duration_days"] - 1)
                result = instantiate_template(
                    db,
                    actor,
                    InstantiateTemplate(
                        expected_version=objective.version,
                        reason=body.reason,
                        template_version_id=version.id,
                        start_date=effective.isoformat(),
                        due_date=end.isoformat(),
                        horizon_type=version.payload["horizon_type"],
                        annual_plan_id=None,
                        objective_id=objective.id,
                        activate_plan=False,
                        bindings=[
                            {
                                "path": "root",
                                "department_id": objective.department_id,
                                "assignee_id": schedule.assignee_id,
                            }
                        ],
                    ),
                    request,
                )
                task_id = UUID(str(result["items"][0]["resource"]["id"]))
                task = db.get(Task, task_id)
                operation.history(
                    db,
                    request,
                    actor,
                    task,
                    {},
                    "recurrence_generated",
                    body.reason,
                    details={"schedule_id": schedule.id, "job_id": job.id},
                )
                outbox(db, actor, "task", task, objective, "recurrence_generated")
                generated.append(task_id)
            db.add(
                RecurrenceOccurrence(
                    schedule_id=schedule.id,
                    job_id=job.id,
                    scheduled_for=scheduled,
                    effective_date=effective,
                    timezone=schedule.timezone,
                    calendar_revision_id=schedule.configuration_revision_id,
                    result="skipped" if skipped else "generated",
                    task_id=task_id,
                )
            )
            db.flush()
            processed += 1
    job_before = operation.state(job)
    job.state = "succeeded" if permitted else "paused"
    job.lease_token = job.lease_until = None
    operation.bump(db, job)
    save_record(db, user, request, job, job_before, "recurrence_finished", body.reason)
    schedule.enabled = schedule.enabled and permitted
    schedule.next_due_at = next_due_at
    operation.bump(db, schedule)
    save_record(db, user, request, schedule, schedule_before, "recurrence_run", body.reason)
    return {
        "job": operation.state(job),
        "schedule": operation.state(schedule),
        "generated_ids": generated,
        "processed_count": processed,
        "replayed": False,
    }


def filter_resource(db, user, query, model, entity_type, filters):
    for tag_id in filters.tag_ids:
        require_module(db, "tags")
        query = query.where(
            select(EntityTag.id)
            .join(Tag)
            .where(
                EntityTag.tag_id == tag_id,
                EntityTag.active,
                Tag.is_active,
                getattr(EntityTag, entity_type + "_id") == model.id,
            )
            .exists()
        )
    for entry in filters.custom_fields:
        require_module(db, "custom_fields")
        definition = db.get(CustomFieldDefinition, entry.definition_id)
        if definition is None or not definition.active or definition.entity_type != entity_type:
            query = query.where(False)
            continue
        if user.role in {"lider", "colaborador"} and definition.department_id not in {
            None,
            user.department_id,
        }:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        values = typed_value(definition, entry.value, field_options(db, definition))
        column_name = next(key for key, value in values.items() if value is not None)
        column, value = getattr(CustomFieldValue, column_name), values[column_name]
        if entry.operator == "eq":
            condition = column == value
        elif entry.operator in {"gte", "lte"} and column_name in {"number_value", "date_value"}:
            condition = column >= value if entry.operator == "gte" else column <= value
        elif entry.operator == "contains" and column_name == "text_value":
            condition = func.strpos(func.lower(column), value.lower()) > 0
        elif entry.operator == "contains" and column_name == "option_ids":
            condition = column.contains(value)
        else:
            raise CommandError(422, "CUSTOM_FIELD_FILTER_OPERATOR")
        query = query.where(
            select(CustomFieldValue.id)
            .where(
                CustomFieldValue.definition_id == definition.id,
                getattr(CustomFieldValue, entity_type + "_id") == model.id,
                condition,
            )
            .exists()
        )
    if entity_type == "task":
        if filters.assignee_id:
            query = query.where(Task.assignee_id == filters.assignee_id)
        if filters.stage_id:
            query = query.where(Task.stage_id == filters.stage_id)
        if filters.blocked is not None:
            require_module(db, "impediments")
            blocked = (
                select(TaskImpediment.id)
                .where(TaskImpediment.task_id == Task.id, TaskImpediment.closed_at.is_(None))
                .exists()
            )
            query = query.where(blocked if filters.blocked else ~blocked)
    elif any(
        value is not None for value in (filters.assignee_id, filters.stage_id, filters.blocked)
    ):
        query = query.where(False)
    return query


def execution_filter(db, user, query, raw):
    from pydantic import ValidationError

    from app.schemas.collaboration import SearchFilters

    if not raw:
        return query
    require_module(db, "search")
    try:
        filters = SearchFilters.model_validate_json(raw)
    except ValidationError:
        raise CommandError(422, "INVALID_SEARCH_FILTERS") from None
    if filters.entity_type not in {None, "task"}:
        raise CommandError(422, "TASK_FILTER_REQUIRED")
    query = filter_resource(db, user, query, Task, "task", filters)
    if filters.q:
        config = literal_column("'spanish'")
        query = query.where(
            func.to_tsvector(config, Task.title + literal(" ") + Task.description).op("@@")(
                func.websearch_to_tsquery(config, filters.q)
            )
        )
    return query


def search_union(db, user, filters):
    kinds = (
        [filters.entity_type] if filters.entity_type else ["plan", "objective", "task", "comment"]
    )
    if user.role == "colaborador" and filters.entity_type in {"plan", "objective"}:
        raise CommandError(403, "FORBIDDEN")
    queries = []
    configuration = literal_column("'spanish'")
    needle = func.websearch_to_tsquery(configuration, filters.q)
    for kind in kinds:
        if kind in {"plan", "objective"} and user.role == "colaborador":
            continue
        if kind == "comment":
            if not enabled(db, "comments"):
                continue
            tasks = filter_resource(
                db, user, operation.scope(select(Task.id), Task, user), Task, "task", filters
            )
            allowed = Comment.task_id.in_(tasks)
            if user.role != "colaborador":
                objectives = filter_resource(
                    db,
                    user,
                    operation.scope(select(Objective.id), Objective, user),
                    Objective,
                    "objective",
                    filters,
                )
                allowed = or_(allowed, Comment.objective_id.in_(objectives))
            document = CommentRevision.body
            base = select(
                Comment.id.label("id"),
                literal(kind).label("entity_type"),
                document.label("document"),
                Comment.task_id.label("task_id"),
                Comment.objective_id.label("objective_id"),
            ).join(
                CommentRevision,
                and_(
                    CommentRevision.comment_id == Comment.id,
                    CommentRevision.revision_no == Comment.current_revision,
                ),
            )
            base = base.where(allowed, Comment.annulled_at.is_(None))
        else:
            model = ENTITY_MODELS[kind]
            document = (
                model.title if kind == "plan" else model.title + literal(" ") + model.description
            )
            base = operation.scope(
                select(
                    model.id.label("id"),
                    literal(kind).label("entity_type"),
                    document.label("document"),
                    (model.id if kind == "task" else cast(literal(None), Task.id.type)).label(
                        "task_id"
                    ),
                    (
                        model.id
                        if kind == "objective"
                        else Task.objective_id
                        if kind == "task"
                        else cast(literal(None), Objective.id.type)
                    ).label("objective_id"),
                ),
                model,
                user,
            )
            base = filter_resource(db, user, base, model, kind, filters)
        authorized = base.subquery()
        vector = func.to_tsvector(configuration, authorized.c.document)
        rank = cast(func.ts_rank_cd(vector, needle) * 1000000, Integer) if filters.q else literal(0)
        result = select(
            authorized.c.id,
            authorized.c.entity_type,
            authorized.c.task_id,
            authorized.c.objective_id,
            func.substr(authorized.c.document, 1, 180).label("snippet"),
            rank.label("score"),
        )
        if filters.q:
            result = result.where(vector.op("@@")(needle))
        queries.append(result)
    return union_all(*queries).subquery("authorized_search")


def search(db, user, filters, limit, cursor=None):
    require_module(db, "search")
    require_page_size(db, limit)
    results = search_union(db, user, filters)
    query = select(results)
    fingerprint = canonical_hash(filters.model_dump(mode="json"))
    if cursor:
        try:
            position = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if (
                set(position) != {"filter", "user", "score", "kind", "id"}
                or position["filter"] != fingerprint
                or position["user"] != str(user.id)
                or type(position["score"]) is not int
                or position["kind"] not in {"plan", "objective", "task", "comment"}
            ):
                raise ValueError
            identity = UUID(position["id"])
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise CommandError(422, "INVALID_SEARCH_CURSOR") from None
        query = query.where(
            or_(
                results.c.score < position["score"],
                and_(
                    results.c.score == position["score"],
                    or_(
                        results.c.entity_type > position["kind"],
                        and_(results.c.entity_type == position["kind"], results.c.id > identity),
                    ),
                ),
            )
        )
    rows = list(
        db.execute(
            query.order_by(results.c.score.desc(), results.c.entity_type, results.c.id).limit(
                limit + 1
            )
        ).mappings()
    )
    following = None
    if len(rows) > limit:
        last = rows[limit - 1]
        following = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "filter": fingerprint,
                    "user": str(user.id),
                    "score": last["score"],
                    "kind": last["entity_type"],
                    "id": str(last["id"]),
                }
            ).encode()
        ).decode()
    counts = dict(
        db.execute(
            select(results.c.entity_type, func.count()).group_by(results.c.entity_type)
        ).all()
    )
    return {
        "items": [dict(row) for row in rows[:limit]],
        "next_cursor": following,
        "counts": counts,
    }


def saved_view_query(user):
    scopes = [SavedView.owner_id == user.id]
    if user.role in {"admin", "gerente"}:
        scopes += [SavedView.scope_kind == "organization", SavedView.scope_kind == "department"]
    elif user.role == "lider":
        scopes.append(
            and_(
                SavedView.scope_kind == "department", SavedView.department_id == user.department_id
            )
        )
    return select(SavedView).where(or_(*scopes))


def save_view(db, user, identity, body, request):
    require_module(db, "saved_views")
    if (
        (body.scope_kind == "department") != (body.department_id is not None)
        or body.scope_kind == "department"
        and user.role not in {"admin", "lider"}
        or body.scope_kind == "organization"
        and user.role not in {"admin", "gerente"}
        or body.scope_kind == "department"
        and user.role == "lider"
        and body.department_id != user.department_id
    ):
        raise CommandError(403, "FORBIDDEN")
    if body.department_id:
        department = db.get(Department, body.department_id)
        if department is None or not department.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")
    filters = body.filters.model_copy(update={"entity_type": body.entity_type})
    search_union(db, user, filters)
    existing = db.scalar(saved_view_query(user).where(SavedView.id == identity))
    if existing is None and db.get(SavedView, identity):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if existing and existing.owner_id != user.id and user.role != "admin":
        raise CommandError(403, "FORBIDDEN")
    if existing and any(
        getattr(existing, field) != getattr(body, field)
        for field in ("entity_type", "scope_kind", "department_id")
    ):
        raise CommandError(409, "SAVED_VIEW_IMMUTABLE_SCOPE")
    values = body.model_dump(exclude={"expected_version", "reason", "filters"})
    values.update(
        owner_id=existing.owner_id if existing else user.id,
        filter_schema_version=1,
        filters=filters.model_dump(mode="json"),
    )
    record, before = mutable_record(db, SavedView, identity, body, values=values)
    save_record(db, user, request, record, before, "saved_view_changed", body.reason)
    return operation.state(record)
