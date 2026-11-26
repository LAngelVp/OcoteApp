from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class NotificationConnector(Mutable, Base):
    __tablename__ = "notification_connectors"
    name: Mapped[str] = mapped_column(String(120))
    scope_kind: Mapped[str] = mapped_column(String(20))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"))
    provider: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSONB)
    secret_id: Mapped[UUID | None] = mapped_column(ForeignKey("encrypted_secrets.id"))
    config_revision: Mapped[int]
    is_active: Mapped[bool]
    tested_version: Mapped[int | None]
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class NotificationConnectorCheck(Identity, Base):
    __tablename__ = "notification_connector_checks"
    connector_id: Mapped[UUID] = mapped_column(ForeignKey("notification_connectors.id"))
    config_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(12))
    result_code: Mapped[str] = mapped_column(String(80))
    latency_ms: Mapped[int]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[UUID]


class NotificationRule(Mutable, Base):
    __tablename__ = "notification_rules"
    name: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"))
    trigger: Mapped[str] = mapped_column(String(32))
    recipient_mode: Mapped[str] = mapped_column(String(32))
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    connector_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    threshold_days: Mapped[int | None]
    day_basis: Mapped[str] = mapped_column(String(12))
    max_age_hours: Mapped[int]
    max_attempts: Mapped[int]
    retry_base_seconds: Mapped[int]
    enabled: Mapped[bool]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class NotificationPreference(Mutable, Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    opt_in: Mapped[bool]
    quiet_start: Mapped[str | None] = mapped_column(String(5))
    quiet_end: Mapped[str | None] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(64))


class Notification(Mutable, Base):
    __tablename__ = "notifications"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    outbox_id: Mapped[UUID] = mapped_column(ForeignKey("transactional_outbox.id"))
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("notification_rules.id"))
    rule_version: Mapped[int]
    safe_projection: Mapped[dict] = mapped_column(JSONB)
    in_app: Mapped[bool]
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Mutable, Base):
    __tablename__ = "notification_deliveries"
    notification_id: Mapped[UUID] = mapped_column(ForeignKey("notifications.id"))
    connector_id: Mapped[UUID] = mapped_column(ForeignKey("notification_connectors.id"))
    config_revision: Mapped[int]
    channel: Mapped[str] = mapped_column(String(20))
    attempt_no: Mapped[int]
    state: Mapped[str] = mapped_column(String(20))
    result_code: Mapped[str | None] = mapped_column(String(80))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDispatch(Identity, Base):
    __tablename__ = "notification_dispatches"
    outbox_id: Mapped[UUID] = mapped_column(ForeignKey("transactional_outbox.id"))
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("notification_rules.id"))
    rule_version: Mapped[int]
    recipient_count: Mapped[int]


class CalendarFeed(Mutable, Base):
    __tablename__ = "calendar_feeds"
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    signing_secret_id: Mapped[UUID] = mapped_column(ForeignKey("encrypted_secrets.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
