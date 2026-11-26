from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, model_validator

from app.schemas.collaboration import MetadataValues
from app.schemas.identity import Command, Reason, Version

Title = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=10000)]
Horizon = Literal["annual", "semiannual", "quarterly", "monthly", "custom"]


def civil_date(value):
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise ValueError("Civil ISO date required")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Civil ISO date required")
    return parsed


CivilDate = Annotated[date, BeforeValidator(civil_date)]


class Period(Command):
    horizon_type: Horizon
    start_date: CivilDate
    due_date: CivilDate

    @model_validator(mode="after")
    def valid_range(self):
        if self.start_date > self.due_date:
            raise ValueError("Invalid inclusive interval")
        return self


class PlanCreate(Period, MetadataValues):
    title: Title


class Versioned(Command):
    expected_version: Version


class PlanUpdate(Versioned):
    title: Title


class PeriodChange(Period, Versioned):
    reason: Reason


class StatusChange(Versioned):
    status: Literal["active", "closed"]
    reason: Reason | None = None


class ObjectiveCreate(PlanCreate):
    annual_plan_id: UUID
    department_id: UUID
    description: Description = ""


class ObjectiveUpdate(PlanUpdate):
    description: Description


class TaskCreate(MetadataValues):
    objective_id: UUID
    assignee_id: UUID
    priority_id: UUID | None = None
    title: Title
    description: Description = ""
    start_date: CivilDate
    due_date: CivilDate


class TaskUpdate(Versioned):
    title: Title
    description: Description
    priority_id: UUID | None = None

    @model_validator(mode="after")
    def no_null_priority(self):
        if "priority_id" in self.model_fields_set and self.priority_id is None:
            raise ValueError("Priority cannot be null")
        return self


class Assignment(Versioned):
    assignee_id: UUID
    reason: Reason


class StageChange(Versioned):
    to_stage_id: UUID
    reason: Reason | None = None
    evidence_ids: Annotated[list[UUID], Field(max_length=100)] = Field(default_factory=list)


class DueChange(Versioned):
    due_date: CivilDate
    reason: Reason


class ScheduleChange(Versioned):
    start_date: CivilDate
    reason: Reason


class SubtaskCreate(Versioned):
    title: Title
    start_date: CivilDate
    due_date: CivilDate


class ChildVersion(Versioned):
    expected_task_version: Version


class SubtaskUpdate(ChildVersion):
    title: Title


class SubtaskDueChange(DueChange):
    expected_task_version: Version


class SubtaskScheduleChange(ScheduleChange):
    expected_task_version: Version


class DateRequest(Command):
    proposed_due_date: CivilDate
    reason: Reason
    expected_task_version: Version


class SubtaskDateRequest(DateRequest):
    expected_subtask_version: Version


class Decision(Versioned):
    reason: Reason
