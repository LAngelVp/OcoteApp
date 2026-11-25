from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mutable(Identity):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Department(Mutable, Base):
    __tablename__ = "departments"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Mutable, Base):
    __tablename__ = "users"
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RefreshSession(Identity, Base):
    __tablename__ = "refresh_sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    family_id: Mapped[UUID]
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_version: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="RESTRICT"), unique=True
    )


class WorkflowStage(Mutable, Base):
    __tablename__ = "workflow_stages"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(12))
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_reason: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowTransition(Mutable, Base):
    __tablename__ = "workflow_transitions"
    from_stage_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="RESTRICT")
    )
    to_stage_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_stages.id", ondelete="RESTRICT"))
    allowed_roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID | None]
    before_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[UUID]
    outcome: Mapped[str] = mapped_column(String(12))


class SystemSetting(Mutable, Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[object] = mapped_column(JSONB)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Priority(Mutable, Base):
    __tablename__ = "priorities"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class HorizonType(Mutable, Base):
    __tablename__ = "horizon_types"
    code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
