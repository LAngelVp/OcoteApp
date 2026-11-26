from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Computed, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class AnnualPlan(Mutable, Base):
    __tablename__ = "annual_plans"
    template_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("template_versions.id"))
    title: Mapped[str] = mapped_column(String(200))
    horizon_type: Mapped[str] = mapped_column(ForeignKey("horizon_types.code", ondelete="RESTRICT"))
    start_date: Mapped[date]
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(12), default="draft")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Objective(Mutable, Base):
    __tablename__ = "objectives"
    template_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("template_versions.id"))
    annual_plan_id: Mapped[UUID] = mapped_column(ForeignKey("annual_plans.id", ondelete="RESTRICT"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    horizon_type: Mapped[str] = mapped_column(ForeignKey("horizon_types.code", ondelete="RESTRICT"))
    start_date: Mapped[date]
    due_date: Mapped[date]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Task(Mutable, Base):
    __tablename__ = "tasks"
    template_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("template_versions.id"))
    objective_id: Mapped[UUID] = mapped_column(ForeignKey("objectives.id", ondelete="RESTRICT"))
    assignee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_stages.id", ondelete="RESTRICT"))
    priority_id: Mapped[UUID] = mapped_column(ForeignKey("priorities.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date]
    original_due_date: Mapped[date]
    due_date: Mapped[date]
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subtask(Mutable, Base):
    __tablename__ = "subtasks"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date]
    original_due_date: Mapped[date]
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(12), default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class TaskHistory(Identity, Base):
    __tablename__ = "task_history"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    subtask_id: Mapped[UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_service_id: Mapped[UUID | None] = mapped_column(ForeignKey("service_principals.id"))
    actor_kind: Mapped[str] = mapped_column(String(12), Computed(
        "CASE WHEN actor_service_id IS NOT NULL THEN 'service' ELSE 'human' END", persisted=True))
    event_type: Mapped[str] = mapped_column(String(40))
    before_data: Mapped[dict] = mapped_column(JSONB)
    after_data: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[UUID]


class EvidenceFile(Identity, Base):
    __tablename__ = "evidence_files"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    storage_config_id: Mapped[UUID | None] = mapped_column(ForeignKey("integration_configs.id"))
    storage_config_version: Mapped[int | None]
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    scan_engine: Mapped[str] = mapped_column(String(32))
    scan_version: Mapped[str] = mapped_column(String(200))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DueDateRequest(Mutable, Base):
    __tablename__ = "due_date_requests"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    subtask_id: Mapped[UUID | None] = mapped_column(ForeignKey("subtasks.id", ondelete="RESTRICT"))
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    proposed_due_date: Mapped[date]
    previous_due_date: Mapped[date]
    task_version_at_request: Mapped[int]
    subtask_version_at_request: Mapped[int | None]
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
