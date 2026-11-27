from uuid import uuid4

from sqlalchemy import select

from app.core.errors import CommandError
from app.core.security import now
from app.models.collaboration import OutboxEvent
from app.models.identity import Department, User
from app.models.integrations import WebhookAttempt, WebhookDelivery, WebhookSubscription
from app.services import integrations
from app.services import operations as operation
from app.services.administration import check_version
from app.services.collaboration import save_record
from app.services.enterprise import require_page_size
from app.services.identity import touch
from app.services.notification_worker import can_view


def department_scope(db, owner, departments):
    if owner is None or not owner.is_active or not departments:
        raise CommandError(422, "WEBHOOK_OWNER_SCOPE_INVALID")
    if owner.role not in {"admin", "gerente"} and set(departments) != {owner.department_id}:
        raise CommandError(422, "WEBHOOK_OWNER_SCOPE_INVALID")
    active = set(db.scalars(select(Department.id).where(
        Department.id.in_(departments), Department.is_active,
    )))
    if active != set(departments):
        raise CommandError(422, "WEBHOOK_OWNER_SCOPE_INVALID")


def configuration(db, identity, departments, *, active=False):
    record = integrations.connector_for(db, identity)
    if record.kind != "outgoing_webhook" or (active and not record.is_active):
        raise CommandError(409, "WEBHOOK_CONNECTOR_UNAVAILABLE")
    if record.scope_kind == "department" and set(departments) != {record.department_id}:
        raise CommandError(422, "WEBHOOK_CONNECTOR_OUTSIDE_SCOPE")
    return record


def subscriptions(db, actor, limit, cursor=None):
    integrations.administrator(actor)
    integrations.modules(db, "outgoing_webhook")
    require_page_size(db, limit)
    query = select(WebhookSubscription)
    if cursor:
        query = query.where(WebhookSubscription.id > cursor)
    rows = list(db.scalars(query.order_by(WebhookSubscription.id).limit(limit + 1)))
    return {"items": [operation.state(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def save_subscription(db, identity, body, request, actor):
    integrations.administrator(actor)
    integrations.reauthenticate(db, actor, body, request)
    integrations.administrator(actor)
    integrations.modules(db, "outgoing_webhook")
    owner = db.get(User, body.owner_user_id, populate_existing=True)
    if owner is None:
        raise CommandError(422, "WEBHOOK_OWNER_SCOPE_INVALID")
    if body.enabled:
        department_scope(db, owner, body.department_ids)
    configuration(db, body.integration_id, body.department_ids, active=body.enabled)
    record = db.get(WebhookSubscription, identity, with_for_update=True) if identity else None
    if identity and record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if record and (record.integration_id != body.integration_id
                   or record.owner_user_id != body.owner_user_id):
        raise CommandError(409, "WEBHOOK_SUBSCRIPTION_IDENTITY_IMMUTABLE")
    values = body.model_dump(exclude={"expected_version", "current_password", "reason"})
    before = operation.state(record) if record else {}
    if record:
        for field, value in values.items():
            setattr(record, field, value)
        touch(record)
    else:
        moment = now()
        record = WebhookSubscription(id=uuid4(), version=1, created_at=moment,
                                     updated_at=moment, **values)
    save_record(db, actor, request, record, before, "webhook_subscription_changed", body.reason)
    return operation.state(record)


def delivery_view(record):
    return {name: getattr(record, name) for name in (
        "id", "version", "created_at", "updated_at", "subscription_id", "outbox_id",
        "state", "attempt_count", "max_attempts", "next_attempt_at", "retry_of_id", "requested_by",
    )}


def deliveries(db, actor, limit, cursor=None, *, subscription_id=None, state=None,
               since=None, until=None):
    integrations.administrator(actor)
    integrations.modules(db, "outgoing_webhook")
    require_page_size(db, limit)
    if since is not None and until is not None and since > until:
        raise CommandError(422, "WEBHOOK_DATE_RANGE_INVALID")
    query = select(WebhookDelivery)
    if cursor:
        query = query.where(WebhookDelivery.id > cursor)
    if subscription_id:
        query = query.where(WebhookDelivery.subscription_id == subscription_id)
    if state:
        query = query.where(WebhookDelivery.state == state)
    if since:
        query = query.where(WebhookDelivery.created_at >= since)
    if until:
        query = query.where(WebhookDelivery.created_at <= until)
    rows = list(db.scalars(query.order_by(WebhookDelivery.id).limit(limit + 1)))
    return {"items": [delivery_view(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def attempt_view(record):
    return {name: getattr(record, name) for name in (
        "id", "created_at", "delivery_id", "attempt_no", "signed_at", "outcome",
        "status_code", "result_code", "latency_ms",
    )}


def attempts(db, actor, identity, limit, cursor=None):
    integrations.administrator(actor)
    integrations.modules(db, "outgoing_webhook")
    require_page_size(db, limit)
    if db.get(WebhookDelivery, identity) is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    query = select(WebhookAttempt).where(WebhookAttempt.delivery_id == identity)
    if cursor:
        query = query.where(WebhookAttempt.id > cursor)
    rows = list(db.scalars(query.order_by(WebhookAttempt.id).limit(limit + 1)))
    return {"items": [attempt_view(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def new_delivery(subscription, event, config, body, idempotency_key, *, retry_of=None, actor=None):
    moment = now()
    return WebhookDelivery(
        id=uuid4(), version=1, created_at=moment, updated_at=moment,
        subscription_id=subscription.id, subscription_version=subscription.version,
        outbox_id=event.id, idempotency_key=idempotency_key,
        config_revision=config.config_revision, signing_secret_id=config.secret_id, body=body,
        state="pending", attempt_count=0, max_attempts=subscription.max_attempts,
        retry_base_seconds=subscription.retry_base_seconds,
        max_delay_seconds=subscription.max_delay_seconds, next_attempt_at=moment,
        lease_token=None, lease_until=None, retry_of_id=retry_of, requested_by=actor,
    )


def replay(db, identity, body, request, actor):
    integrations.administrator(actor)
    integrations.reauthenticate(db, actor, body, request)
    integrations.administrator(actor)
    integrations.modules(db, "outgoing_webhook")
    subscription = db.get(WebhookSubscription, identity, with_for_update=True)
    if subscription is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    original = db.get(WebhookDelivery, body.delivery_id)
    if original is None or original.subscription_id != subscription.id:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(original, body.expected_version)
    if original.state not in {"delivered", "dead_letter", "cancelled"} or not subscription.enabled:
        raise CommandError(409, "WEBHOOK_TERMINAL_DELIVERY_REQUIRED")
    event = db.get(OutboxEvent, original.outbox_id)
    owner = db.get(User, subscription.owner_user_id, populate_existing=True)
    department_scope(db, owner, subscription.department_ids)
    if (
        event.event_type not in subscription.event_types
        or event.department_id not in subscription.department_ids
        or not can_view(db, owner, event)
    ):
        raise CommandError(403, "WEBHOOK_REPLAY_SCOPE_DENIED")
    config = configuration(
        db, subscription.integration_id, subscription.department_ids, active=True
    )
    key = "replay:" + str(body.idempotency_key)
    previous = db.scalar(select(WebhookDelivery).where(
        WebhookDelivery.subscription_id == subscription.id, WebhookDelivery.idempotency_key == key,
    ))
    if previous is not None:
        if previous.retry_of_id != original.id:
            raise CommandError(409, "WEBHOOK_REPLAY_IDEMPOTENCY_COLLISION")
        return delivery_view(previous)
    record = new_delivery(subscription, event, config, original.body, key,
                          retry_of=original.id, actor=actor.id)
    save_record(db, actor, request, record, {}, "webhook_replayed", body.reason)
    return delivery_view(record)