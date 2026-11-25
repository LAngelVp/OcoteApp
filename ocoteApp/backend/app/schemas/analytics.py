from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.identity import Command
from app.schemas.operations import CivilDate, Versioned


class AnalyticsFilters(Command):
    annual_plan_id: UUID | None = None
    department_id: UUID | None = None
    assignee_id: UUID | None = None
    period_start: CivilDate | None = None
    period_end: CivilDate | None = None
    status: Literal["open", "blocked", "completed"] | None = None
    punctuality_status: Literal["on_time", "late", "pending", "overdue"] | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("Both period boundaries are required")
        if self.period_start and self.period_start > self.period_end:
            raise ValueError("Invalid inclusive period")
        return self


class SummaryQuery(AnalyticsFilters):
    limit: int = Field(default=5, ge=1, le=100)
    cursor: UUID | None = None


class SeriesQuery(AnalyticsFilters):
    limit: int = Field(default=5, ge=1, le=100)
    cursor: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class EvaluationCreate(Command):
    annual_plan_id: UUID
    department_id: UUID
    period_start: CivilDate
    period_end: CivilDate

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_start > self.period_end:
            raise ValueError("Invalid inclusive period")
        return self


class EvaluationFinalize(Versioned):
    summary: str

    @model_validator(mode="after")
    def valid_summary(self):
        if not 10 <= len(self.summary) <= 4000:
            raise ValueError("Summary must contain 10..4000 characters")
        return self


class TaskExport(AnalyticsFilters):
    format: Literal["json", "csv"]


class EvaluationExport(Command):
    format: Literal["json", "csv"]
