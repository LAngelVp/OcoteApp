import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from time import monotonic
from uuid import UUID, uuid4

from pydantic import SecretStr, TypeAdapter
from sqlalchemy import func, or_, select

from app.core.errors import CommandError
from app.core.notifications import calendar_content, provider_target, send
from app.core.security import now
from app.models.collaboration import OutboxEvent
from app.models.evaluations import Evaluation
from app.models.identity import AuditEvent, User
from app.models.notifications import (
    CalendarFeed,
    Notification,
    NotificationConnector,
    NotificationConnectorCheck,
    NotificationPreference,
    NotificationRule,
)
from app.models.operations import Objective, Task
from app.models.platform import EncryptedSecret
from app.schemas.notifications import ConnectorConfig
from app.schemas.platform import SecretWrite
from app.services import platform
from app.services.administration import check_version
from app.services.enterprise import (
    department_scope,
    reauthenticate,
    require_module,
    require_page_size,
)
from app.services.identity import audit, config_lock, touch
from app.services.operations import scope

CONFIG = TypeAdapter(ConnectorConfig)


def changed(db, record, request, actor, reason, keys):
    audit(
        db,
        request,
        "administration_changed",
        actor=actor.id,
        entity=record.__tablename__,
        entity_id=record.id,
        after={"version": record.version, "changed_keys": sorted(keys), "reason": reason},
    )
    db.add(record)
    db.flush()


def preferences_view(record):
    if record is None:
        return None
    return {
        key: getattr(record, key)
        for key in (
            "id",
            "version",
            "channels",
            "opt_in",
            "quiet_start",
            "quiet_end",
            "timezone",
        )
    }


def preferences(db, actor, *, lock=False):
    require_module(db, "notifications")
    query = select(NotificationPreference).where(NotificationPreference.user_id == actor.id)
    return db.scalar(query.with_for_update() if lock else query)


def save_preferences(db, body, request, actor):
    record = preferences(db, actor, lock=True)
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    values = body.model_dump(exclude={"expected_version", "reason"})
    if record is None:
        record = NotificationPreference(id=uuid4(), version=1, user_id=actor.id, **values)
    else:
        for key, value in values.items():
            setattr(record, key, value)
        touch(record)
    changed(db, record, request, actor, body.reason, values)
    return preferences_view(record)


def scoped_notifications(actor):
    query = select(Notification).join(OutboxEvent, Notification.outbox_id == OutboxEvent.id)
    query = query.where(
        Notification.user_id == actor.id,
        Notification.expires_at > now(),
        Notification.in_app,
        Notification.available_at <= now(),
    )
    task_ids = scope(select(Task.id), Task, actor)
    if actor.role == "colaborador":
        return query.where(OutboxEvent.task_id.in_(task_ids))
    objective_ids = scope(select(Objective.id), Objective, actor)
    evaluations = select(Evaluation.id).where(Evaluation.status == "final")
    if actor.role == "lider":
        evaluations = evaluations.where(Evaluation.department_id == actor.department_id)
    return query.where(
        or_(
            OutboxEvent.task_id.in_(task_ids),
            OutboxEvent.objective_id.in_(objective_ids),
            OutboxEvent.evaluation_id.in_(evaluations),
        )
    )


def notification_view(record):
    return {
        key: getattr(record, key)
        for key in (
            "id",
            "version",
            "safe_projection",
            "read_at",
            "created_at",
            "expires_at",
        )
    }


def inbox(db, actor, limit, cursor=None, unread=False):
    require_module(db, "notifications")
    require_page_size(db, limit)
    query = scoped_notifications(actor)
    count_query = query.where(Notification.read_at.is_(None)).subquery()
    count = db.scalar(select(func.count()).select_from(count_query))
    if unread:
        query = query.where(Notification.read_at.is_(None))
    if cursor:
        query = query.where(Notification.id > cursor)
    records = list(db.scalars(query.order_by(Notification.id).limit(limit + 1)))
    return {
        "items": [notification_view(record) for record in records[:limit]],
        "next_cursor": records[limit - 1].id if len(records) > limit else None,
        "unread_count": count,
    }


def read_notification(db, identity, body, request, actor):
    require_module(db, "notifications")
    record = db.scalar(
        scoped_notifications(actor)
        .where(Notification.id == identity)
        .with_for_update(of=Notification)
    )
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.read_at is None:
        record.read_at = now()
        touch(record)
        changed(db, record, request, actor, body.reason, ["read_at"])
    return notification_view(record)


def store_secret(db, owner, purpose, value, reason, request, actor):
    query = (
        select(EncryptedSecret)
        .where(
            EncryptedSecret.owner_id == owner,
            EncryptedSecret.purpose == purpose,
        )
        .order_by(EncryptedSecret.secret_version.desc())
        .limit(1)
    )
    previous = db.scalar(query)
    platform.write_secret(
        db,
        owner,
        purpose,
        SecretWrite(
            expected_version=previous.secret_version if previous else 0,
            reason=reason,
            value=SecretStr(value),
        ),
        request,
        actor,
    )
    return db.scalar(query).id


def decrypted_secret(db, owner, identity, purpose, request=None):
    secret = db.get(EncryptedSecret, identity)
    if secret is None or secret.owner_id != owner or secret.purpose != purpose:
        raise CommandError(503, "VAULT_UNAVAILABLE")
    key = db.get(platform.SecretKeyVersion, secret.key_id)
    try:
        return (
            platform.vault(db, request)
            .decrypt(platform.wrapped(key), platform.encrypted(secret))
            .decode("utf-8")
        )
    except UnicodeError:
        raise CommandError(503, "VAULT_UNAVAILABLE") from None


def feed_view(record):
    return {
        key: getattr(record, key)
        for key in (
            "id",
            "version",
            "name",
            "created_at",
            "expires_at",
            "revoked_at",
        )
    }


def require_feeds(db):
    require_module(db, "calendar")
    require_module(db, "calendar_feeds")


def feed_signature(key, record, nonce):
    content = f"{record.id}:{record.owner_user_id}:{int(record.expires_at.timestamp())}:{nonce}"
    return hmac.new(key.encode(), content.encode(), hashlib.sha256).hexdigest()


def create_feed(db, body, request, actor):
    require_feeds(db)
    if body.expected_version != 0:
        raise CommandError(409, "VERSION_CONFLICT")
    moment = now()
    if not moment + timedelta(minutes=1) <= body.expires_at <= moment + timedelta(days=90):
        raise CommandError(422, "FEED_EXPIRATION_OUT_OF_RANGE")
    count = db.scalar(
        select(func.count())
        .select_from(CalendarFeed)
        .where(
            CalendarFeed.owner_user_id == actor.id,
            CalendarFeed.revoked_at.is_(None),
            CalendarFeed.expires_at > moment,
        )
    )
    if count >= 20:
        raise CommandError(413, "CALENDAR_FEED_LIMIT_EXCEEDED")
    record = CalendarFeed(
        id=uuid4(),
        version=1,
        owner_user_id=actor.id,
        name=body.name,
        expires_at=body.expires_at,
        revoked_at=None,
    )
    key, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    capability = nonce + "." + feed_signature(key, record, nonce)
    record.token_hash = hashlib.sha256(capability.encode()).hexdigest()
    record.signing_secret_id = store_secret(
        db, record.id, "calendar_feed", key, body.reason, request, actor
    )
    changed(db, record, request, actor, body.reason, ["created"])
    return feed_view(record) | {"capability": capability}


def feeds(db, actor, limit, cursor=None):
    require_feeds(db)
    require_page_size(db, limit)
    query = select(CalendarFeed).where(CalendarFeed.owner_user_id == actor.id)
    if cursor:
        query = query.where(CalendarFeed.id > cursor)
    records = list(db.scalars(query.order_by(CalendarFeed.id).limit(limit + 1)))
    return {
        "items": [feed_view(record) for record in records[:limit]],
        "next_cursor": records[limit - 1].id if len(records) > limit else None,
    }


def revoke_feed(db, identity, body, request, actor):
    require_feeds(db)
    record = db.scalar(
        select(CalendarFeed)
        .where(
            CalendarFeed.id == identity,
            CalendarFeed.owner_user_id == actor.id,
        )
        .with_for_update()
    )
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.revoked_at is None:
        record.revoked_at = now()
        touch(record)
        changed(db, record, request, actor, body.reason, ["revoked_at"])
    return feed_view(record)


def render_feed(db, identity, capability, request):
    if re.fullmatch(r"[A-Za-z0-9_-]{43}\.[0-9a-f]{64}", capability) is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    require_feeds(db)
    record = db.get(CalendarFeed, identity)
    if (
        record is None
        or record.revoked_at is not None
        or record.expires_at <= now()
        or not hmac.compare_digest(
            record.token_hash, hashlib.sha256(capability.encode()).hexdigest()
        )
    ):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    nonce, separator, signature = capability.partition(".")
    key = decrypted_secret(db, record.id, record.signing_secret_id, "calendar_feed", request)
    if not separator or not hmac.compare_digest(signature, feed_signature(key, record, nonce)):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    actor = db.get(User, record.owner_user_id)
    if actor is None or not actor.is_active:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    tasks = list(db.scalars(scope(select(Task), Task, actor).order_by(Task.id).limit(10001)))
    if len(tasks) > 10000:
        raise CommandError(413, "CALENDAR_TASK_LIMIT_EXCEEDED")
    try:
        content = calendar_content(tasks, now())
    except OverflowError:
        raise CommandError(413, "CALENDAR_DATE_RANGE_NOT_REPRESENTABLE") from None
    if len(content) > 16777216:
        raise CommandError(413, "CALENDAR_BYTE_LIMIT_EXCEEDED")
    audit(
        db,
        request,
        "administration_changed",
        actor=actor.id,
        entity="calendar_feeds",
        entity_id=record.id,
        after={"calendar_read": True},
    )
    return content


def require_connectors(db, provider=None):
    require_module(db, "integrations")
    require_module(db, "notifications")
    if provider:
        require_module(db, "email_notifications" if provider == "smtp" else "corporate_messaging")


def connector_view(record):
    return {
        key: getattr(record, key)
        for key in (
            "id",
            "version",
            "name",
            "scope_kind",
            "department_id",
            "provider",
            "config",
            "config_revision",
            "is_active",
            "tested_version",
            "tested_at",
        )
    } | {"secret_configured": record.secret_id is not None}


def connector_for(db, identity):
    record = db.get(NotificationConnector, identity, with_for_update=True, populate_existing=True)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def save_connector(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    require_connectors(db)
    department_scope(db, body.scope_kind, body.department_id)
    record = connector_for(db, identity) if identity else None
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    config = body.config.model_dump(mode="json")
    if record is None:
        record = NotificationConnector(
            id=uuid4(),
            version=1,
            config_revision=1,
            provider=config["provider"],
            created_by=actor.id,
        )
    elif record.provider != config["provider"]:
        raise CommandError(409, "PROVIDER_TYPE_IMMUTABLE")
    secret_id = record.secret_id
    if body.credential is not None:
        credential = body.credential.get_secret_value()
        if record.provider != "smtp":
            provider_target(config, credential)
        secret_id = store_secret(
            db, record.id, "notifications", credential, body.reason, request, actor
        )
    if secret_id is None and (record.provider != "smtp" or config["authentication"] != "none"):
        raise CommandError(422, "PROVIDER_CREDENTIALS_REQUIRED")
    if identity:
        record.config_revision += 1
        touch(record)
    record.secret_id, record.config, record.name = secret_id, config, body.name
    record.scope_kind, record.department_id = body.scope_kind, body.department_id
    record.is_active = False
    record.tested_version = record.tested_at = None
    changed(
        db,
        record,
        request,
        actor,
        body.reason,
        ["configuration", "secret_replaced"] if body.credential else ["configuration"],
    )
    return connector_view(record)


def connector_material(db, record, request):
    config = CONFIG.validate_python(record.config).model_dump(mode="json")
    credential = (
        decrypted_secret(db, record.id, record.secret_id, "notifications", request)
        if record.secret_id
        else None
    )
    if config["provider"] != "smtp":
        provider_target(config, credential)
    elif config["authentication"] == "login" and credential is None:
        raise CommandError(503, "VAULT_UNAVAILABLE")
    return config, credential


def test_connector(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    record = connector_for(db, identity)
    require_connectors(db, record.provider)
    check_version(record, body.expected_version)
    config, credential = connector_material(db, record, request)
    destination = config["test_recipient"] if record.provider == "smtp" else config["destination"]
    if not config["audience_approved"] or body.destination != destination or not body.confirmed:
        raise CommandError(422, "EXPLICIT_AUDIENCE_AND_DESTINATION_REQUIRED")
    recent = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.entity_type == "notification_connectors",
            AuditEvent.entity_id == identity,
            AuditEvent.created_at >= now() - timedelta(minutes=1),
            AuditEvent.after_data["changed_keys"].contains(["probe_started"]),
        )
    )
    if recent >= config["rate_per_minute"]:
        raise CommandError(429, "CONNECTOR_RATE_LIMIT")
    record.is_active = False
    record.tested_version = record.tested_at = None
    touch(record)
    changed(db, record, request, actor, body.reason, ["probe_started"])
    prepared_version, revision, actor_id = record.version, record.config_revision, actor.id
    db.commit()
    started, passed = monotonic(), False
    try:
        send(
            config,
            credential,
            recipient=destination if config["provider"] == "smtp" else None,
            test=True,
            transport=getattr(request.app.state, "notification_transport", None),
            smtp_factory=getattr(request.app.state, "notification_smtp_factory", None),
        )
        passed = True
    except (CommandError, OSError, ValueError):
        pass
    finally:
        credential = None
    latency = min(120000, max(0, int((monotonic() - started) * 1000)))
    db.expire_all()
    db.info.pop("f8_flags", None)
    config_lock(db)
    actor = db.get(User, actor_id, with_for_update=True, populate_existing=True)
    if actor is None or not actor.is_active or actor.role != "admin":
        raise CommandError(403, "ADMINISTRATOR_REQUIRED")
    record = connector_for(db, identity)
    require_connectors(db, record.provider)
    current = record.version == prepared_version and record.config_revision == revision
    passed = passed and current
    code = "VERIFIED" if passed else "PROVIDER_UNAVAILABLE_OR_UNSAFE"
    db.add(
        NotificationConnectorCheck(
            connector_id=identity,
            config_version=revision,
            status="passed" if passed else "failed",
            result_code=code,
            latency_ms=latency,
            actor_id=actor_id,
            request_id=UUID(request.state.request_id),
        )
    )
    if not current:
        db.flush()
        raise CommandError(409, "CONFIGURATION_CHANGED_DURING_TEST", persist=True)
    record.tested_version = revision if passed else None
    record.tested_at = now() if passed else None
    touch(record)
    changed(db, record, request, actor, body.reason, ["probe_finished"])
    return connector_view(record) | {"passed": passed, "result_code": code}


def activate_connector(db, identity, body, request, actor, active):
    reauthenticate(db, actor, body, request)
    require_connectors(db)
    record = connector_for(db, identity)
    check_version(record, body.expected_version)
    if active:
        require_connectors(db, record.provider)
        if (
            record.tested_version != record.config_revision
            or record.tested_at is None
            or not now() - timedelta(minutes=10) <= record.tested_at <= now()
            or not record.config.get("audience_approved")
        ):
            raise CommandError(409, "FRESH_VERIFICATION_REQUIRED")
        connector_material(db, record, request)
    record.is_active = active
    touch(record)
    changed(db, record, request, actor, body.reason, ["is_active"])
    return connector_view(record)


def rule_view(record):
    from app.schemas.notifications import RuleWrite

    return {"id": record.id, "version": record.version} | {
        key: getattr(record, key)
        for key in RuleWrite.model_fields
        if key not in {"expected_version", "current_password", "reason"}
    }


def save_rule(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    require_module(db, "notifications")
    department_scope(db, "department" if body.department_id else "organization", body.department_id)
    record = db.get(NotificationRule, identity, with_for_update=True) if identity else None
    if identity and record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    channels = set()
    for connector_id in body.connector_ids:
        connector = connector_for(db, connector_id)
        if connector.department_id is not None and connector.department_id != body.department_id:
            raise CommandError(422, "CONNECTOR_OUTSIDE_RULE_SCOPE")
        channel = "email" if connector.provider == "smtp" else "messaging"
        if channel not in body.channels:
            raise CommandError(422, "CONNECTOR_CHANNEL_MISMATCH")
        channels.add(channel)
    if set(body.channels) - {"in_app"} != channels:
        raise CommandError(422, "EXPLICIT_CHANNEL_CONNECTORS_REQUIRED")
    values = body.model_dump(exclude={"expected_version", "current_password", "reason"})
    if record is None:
        record = NotificationRule(id=uuid4(), version=1, created_by=actor.id, **values)
    else:
        for key, value in values.items():
            setattr(record, key, value)
        touch(record)
    changed(db, record, request, actor, body.reason, values)
    return rule_view(record)
