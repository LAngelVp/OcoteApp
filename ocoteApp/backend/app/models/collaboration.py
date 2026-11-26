from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class Scoped:
    scope_kind: Mapped[str] = mapped_column(String(20))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"))


class EntityReference:
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("annual_plans.id"))
    objective_id: Mapped[UUID | None] = mapped_column(ForeignKey("objectives.id"))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))


class ServicePrincipal(Mutable, Base):
    __tablename__ = "service_principals"
    name: Mapped[str] = mapped_column(String(120))
    approved_scopes: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    department_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    is_active: Mapped[bool]
    token_version: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class JobRun(Mutable, Base):
    __tablename__ = "job_runs"
    kind: Mapped[str] = mapped_column(String(40))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    service_principal_id: Mapped[UUID] = mapped_column(ForeignKey("service_principals.id"))
    request_id: Mapped[UUID]
    idempotency_key: Mapped[UUID]
    input_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20))
    attempt: Mapped[int]
    retry_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("job_runs.id"))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    configuration_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("configuration_revisions.id")
    )


class OutboxEvent(Identity, Base):
    __tablename__ = "transactional_outbox"
    event_id: Mapped[UUID]
    event_type: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[int]
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    objective_id: Mapped[UUID | None] = mapped_column(ForeignKey("objectives.id"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_service_id: Mapped[UUID | None] = mapped_column(ForeignKey("service_principals.id"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id"))
    payload: Mapped[dict] = mapped_column(JSONB)


class TaskDependency(Mutable, Base):
    __tablename__ = "task_dependencies"
    predecessor_task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    successor_task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool]


class TaskImpediment(Mutable, Base):
    __tablename__ = "task_impediments"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(12))
    kind: Mapped[str] = mapped_column(String(20))
    required_area: Mapped[str | None] = mapped_column(String(120))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class Template(Scoped, Mutable, Base):
    __tablename__ = "templates"
    entity_type: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(120))
    name_normalized: Mapped[str] = mapped_column(String(120))
    current_version: Mapped[int]
    is_active: Mapped[bool]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class TemplateVersion(Identity, Base):
    __tablename__ = "template_versions"
    template_id: Mapped[UUID] = mapped_column(ForeignKey("templates.id"))
    template_version: Mapped[int]
    schema_version: Mapped[int]
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class RecurrenceSchedule(Mutable, Base):
    __tablename__ = "recurrence_schedules"
    template_version_id: Mapped[UUID] = mapped_column(ForeignKey("template_versions.id"))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    service_principal_id: Mapped[UUID] = mapped_column(ForeignKey("service_principals.id"))
    objective_id: Mapped[UUID] = mapped_column(ForeignKey("objectives.id"))
    assignee_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    calendar_id: Mapped[UUID] = mapped_column(ForeignKey("calendar_configs.id"))
    configuration_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("configuration_revisions.id")
    )
    calendar_snapshot: Mapped[dict] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(String(64))
    frequency: Mapped[str] = mapped_column(String(12))
    interval: Mapped[int]
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    occurrence_count: Mapped[int | None]
    end_policy: Mapped[str] = mapped_column(String(12))
    non_business_policy: Mapped[str] = mapped_column(String(12))
    missed_policy: Mapped[str] = mapped_column(String(12))
    next_due_at: Mapped[date | None]
    enabled: Mapped[bool]


class RecurrenceOccurrence(EntityReference, Identity, Base):
    __tablename__ = "recurrence_occurrences"
    schedule_id: Mapped[UUID] = mapped_column(ForeignKey("recurrence_schedules.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_runs.id"))
    scheduled_for: Mapped[date]
    effective_date: Mapped[date]
    timezone: Mapped[str] = mapped_column(String(64))
    calendar_revision_id: Mapped[UUID] = mapped_column(ForeignKey("configuration_revisions.id"))
    result: Mapped[str] = mapped_column(String(12))


class CustomFieldDefinition(Scoped, Mutable, Base):
    __tablename__ = "custom_field_definitions"
    entity_type: Mapped[str] = mapped_column(String(12))
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    data_type: Mapped[str] = mapped_column(String(12))
    constraints: Mapped[dict] = mapped_column(JSONB)
    required_stage_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    required_on_create: Mapped[bool]
    active: Mapped[bool]


class CustomFieldOption(Mutable, Base):
    __tablename__ = "custom_field_options"
    definition_id: Mapped[UUID] = mapped_column(ForeignKey("custom_field_definitions.id"))
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    position: Mapped[int]
    is_active: Mapped[bool]


class CustomFieldValue(EntityReference, Mutable, Base):
    __tablename__ = "custom_field_values"
    definition_id: Mapped[UUID] = mapped_column(ForeignKey("custom_field_definitions.id"))
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    date_value: Mapped[date | None]
    boolean_value: Mapped[bool | None]
    option_id: Mapped[UUID | None] = mapped_column(ForeignKey("custom_field_options.id"))
    option_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(PGUUID(as_uuid=True)))


class Tag(Scoped, Mutable, Base):
    __tablename__ = "tags"
    name_normalized: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(60))
    color_code: Mapped[str] = mapped_column(String(12))
    is_active: Mapped[bool]


class EntityTag(EntityReference, Mutable, Base):
    __tablename__ = "entity_tags"
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("tags.id"))
    assigned_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool]


class Comment(Mutable, Base):
    __tablename__ = "comments"
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    objective_id: Mapped[UUID | None] = mapped_column(ForeignKey("objectives.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    parent_comment_id: Mapped[UUID | None] = mapped_column(ForeignKey("comments.id"))
    current_revision: Mapped[int]
    annulled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommentRevision(Identity, Base):
    __tablename__ = "comment_revisions"
    comment_id: Mapped[UUID] = mapped_column(ForeignKey("comments.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    revision_no: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    annulment: Mapped[bool]


class CommentMention(Identity, Base):
    __tablename__ = "comment_mentions"
    comment_revision_id: Mapped[UUID] = mapped_column(ForeignKey("comment_revisions.id"))
    mentioned_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    notification_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactional_outbox.id")
    )


class SavedView(Scoped, Mutable, Base):
    __tablename__ = "saved_views"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(120))
    filter_schema_version: Mapped[int]
    filters: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool]