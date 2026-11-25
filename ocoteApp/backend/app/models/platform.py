from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class DeploymentInstance(Mutable, Base):
    __tablename__ = "deployment_instances"
    singleton: Mapped[bool] = mapped_column(Boolean, default=True)
    root_key_ref: Mapped[str] = mapped_column(String(200))
    primary_name: Mapped[str | None] = mapped_column(String(160))
    primary_contact: Mapped[str | None] = mapped_column(String(254))
    backup_name: Mapped[str | None] = mapped_column(String(160))
    backup_contact: Mapped[str | None] = mapped_column(String(254))


class ConfigurationRevision(Identity, Base):
    __tablename__ = "configuration_revisions"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    request_id: Mapped[UUID]
    entity_id: Mapped[UUID]
    entity_type: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(1000))
    changed_keys: Mapped[list] = mapped_column(JSONB)


class SecretKeyVersion(Identity, Base):
    __tablename__ = "secret_key_versions"
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("deployment_instances.id"))
    purpose: Mapped[str] = mapped_column(String(30))
    epoch: Mapped[int]
    root_key_ref: Mapped[str] = mapped_column(String(200))
    algorithm: Mapped[str] = mapped_column(String(20))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)


class EncryptedSecret(Identity, Base):
    __tablename__ = "encrypted_secrets"
    owner_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(30))
    secret_version: Mapped[int]
    key_id: Mapped[UUID] = mapped_column(ForeignKey("secret_key_versions.id"))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class IntegrationConfig(Mutable, Base):
    __tablename__ = "integration_configs"
    kind: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSONB)
    config_revision: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    tested_version: Mapped[int | None]
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationHealthCheck(Identity, Base):
    __tablename__ = "integration_health_checks"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integration_configs.id"))
    config_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(12))
    result_code: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[UUID]
