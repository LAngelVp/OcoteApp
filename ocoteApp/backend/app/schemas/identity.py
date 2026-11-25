from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)


def exact_secret(value):
    return SecretStr(value) if isinstance(value, str) else value


ExactSecret = Annotated[SecretStr, BeforeValidator(exact_secret)]
Role = Literal["admin", "gerente", "lider", "colaborador"]
Code = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]
Name = Annotated[str, Field(min_length=1, max_length=120)]
Version = Annotated[StrictInt, Field(ge=1)]
Position = Annotated[StrictInt, Field(ge=0, le=2147483647)]
Reason = Annotated[str, Field(min_length=10, max_length=2000)]
Password = Annotated[ExactSecret, Field(min_length=12, max_length=128)]
Email = Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Command):
    email: Email
    password: Annotated[ExactSecret, Field(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def canonical_email(cls, value):
        return value.lower()


class ChangePassword(Command):
    current_password: Annotated[ExactSecret, Field(min_length=1, max_length=128)]
    new_password: Password


class DepartmentCreate(Command):
    code: Code
    name: Name
    is_active: StrictBool = True
    reason: Reason


class DepartmentUpdate(Command):
    expected_version: Version
    name: Name
    is_active: StrictBool
    reason: Reason


class UserCreate(Command):
    email: Email
    display_name: Name
    password: Password
    role: Role
    department_id: UUID | None = None
    is_active: StrictBool = True
    reason: Reason

    @field_validator("email")
    @classmethod
    def canonical_email(cls, value):
        return value.lower()


class UserUpdate(Command):
    expected_version: Version
    display_name: Name
    role: Role
    department_id: UUID | None = None
    is_active: StrictBool
    reason: Reason


class PasswordReset(Command):
    expected_version: Version
    new_password: Password
    reason: Reason


class CatalogCreate(DepartmentCreate):
    position: Position


class CatalogUpdate(DepartmentUpdate):
    position: Position


class ReorderEntry(Command):
    id: UUID
    position: Position
    expected_version: Version


class CatalogReorder(Command):
    items: Annotated[list[ReorderEntry], Field(min_length=1, max_length=1000)]
    reason: Reason


class SettingCreate(Command):
    key: str
    value: StrictStr | StrictInt
    reason: Reason


class SettingUpdate(Command):
    value: StrictStr | StrictInt
    reason: Reason
    expected_version: Version


class StageCreate(CatalogCreate):
    kind: Literal["open", "blocked", "completed"]
    is_initial: StrictBool = False
    requires_evidence: StrictBool = False
    requires_reason: StrictBool = False


class StageUpdate(CatalogUpdate):
    requires_evidence: StrictBool
    requires_reason: StrictBool


class TransitionCreate(Command):
    from_stage_id: UUID
    to_stage_id: UUID
    allowed_roles: Annotated[list[Literal["admin", "lider", "colaborador"]], Field(min_length=1)]
    is_active: StrictBool = True
    reason: Reason


class TransitionUpdate(Command):
    expected_version: Version
    allowed_roles: Annotated[list[Literal["admin", "lider", "colaborador"]], Field(min_length=1)]
    is_active: StrictBool
    reason: Reason


class WorkflowStageInput(StageCreate):
    expected_version: Version | None = None


class WorkflowEdgeInput(Command):
    from_code: Code
    to_code: Code
    allowed_roles: Annotated[list[Literal["admin", "lider", "colaborador"]], Field(min_length=1)]
    is_active: StrictBool = True
    expected_version: Version | None = None


class WorkflowInput(Command):
    stages: Annotated[list[WorkflowStageInput], Field(min_length=2, max_length=100)]
    transitions: Annotated[list[WorkflowEdgeInput], Field(min_length=1, max_length=1000)]
    reason: Reason
