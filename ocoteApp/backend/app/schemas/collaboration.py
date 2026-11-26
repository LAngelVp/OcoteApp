from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, StrictBool, StrictFloat, StrictInt, model_validator

from app.schemas.enterprise import CivilDate
from app.schemas.identity import Command, Name, Reason, Version

EntityType = Literal["plan", "objective", "task"]
FieldType = Literal["text", "number", "boolean", "date", "select", "multi_select", "url"]
Key = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]


class Mutation(Command):
    expected_version: Annotated[StrictInt, Field(ge=0)]
    reason: Reason


class Scope(Command):
    scope_kind: Literal["organization", "department"]
    department_id: UUID | None

    @model_validator(mode="after")
    def consistent_scope(self):
        if (self.scope_kind == "department") != (self.department_id is not None):
            raise ValueError("An explicit matching scope is required")
        return self


class DependencyWrite(Mutation):
    predecessor_task_id: UUID
    expected_predecessor_version: Version
    expected_plan_version: Version
    active: StrictBool


class ImpedimentWrite(Mutation):
    owner_user_id: UUID
    severity: Literal["low", "medium", "high", "critical"]
    kind: Literal["internal", "external", "resource", "decision"]
    required_area: Annotated[str, Field(min_length=1, max_length=120)] | None


class ResolveImpediment(Mutation):
    expected_task_version: Version
    resolution: Reason


class MetadataValues(Command):
    custom_fields: Annotated[dict[UUID, JsonValue], Field(max_length=50)] = Field(
        default_factory=dict
    )
    tag_ids: Annotated[list[UUID], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_tags(self):
        if len(set(self.tag_ids)) != len(self.tag_ids):
            raise ValueError("Tags must be unique")
        return self


class MetadataWrite(MetadataValues, Mutation):
    pass


class TagWrite(Scope, Mutation):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    color_code: Literal["forest", "rust", "ink", "danger"]
    is_active: StrictBool


class FieldOption(Command):
    id: UUID | None = None
    expected_version: Annotated[StrictInt, Field(ge=0)]
    code: Key
    label: Name
    position: Annotated[StrictInt, Field(ge=0, le=10000)]
    is_active: StrictBool


class FieldConstraints(Command):
    min_length: Annotated[StrictInt, Field(ge=0, le=2000)] | None = None
    max_length: Annotated[StrictInt, Field(ge=0, le=2000)] | None = None
    min: StrictInt | StrictFloat | None = Field(default=None, allow_inf_nan=False)
    max: StrictInt | StrictFloat | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("Invalid text bounds")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Invalid numeric bounds")
        return self


class FieldWrite(Scope, Mutation):
    entity_type: EntityType
    key: Key
    label: Name
    data_type: FieldType
    constraints: FieldConstraints
    required_stage_ids: Annotated[list[UUID], Field(max_length=50)]
    required_on_create: StrictBool
    active: StrictBool
    options: Annotated[list[FieldOption], Field(max_length=50)]
    expected_impacted_count: Annotated[StrictInt, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def permitted_options(self):
        constraints = self.constraints.model_dump(exclude_none=True)
        allowed = (
            {"min_length", "max_length"}
            if self.data_type == "text"
            else {"min", "max"}
            if self.data_type == "number"
            else set()
        )
        if set(constraints) - allowed:
            raise ValueError("Constraints must match the field type")
        if self.entity_type == "plan" and self.scope_kind != "organization":
            raise ValueError("Plan fields require organization scope")
        if self.data_type not in {"select", "multi_select"} and self.options:
            raise ValueError("Only closed selection fields have options")
        if len({option.code for option in self.options}) != len(self.options):
            raise ValueError("Option codes must be unique")
        if len(set(self.required_stage_ids)) != len(self.required_stage_ids):
            raise ValueError("Stages must be unique")
        if self.entity_type != "task" and self.required_stage_ids:
            raise ValueError("Workflow requirements apply only to tasks")
        return self


class CommentWrite(Mutation):
    expected_resource_version: Version
    body: Annotated[str, Field(min_length=1, max_length=10000)]
    parent_comment_id: UUID | None = None
    mention_ids: Annotated[list[UUID], Field(max_length=50)] = Field(default_factory=list)
    annulled: StrictBool = False


class SubtaskBlueprint(Command):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    start_offset_days: Annotated[StrictInt, Field(ge=0, le=36600)]
    duration_days: Annotated[StrictInt, Field(ge=1, le=36600)]


class Blueprint(MetadataValues):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=10000)]
    horizon_type: Literal["annual", "semiannual", "quarterly", "monthly", "custom"]
    priority_id: UUID | None
    start_offset_days: Annotated[StrictInt, Field(ge=0, le=36600)] = 0
    duration_days: Annotated[StrictInt, Field(ge=1, le=36600)]
    subtasks: Annotated[list[SubtaskBlueprint], Field(max_length=100)]
    objectives: Annotated[list["Blueprint"], Field(max_length=50)] = Field(default_factory=list)
    tasks: Annotated[list["Blueprint"], Field(max_length=50)] = Field(default_factory=list)


class TemplateWrite(Scope, Mutation):
    entity_type: EntityType
    name: Name
    is_active: StrictBool
    payload: Blueprint


class TemplateBinding(Command):
    path: Annotated[
        str, Field(max_length=100, pattern=r"^(root|tasks\.\d+|objectives\.\d+(\.tasks\.\d+)?)$")
    ]
    department_id: UUID | None
    assignee_id: UUID | None


class InstantiateTemplate(Mutation):
    template_version_id: UUID
    start_date: CivilDate
    due_date: CivilDate
    horizon_type: Literal["annual", "semiannual", "quarterly", "monthly", "custom"]
    annual_plan_id: UUID | None
    objective_id: UUID | None
    bindings: Annotated[list[TemplateBinding], Field(min_length=1, max_length=100)]
    activate_plan: StrictBool


class PrincipalWrite(Mutation):
    name: Name
    department_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    approved_scopes: Annotated[
        list[Literal["tasks:create", "subtasks:create"]], Field(min_length=1, max_length=2)
    ]
    is_active: StrictBool


class RecurrenceRule(Command):
    frequency: Literal["daily", "weekly", "monthly", "yearly"]
    interval: Annotated[StrictInt, Field(ge=1, le=366)]
    start_date: CivilDate
    end_date: CivilDate | None
    occurrence_count: Annotated[StrictInt, Field(ge=1, le=1000)] | None
    end_policy: Literal["skip", "last_day"]
    non_business_policy: Literal["keep", "skip", "next", "previous"]
    missed_policy: Literal["skip", "catch_up"]

    @model_validator(mode="after")
    def bounded(self):
        if (self.end_date is None) == (self.occurrence_count is None):
            raise ValueError("Choose an end date or occurrence count")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Invalid end date")
        return self


class RecurrenceWrite(RecurrenceRule, Mutation):
    template_version_id: UUID
    owner_user_id: UUID
    service_principal_id: UUID
    objective_id: UUID
    assignee_id: UUID
    calendar_id: UUID
    enabled: StrictBool


class RecurrenceRun(Mutation):
    idempotency_key: UUID
    through_date: CivilDate
    limit: Annotated[StrictInt, Field(ge=1, le=100)]


class FieldFilter(Command):
    definition_id: UUID
    operator: Literal["eq", "contains", "gte", "lte"]
    value: JsonValue


class SearchFilters(Command):
    q: Annotated[str, Field(max_length=200)] = ""
    entity_type: Literal["plan", "objective", "task", "comment"] | None = None
    tag_ids: Annotated[list[UUID], Field(max_length=20)] = Field(default_factory=list)
    blocked: StrictBool | None = None
    stage_id: UUID | None = None
    assignee_id: UUID | None = None
    custom_fields: Annotated[list[FieldFilter], Field(max_length=20)] = Field(default_factory=list)


class SavedViewWrite(Mutation):
    name: Name
    entity_type: Literal["plan", "objective", "task", "comment"]
    scope_kind: Literal["personal", "department", "organization"]
    department_id: UUID | None
    filters: SearchFilters
    active: StrictBool
