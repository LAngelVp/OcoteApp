from datetime import timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.notifications import quiet_until, send
from app.core.security import now
from app.models.collaboration import (
    Comment,
    CommentMention,
    CommentRevision,
    OutboxEvent,
    ServicePrincipal,
)
from app.models.enterprise import CalendarHoliday
from app.models.evaluations import Evaluation
from app.models.identity import User
from app.models.notifications import (
    Notification,
    NotificationConnector,
    NotificationDelivery,
    NotificationDispatch,
    NotificationPreference,
    NotificationRule,
)
from app.models.operations import Objective, Task
from app.services import enterprise, notifications, operations
from app.services.identity import audit, config_lock, touch

TRIGGERS = {"mention": "comment_changed", "impediment": "impediment_changed"}


def checked_budget(value):
    if type(value) is not int or not 1 <= value <= 100:
        raise CommandError(422, "NOTIFICATION_BUDGET_INVALID")
    return value


def context(db, identity):
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise CommandError(503, "MAINTENANCE")
    config_lock(db, exclusive=False)
    if db.scalar(text("SELECT current_user")) != "ocote_runtime":
        raise CommandError(503, "RUNTIME_IDENTITY_REQUIRED")
    if db.scalar(text("SELECT version_num FROM alembic_version")) not in {
        "20261126_0009", "20261126_0010", "20261126_0011",
    }:
        raise CommandError(503, "F10_REVISION_REQUIRED")
    actor = db.get(ServicePrincipal, identity)
    if (
        actor is None
        or not actor.is_active
        or not actor.department_ids
        or "notifications:dispatch" not in actor.approved_scopes
    ):
        raise CommandError(403, "NOTIFICATION_SERVICE_SCOPE_REQUIRED")
    return actor


def changed(db, record, actor, request, keys):
    audit(
        db,
        request,
        "administration_changed",
        actor_service=actor.id,
        entity=record.__tablename__,
        entity_id=record.id,
        after={"version": record.version, "changed_keys": keys},
    )
    db.add(record)
    db.flush()


def can_view(db, actor, event):
    if not actor.is_active:
        return False
    if event.task_id:
        query = operations.scope(select(Task.id).where(Task.id == event.task_id), Task, actor)
        return db.scalar(query) is not None
    if actor.role == "colaborador":
        return False
    if event.objective_id:
        query = operations.scope(
            select(Objective.id).where(Objective.id == event.objective_id), Objective, actor
        )
        return db.scalar(query) is not None
    query = select(Evaluation.id).where(
        Evaluation.id == event.evaluation_id, Evaluation.status == "final"
    )
    if actor.role == "lider":
        query = query.where(Evaluation.department_id == actor.department_id)
    return db.scalar(query) is not None


def recipient_query(db, rule, event):
    query = select(User).where(User.is_active)
    if rule.recipient_mode == "admins":
        return query.where(User.role == "admin")
    if rule.recipient_mode == "department_leaders":
        return query.where(User.role == "lider", User.department_id == event.department_id)
    if rule.recipient_mode == "mentioned":
        mentioned = (
            select(CommentMention.mentioned_user_id)
            .join(CommentRevision, CommentMention.comment_revision_id == CommentRevision.id)
            .join(Comment, CommentRevision.comment_id == Comment.id)
            .where(
                CommentMention.notification_event_id == event.id,
                Comment.annulled_at.is_(None),
                Comment.current_revision == CommentRevision.revision_no,
            )
        )
        return query.where(User.id.in_(mentioned))
    identity = None
    if rule.recipient_mode == "assignee" and event.task_id:
        identity = db.scalar(select(Task.assignee_id).where(Task.id == event.task_id))
        if event.event_type == "assignment" and event.payload.get("owner_user_id") != str(identity):
            identity = None
    elif rule.recipient_mode == "evaluator" and event.evaluation_id:
        identity = db.scalar(
            select(Evaluation.evaluator_id).where(Evaluation.id == event.evaluation_id)
        )
    elif rule.recipient_mode == "requester":
        try:
            identity = UUID(event.payload.get("requester_id", ""))
        except (ValueError, TypeError, AttributeError):
            pass
    return query.where(User.id == identity) if identity else query.where(False)


def chosen_channels(db, rule, preference):
    if preference is None or not preference.opt_in:
        return set()
    channels = set(rule.channels) & set(preference.channels)
    if not enterprise.enabled(db, "integrations"):
        channels &= {"in_app"}
    if not enterprise.enabled(db, "email_notifications"):
        channels.discard("email")
    if not enterprise.enabled(db, "corporate_messaging"):
        channels.discard("messaging")
    return channels


def usable_connector(record, event, channel):
    return (
        record is not None
        and record.is_active
        and record.config.get("audience_approved") is True
        and record.department_id in {None, event.department_id}
        and ("email" if record.provider == "smtp" else "messaging") == channel
    )


def dispatch_one(db, principal, rule_id, request):
    if not enterprise.enabled(db, "notifications"):
        return False
    rule = db.scalar(
        select(NotificationRule)
        .where(
            NotificationRule.id == rule_id,
            NotificationRule.enabled,
            or_(
                NotificationRule.department_id.is_(None),
                NotificationRule.department_id.in_(principal.department_ids),
            ),
        )
        .with_for_update(skip_locked=True)
    )
    if rule is None:
        return False
    delivered = exists(
        select(NotificationDispatch.id).where(
            NotificationDispatch.outbox_id == OutboxEvent.id,
            NotificationDispatch.rule_id == rule.id,
            NotificationDispatch.rule_version == rule.version,
        )
    )
    event = db.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.event_type == TRIGGERS.get(rule.trigger, rule.trigger),
            OutboxEvent.department_id.in_(principal.department_ids),
            OutboxEvent.created_at
            >= max(rule.updated_at, now() - timedelta(hours=rule.max_age_hours)),
            or_(
                OutboxEvent.payload["rule_id"].astext.is_(None),
                OutboxEvent.payload["rule_id"].astext == str(rule.id),
            ),
            ~delivered,
            *([OutboxEvent.department_id == rule.department_id] if rule.department_id else []),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(1)
    )
    if event is None:
        return False
    users = list(db.scalars(recipient_query(db, rule, event).order_by(User.id).limit(1001)))
    if len(users) > 1000:
        raise CommandError(413, "NOTIFICATION_RECIPIENT_LIMIT_EXCEEDED")
    recipient_count, moment = 0, now()
    for user in users:
        if not can_view(db, user, event):
            continue
        preference = db.scalar(
            select(NotificationPreference).where(NotificationPreference.user_id == user.id)
        )
        channels = chosen_channels(db, rule, preference)
        if not channels:
            continue
        available = quiet_until(
            moment, preference.quiet_start, preference.quiet_end, preference.timezone
        )
        expires = event.created_at + timedelta(hours=rule.max_age_hours)
        if available >= expires:
            continue
        connectors = []
        for connector_id in rule.connector_ids:
            connector = db.get(NotificationConnector, connector_id)
            channel = "email" if connector and connector.provider == "smtp" else "messaging"
            if channel in channels and usable_connector(connector, event, channel):
                connectors.append((connector, channel))
        if "in_app" not in channels and not connectors:
            continue
        resource = event.task_id or event.objective_id or event.evaluation_id
        resource_type = (
            "task" if event.task_id else "objective" if event.objective_id else "evaluation"
        )
        notice = Notification(
            id=uuid4(),
            version=1,
            user_id=user.id,
            outbox_id=event.id,
            rule_id=rule.id,
            rule_version=rule.version,
            safe_projection={
                "trigger": rule.trigger,
                "resource_id": str(resource),
                "resource_type": resource_type,
            },
            in_app="in_app" in channels,
            available_at=available,
            read_at=None,
            expires_at=expires,
        )
        changed(db, notice, principal, request, ["created"])
        for connector, channel in connectors:
            delivery = NotificationDelivery(
                id=uuid4(),
                version=1,
                notification_id=notice.id,
                connector_id=connector.id,
                config_revision=connector.config_revision,
                channel=channel,
                attempt_no=1,
                state="pending",
                result_code=None,
                next_attempt_at=available,
                lease_token=None,
                lease_until=None,
            )
            changed(db, delivery, principal, request, ["queued"])
        recipient_count += 1
    db.add(
        NotificationDispatch(
            outbox_id=event.id,
            rule_id=rule.id,
            rule_version=rule.version,
            recipient_count=recipient_count,
        )
    )
    db.flush()
    return True


def date_event_id(rule, task, day):
    return uuid5(NAMESPACE_URL, f"ocote:f10:{rule.id}:{rule.version}:{task.id}:{day.isoformat()}")


def scan_dates(db, principal, budget):
    if not enterprise.enabled(db, "notifications"):
        return 0
    rules = list(
        db.scalars(
            select(NotificationRule)
            .where(
                NotificationRule.enabled,
                NotificationRule.trigger.in_(["upcoming_due", "overdue"]),
                or_(
                    NotificationRule.department_id.is_(None),
                    NotificationRule.department_id.in_(principal.department_ids),
                ),
            )
            .order_by(NotificationRule.id)
            .limit(101)
        )
    )
    if len(rules) > 100:
        raise CommandError(413, "NOTIFICATION_DATE_RULE_LIMIT_EXCEEDED")
    created, moment = 0, now()
    today = moment.astimezone(operations.timezone(db)).date() if rules else None
    calendars = {}
    for rule in rules:
        tasks = list(
            db.execute(
                select(Task, Objective.department_id)
                .join(Objective)
                .where(
                    Task.completed_at.is_(None),
                    Objective.department_id.in_(principal.department_ids),
                    *(
                        [Objective.department_id == rule.department_id]
                        if rule.department_id
                        else []
                    ),
                )
                .order_by(Task.id)
                .limit(10001)
            )
        )
        if len(tasks) > 10000:
            raise CommandError(413, "NOTIFICATION_DATE_TASK_LIMIT_EXCEEDED")
        for task, department in tasks:
            if created >= budget:
                return created
            start = today if rule.trigger == "upcoming_due" else task.due_date
            mask, holidays = 127, set()
            if rule.day_basis == "business":
                enterprise.require_module(db, "calendar")
                if department not in calendars:
                    selected, identities = enterprise.calendar_effective(db, department)
                    days = list(
                        db.scalars(
                            select(CalendarHoliday.holiday_date)
                            .where(
                                CalendarHoliday.calendar_id.in_(identities),
                                CalendarHoliday.is_active,
                            )
                            .limit(10001)
                        )
                    )
                    if len(days) > 10000:
                        raise CommandError(413, "NOTIFICATION_HOLIDAY_LIMIT_EXCEEDED")
                    calendars[department] = selected.weekday_mask, set(days)
                mask, holidays = calendars[department]
            threshold = enterprise.working_offset(
                start, rule.threshold_days, mask, holidays, rule.day_basis
            )
            eligible = (
                today <= task.due_date <= threshold
                if rule.trigger == "upcoming_due"
                else task.due_date < today and threshold <= today
            )
            if not eligible:
                continue
            identity = date_event_id(rule, task, today)
            result = db.execute(
                insert(OutboxEvent)
                .values(
                    id=uuid4(),
                    event_id=identity,
                    event_type=rule.trigger,
                    schema_version=1,
                    task_id=task.id,
                    actor_service_id=principal.id,
                    department_id=department,
                    payload={
                        "resource_id": str(task.id),
                        "version": task.version,
                        "owner_user_id": str(task.assignee_id),
                        "rule_id": str(rule.id),
                        "scheduled_for": today.isoformat(),
                    },
                )
                .on_conflict_do_nothing(index_elements=[OutboxEvent.event_id])
            )
            created += int(result.rowcount == 1)
    return created


def retry_time(moment, attempt, base):
    return moment + timedelta(seconds=min(86400, base * (2 ** (attempt - 1))))


def queue_retry(db, record, notice, rule, principal, request):
    moment = retry_time(now(), record.attempt_no, rule.retry_base_seconds)
    if (
        record.attempt_no >= rule.max_attempts
        or moment >= notice.expires_at
        or not rule.enabled
        or rule.version != notice.rule_version
    ):
        return
    queued = NotificationDelivery(
        id=uuid4(),
        version=1,
        notification_id=notice.id,
        connector_id=record.connector_id,
        config_revision=record.config_revision,
        channel=record.channel,
        attempt_no=record.attempt_no + 1,
        state="pending",
        result_code=None,
        next_attempt_at=moment,
        lease_token=None,
        lease_until=None,
    )
    changed(db, queued, principal, request, ["retry_queued"])


def claim(db, principal, request):
    moment = now()
    record = db.scalar(
        select(NotificationDelivery)
        .join(Notification)
        .join(OutboxEvent, Notification.outbox_id == OutboxEvent.id)
        .where(
            OutboxEvent.department_id.in_(principal.department_ids),
            or_(
                (NotificationDelivery.state == "pending")
                & (NotificationDelivery.next_attempt_at <= moment),
                (NotificationDelivery.state == "sending")
                & (NotificationDelivery.lease_until <= moment),
            ),
        )
        .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
        .limit(1)
        .with_for_update(of=NotificationDelivery, skip_locked=True)
    )
    if record is None:
        return None
    notice = db.get(Notification, record.notification_id)
    rule = db.get(NotificationRule, notice.rule_id)
    event = db.get(OutboxEvent, notice.outbox_id)
    if record.state == "sending":
        record.state, record.result_code = "ambiguous", "LEASE_EXPIRED"
        record.lease_token = record.lease_until = None
        touch(record)
        changed(db, record, principal, request, ["lease_expired"])
        queue_retry(db, record, notice, rule, principal, request)
        return {"state": "ambiguous"}
    user = db.get(User, notice.user_id)
    preference = db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == notice.user_id)
    )
    connector = db.get(NotificationConnector, record.connector_id, with_for_update=True)
    eligible = (
        enterprise.enabled(db, "notifications")
        and notice.expires_at > moment
        and user is not None
        and can_view(db, user, event)
        and rule.enabled
        and rule.version == notice.rule_version
        and record.channel in chosen_channels(db, rule, preference)
        and usable_connector(connector, event, record.channel)
        and connector.config_revision == record.config_revision
    )
    if not eligible:
        record.state, record.result_code = "cancelled", "CONTEXT_DISABLED_EXPIRED_OR_CHANGED"
        touch(record)
        changed(db, record, principal, request, ["cancelled"])
        return {"state": "cancelled"}
    available = quiet_until(
        moment, preference.quiet_start, preference.quiet_end, preference.timezone
    )
    recent = db.scalar(
        select(func.count())
        .select_from(NotificationDelivery)
        .where(
            NotificationDelivery.connector_id == connector.id,
            NotificationDelivery.state.in_(["sending", "accepted", "failed", "ambiguous"]),
            NotificationDelivery.updated_at >= moment - timedelta(minutes=1),
        )
    )
    if recent >= connector.config["rate_per_minute"]:
        available = max(available, moment + timedelta(minutes=1))
    if available > moment:
        record.next_attempt_at = available
        touch(record)
        changed(db, record, principal, request, ["deferred"])
        return {"state": "deferred"}
    config, credential = notifications.connector_material(db, connector, request)
    record.state, record.result_code = "sending", None
    record.lease_token, record.lease_until = uuid4(), moment + timedelta(seconds=90)
    touch(record)
    changed(db, record, principal, request, ["attempt_started"])
    return {
        "state": "sending",
        "id": record.id,
        "lease_token": record.lease_token,
        "config": config,
        "credential": credential,
        "recipient": user.email if record.channel == "email" else None,
    }


def finish(db, principal, prepared, passed, request):
    record = db.get(NotificationDelivery, prepared["id"], with_for_update=True)
    if record.state != "sending" or record.lease_token != prepared["lease_token"]:
        return "superseded"
    notice = db.get(Notification, record.notification_id)
    rule = db.get(NotificationRule, notice.rule_id)
    state = "accepted" if passed else "ambiguous"
    if record.lease_until <= now():
        state = "ambiguous"
    record.state = state
    record.result_code = "ACCEPTED" if state == "accepted" else "DELIVERY_OUTCOME_UNKNOWN"
    record.lease_token = record.lease_until = None
    touch(record)
    changed(db, record, principal, request, ["attempt_finished"])
    if state in {"failed", "ambiguous"}:
        queue_retry(db, record, notice, rule, principal, request)
    return state


def tick(factory, principal_id, budget, *, request=None, transport=None, smtp_factory=None):
    checked_budget(budget)
    request = request or SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    report = {
        key: 0
        for key in (
            "date_events",
            "dispatched",
            "accepted",
            "failed",
            "ambiguous",
            "cancelled",
            "deferred",
            "superseded",
        )
    }
    with factory.begin() as db:
        principal = context(db, principal_id)
        report["date_events"] = scan_dates(db, principal, budget)
        rules = list(
            db.scalars(
                select(NotificationRule.id)
                .where(NotificationRule.enabled)
                .order_by(NotificationRule.id)
                .limit(101)
            )
        )
        if len(rules) > 100:
            raise CommandError(413, "NOTIFICATION_RULE_LIMIT_EXCEEDED")
    for identity in rules:
        while report["dispatched"] < budget:
            with factory.begin() as db:
                principal = context(db, principal_id)
                processed = dispatch_one(db, principal, identity, request)
            if not processed:
                break
            report["dispatched"] += 1
    for _ in range(budget):
        with factory.begin() as db:
            principal = context(db, principal_id)
            prepared = claim(db, principal, request)
        if prepared is None:
            break
        if prepared["state"] != "sending":
            report[prepared["state"]] += 1
            continue
        passed = False
        try:
            send(
                prepared["config"],
                prepared["credential"],
                recipient=prepared["recipient"],
                transport=transport,
                smtp_factory=smtp_factory,
            )
            passed = True
        except (CommandError, OSError, ValueError):
            pass
        finally:
            prepared["credential"] = None
        with factory.begin() as db:
            principal = context(db, principal_id)
            state = finish(db, principal, prepared, passed, request)
        report[state] += 1
    return report
