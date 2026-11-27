from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class ExternalIdentity(Mutable, Base):
    __tablename__ = "external_identities"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(512))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SSOTransaction(Mutable, Base):
    __tablename__ = "sso_transactions"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    config_revision: Mapped[int]
    purpose: Mapped[str] = mapped_column(String(12))
    initiating_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    state_hash: Mapped[str] = mapped_column(String(64))
    browser_hash: Mapped[str] = mapped_column(String(64))
    context_secret_id: Mapped[UUID] = mapped_column(ForeignKey("encrypted_secrets.id"))
    state: Mapped[str] = mapped_column(String(12))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issuer: Mapped[str | None] = mapped_column(String(512))
    subject: Mapped[str | None] = mapped_column(String(512))
    authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SSOAssertionUse(Identity, Base):
    __tablename__ = "sso_assertion_uses"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("sso_transactions.id"))
    assertion_id: Mapped[str] = mapped_column(String(256))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class APIKey(Mutable, Base):
    __tablename__ = "api_keys"
    name: Mapped[str] = mapped_column(String(120))
    service_principal_id: Mapped[UUID] = mapped_column(ForeignKey("service_principals.id"))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    principal_token_version: Mapped[int]
    owner_token_version: Mapped[int]
    rate_per_minute: Mapped[int]
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    department_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    allowed_networks: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))
    token_hash: Mapped[str] = mapped_column(String(64))
    pepper_secret_id: Mapped[UUID] = mapped_column(ForeignKey("encrypted_secrets.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_from_id: Mapped[UUID | None] = mapped_column(ForeignKey("api_keys.id"))


class TaskExternalLink(Mutable, Base):
    __tablename__ = "task_external_links"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    repository_id: Mapped[str] = mapped_column(String(128))
    external_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(20))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    safe_projection: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookInbox(Identity, Base):
    __tablename__ = "webhook_inbox"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    delivery_id: Mapped[str] = mapped_column(String(200))
    body_hash: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(80))
    safe_projection: Mapped[dict] = mapped_column(JSONB)
    request_id: Mapped[UUID]


class WebhookSubscription(Mutable, Base):
    __tablename__ = "webhook_subscriptions"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    department_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    max_attempts: Mapped[int]
    retry_base_seconds: Mapped[int]
    max_delay_seconds: Mapped[int]
    enabled: Mapped[bool]


class WebhookDelivery(Mutable, Base):
    __tablename__ = "webhook_deliveries"
    subscription_id: Mapped[UUID] = mapped_column(ForeignKey("webhook_subscriptions.id"))
    subscription_version: Mapped[int]
    outbox_id: Mapped[UUID] = mapped_column(ForeignKey("transactional_outbox.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    config_revision: Mapped[int]
    signing_secret_id: Mapped[UUID] = mapped_column(ForeignKey("encrypted_secrets.id"))
    body: Mapped[bytes] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(20))
    attempt_count: Mapped[int]
    max_attempts: Mapped[int]
    retry_base_seconds: Mapped[int]
    max_delay_seconds: Mapped[int]
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("webhook_deliveries.id"))
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class WebhookAttempt(Identity, Base):
    __tablename__ = "webhook_attempts"
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("webhook_deliveries.id"))
    attempt_no: Mapped[int]
    lease_token: Mapped[UUID]
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(20))
    status_code: Mapped[int | None]
    result_code: Mapped[str] = mapped_column(String(80))
    latency_ms: Mapped[int]