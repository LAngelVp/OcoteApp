import json
import secrets
from datetime import UTC, timedelta
from email.utils import parsedate_to_datetime
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import exists, func, or_, select, text

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.outgoing_webhooks import send
from app.core.security import now
from app.models.collaboration import OutboxEvent, ServicePrincipal
from app.models.evaluations import Evaluation
from app.models.identity import User
from app.models.integrations import WebhookAttempt, WebhookDelivery, WebhookSubscription
from app.models.operations import Objective, Task
from app.services import enterprise, integrations, outgoing_webhooks
from app.services import operations as operation
from app.services.identity import audit, config_lock, touch


def budget(value):
    if type(value) is not int or not 1 <= value <= 100:
        raise CommandError(422, "WEBHOOK_BUDGET_INVALID")
    return value


def context(db, identity):
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise CommandError(503, "MAINTENANCE")
    config_lock(db, exclusive=False)
    if db.scalar(text("SELECT current_user")) != "ocote_runtime":
        raise CommandError(503, "RUNTIME_IDENTITY_REQUIRED")
    if db.scalar(text("SELECT version_num FROM alembic_version")) != "20261126_0010":
        raise CommandError(503, "F11_REVISION_REQUIRED")
    principal = db.get(ServicePrincipal, identity, populate_existing=True)
    if (
        principal is None or not principal.is_active or not principal.department_ids
        or "notifications:dispatch" not in principal.approved_scopes
    ):
        raise CommandError(403, "WEBHOOK_SERVICE_SCOPE_REQUIRED")
    return principal


def ready(db):
    if not all(enterprise.enabled(db, code) for code in ("integrations", "outgoing_webhooks")):
        return False
    enterprise.policy(db)
    return True


def changed(db, record, principal, request, reason):
    audit(db, request, "administration_changed", actor_service=principal.id,
          entity=record.__tablename__, entity_id=record.id,
          after={"version": record.version, "reason": reason})
    db.add(record)
    db.flush()


def scoped_events(owner):
    tasks = operation.scope(select(Task.id), Task, owner)
    objectives = select(Objective.id).where(False)
    evaluations = select(Evaluation.id).where(Evaluation.status == "final")
    if owner.role != "colaborador":
        objectives = operation.scope(select(Objective.id), Objective, owner)
        if owner.role == "lider":
            evaluations = evaluations.where(Evaluation.department_id == owner.department_id)
    else:
        evaluations = evaluations.where(False)
    return or_(OutboxEvent.task_id.in_(tasks), OutboxEvent.objective_id.in_(objectives),
               OutboxEvent.evaluation_id.in_(evaluations))


def event_body(event):
    resource = event.task_id or event.objective_id or event.evaluation_id
    kind = "task" if event.task_id else "objective" if event.objective_id else "evaluation"
    version = event.payload.get("version")
    if type(version) is not int or version < 1:
        version = None
    return json.dumps({
        "event_id": str(event.event_id), "event_type": event.event_type, "schema_version": 1,
        "occurred_at": event.created_at.astimezone(UTC).isoformat(),
        "resource": {"type": kind, "id": str(resource), "version": version},
    }, sort_keys=True, separators=(",", ":")).encode()


def dispatch(db, principal, identity, request):
    if not ready(db):
        return False
    subscription = db.scalar(select(WebhookSubscription).where(
        WebhookSubscription.id == identity, WebhookSubscription.enabled,
    ).with_for_update(skip_locked=True))
    if subscription is None:
        return False
    owner = db.get(User, subscription.owner_user_id, populate_existing=True)
    try:
        outgoing_webhooks.department_scope(db, owner, subscription.department_ids)
        config = outgoing_webhooks.configuration(
            db, subscription.integration_id, subscription.department_ids, active=True
        )
    except CommandError:
        return False
    allowed = set(principal.department_ids) & set(subscription.department_ids)
    queued = exists(select(WebhookDelivery.id).where(
        WebhookDelivery.subscription_id == subscription.id,
        WebhookDelivery.outbox_id == OutboxEvent.id,
        WebhookDelivery.retry_of_id.is_(None),
    ))
    event = db.scalar(select(OutboxEvent).where(
        OutboxEvent.event_type.in_(subscription.event_types),
        OutboxEvent.department_id.in_(allowed),
        OutboxEvent.created_at >= subscription.updated_at,
        scoped_events(owner), ~queued,
    ).order_by(OutboxEvent.created_at, OutboxEvent.id).limit(1))
    if event is None:
        return False
    record = outgoing_webhooks.new_delivery(
        subscription, event, config, event_body(event), str(event.event_id)
    )
    changed(db, record, principal, request, "webhook_queued")
    return True


def retry_delay(moment, attempt, base, maximum, retry_after=None):
    delay = min(maximum, base * 2 ** (attempt - 1))
    delay = min(maximum, delay + secrets.randbelow(max(1, delay // 4 + 1)))
    if isinstance(retry_after, str) and len(retry_after) <= 128:
        try:
            if retry_after.isascii() and retry_after.isdecimal():
                requested = min(maximum, int(retry_after))
            else:
                requested = (parsedate_to_datetime(retry_after) - moment).total_seconds()
            delay = min(maximum, max(delay, requested))
        except (ValueError, TypeError, OverflowError):
            pass
    return moment + timedelta(seconds=delay)


def outcome(status):
    if type(status) is not int or not 200 <= status <= 599:
        return "ambiguous", None, "TRANSPORT_UNAVAILABLE"
    if status < 300:
        return "accepted", status, "ACCEPTED"
    if status in {408, 429} or status >= 500:
        return "retryable", status, "RETRYABLE"
    return "rejected", status, "REJECTED"


def complete(db, principal, request, record, prepared, status, headers, latency):
    moment = now()
    if record.state != "sending" or record.lease_token != prepared["lease_token"]:
        return "fenced"
    result, status, code = outcome(status)
    if record.lease_until <= moment:
        result, status, code = "ambiguous", None, "LEASE_EXPIRED"
    attempt = WebhookAttempt(
        id=prepared["attempt_id"], created_at=moment, delivery_id=record.id,
        attempt_no=record.attempt_count, lease_token=record.lease_token,
        signed_at=prepared["signed_at"], outcome=result, status_code=status, result_code=code,
        latency_ms=min(120000, max(0, latency)),
    )
    db.add(attempt)
    db.flush([attempt])
    if result == "accepted":
        record.state = "delivered"
    elif result in {"retryable", "ambiguous"} and record.attempt_count < record.max_attempts:
        record.state = "pending"
        record.next_attempt_at = retry_delay(
            moment, record.attempt_count, record.retry_base_seconds, record.max_delay_seconds,
            headers.get("retry-after"),
        )
    else:
        record.state = "dead_letter"
    record.lease_token = record.lease_until = None
    touch(record)
    changed(db, record, principal, request, "webhook_" + result)
    return result


def claim(db, principal, request):
    if not ready(db):
        return None
    moment = now()
    record = db.scalar(select(WebhookDelivery).join(WebhookSubscription).where(
        WebhookSubscription.department_ids.overlap(principal.department_ids),
        or_((WebhookDelivery.state == "pending") & (WebhookDelivery.next_attempt_at <= moment),
            (WebhookDelivery.state == "sending") & (WebhookDelivery.lease_until <= moment)),
    ).order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id).limit(1)
        .with_for_update(of=WebhookDelivery, skip_locked=True))
    if record is None:
        return None
    if record.state == "sending":
        complete(db, principal, request, record, {
            "lease_token": record.lease_token, "attempt_id": uuid4(),
            "signed_at": record.updated_at,
        }, None, {}, 0)
        return {"recovered": True}
    subscription = db.get(WebhookSubscription, record.subscription_id)
    owner = db.get(User, subscription.owner_user_id, populate_existing=True)
    event = db.get(OutboxEvent, record.outbox_id)
    try:
        if not subscription.enabled or subscription.version != record.subscription_version:
            raise CommandError(409, "WEBHOOK_SUBSCRIPTION_CHANGED")
        outgoing_webhooks.department_scope(db, owner, subscription.department_ids)
        config = outgoing_webhooks.configuration(
            db, subscription.integration_id, subscription.department_ids, active=True
        )
        integrations.connector_for(db, config.id, lock=True)
        if (
            event.department_id not in principal.department_ids
            or event.department_id not in subscription.department_ids
            or event.event_type not in subscription.event_types
            or config.config_revision != record.config_revision
            or config.secret_id != record.signing_secret_id
            or record.attempt_count >= record.max_attempts
            or db.scalar(select(OutboxEvent.id).where(
                OutboxEvent.id == event.id, scoped_events(owner)
            )) is None
        ):
            raise CommandError(403, "WEBHOOK_CURRENT_SCOPE_DENIED")
        config, credential = integrations.connector_material(db, config, request)
        if not config.endpoint.audience_approved:
            raise CommandError(422, "EXPLICIT_AUDIENCE_AND_DESTINATION_REQUIRED")
    except CommandError:
        record.state = "cancelled"
        touch(record)
        changed(db, record, principal, request, "webhook_context_invalidated")
        return {"cancelled": True}
    completed = db.scalar(select(func.count()).select_from(WebhookAttempt).join(
        WebhookDelivery
    ).join(WebhookSubscription).where(
        WebhookSubscription.integration_id == subscription.integration_id,
        WebhookAttempt.signed_at >= moment - timedelta(minutes=1),
    ))
    reserved = db.scalar(select(func.count()).select_from(WebhookDelivery).join(
        WebhookSubscription
    ).where(WebhookSubscription.integration_id == subscription.integration_id,
            WebhookDelivery.updated_at >= moment - timedelta(minutes=1),
            WebhookDelivery.state == "sending"))
    if completed + reserved >= config.endpoint.rate_per_minute:
        return None
    record.state, record.attempt_count = "sending", record.attempt_count + 1
    record.lease_token, record.lease_until = uuid4(), moment + timedelta(seconds=90)
    touch(record)
    changed(db, record, principal, request, "webhook_claimed")
    return {"id": record.id, "lease_token": record.lease_token, "attempt_id": uuid4(),
            "signed_at": moment, "body": bytes(record.body), "config": config,
            "credential": credential, "key_id": record.signing_secret_id,
            "event_id": event.event_id}


def tick(factory, principal_id, limit, *, request=None, transport=None):
    budget(limit)
    request = request or SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    report = {"queued": 0, "accepted": 0, "retryable": 0, "rejected": 0, "ambiguous": 0,
              "fenced": 0, "recovered": 0, "cancelled": 0}
    with factory.begin() as db:
        principal = context(db, principal_id)
        if not ready(db):
            return report
        identities = list(db.scalars(select(WebhookSubscription.id).where(
            WebhookSubscription.enabled,
            WebhookSubscription.department_ids.overlap(principal.department_ids),
        ).order_by(WebhookSubscription.id).limit(limit)))
    for identity in identities:
        with factory.begin() as db:
            principal = context(db, principal_id)
            report["queued"] += int(dispatch(db, principal, identity, request))
    for _index in range(limit):
        with factory.begin() as db:
            principal = context(db, principal_id)
            prepared = claim(db, principal, request)
        if prepared is None:
            break
        if prepared.get("recovered") or prepared.get("cancelled"):
            report["recovered" if prepared.get("recovered") else "cancelled"] += 1
            continue
        status, headers, started = None, {}, monotonic()
        try:
            status, headers, _response = send(
                prepared["config"], prepared["credential"], prepared["key_id"],
                prepared["event_id"], prepared["attempt_id"], prepared["body"],
                timestamp=int(prepared["signed_at"].timestamp()), transport=transport,
            )
        except (CommandError, OSError, ValueError, TypeError):
            pass
        finally:
            prepared.pop("credential", None)
        latency = int((monotonic() - started) * 1000)
        with factory.begin() as db:
            principal = context(db, principal_id)
            record = db.get(WebhookDelivery, prepared["id"], with_for_update=True,
                            populate_existing=True)
            if record is None:
                raise CommandError(503, "WEBHOOK_DELIVERY_INTEGRITY_FAILURE")
            result = complete(db, principal, request, record, prepared, status, headers, latency)
        report[result] += 1
    return report