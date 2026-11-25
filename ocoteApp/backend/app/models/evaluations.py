from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Mutable


class Evaluation(Mutable, Base):
    __tablename__ = "evaluations"
    annual_plan_id: Mapped[UUID] = mapped_column(ForeignKey("annual_plans.id", ondelete="RESTRICT"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    evaluator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    period_start: Mapped[date]
    period_end: Mapped[date]
    status: Mapped[str] = mapped_column(String(12), default="draft")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(JSONB)
    calculation_version: Mapped[str] = mapped_column(String(20))
    organization_timezone: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationItem(Base):
    __tablename__ = "evaluation_items"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    evaluation_id: Mapped[UUID] = mapped_column(ForeignKey("evaluations.id", ondelete="RESTRICT"))
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    snapshot_data: Mapped[dict] = mapped_column(JSONB)
