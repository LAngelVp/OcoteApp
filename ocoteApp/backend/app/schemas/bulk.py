from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, model_validator

from app.schemas.enterprise import Reauthenticated
from app.schemas.identity import Command, ExactSecret, Reason, Version

EntityType = Literal["plan", "objective", "task"]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Category = Literal[
    "evidence", "audit", "task_history", "evaluations", "releases",
    "import_staging", "reports", "backups",
]


class ImportCreate(Command):
    entity_type: EntityType
    file_format: Literal["csv", "xlsx"]
    content: Annotated[ExactSecret, Field(min_length=4, max_length=13981016)]
    idempotency_key: UUID
    reason: Reason


class ImportPreview(Command):
    expected_version: Version
    mapping: Annotated[dict[str, str], Field(min_length=1, max_length=100)]
    reason: Reason

    @model_validator(mode="after")
    def unique_targets(self):
        if len(set(self.mapping.values())) != len(self.mapping):
            raise ValueError("Import targets must be unique")
        if any(not key or len(key) > 160 or not value or len(value) > 64
               for key, value in self.mapping.items()):
            raise ValueError("Invalid import mapping")
        return self


class ImportCommit(Command):
    expected_version: Version
    preview_hash: Hash
    idempotency_key: UUID
    reason: Reason


class ReportCreate(Command):
    evaluation_id: UUID
    file_format: Literal["pdf", "xlsx"]
    idempotency_key: UUID
    reason: Reason


class RetentionWrite(Reauthenticated):
    category: Category
    minimum_days: Annotated[StrictInt, Field(ge=1, le=36500)]
    legal_hold: StrictBool
    responsible_user_id: UUID
    approval_ref: Annotated[str, Field(min_length=10, max_length=200)]


class BackupRequest(Reauthenticated):
    idempotency_key: UUID


class AgentWrite(Reauthenticated):
    service_principal_id: UUID
    capabilities: Annotated[list[Literal["backup", "restore_verify"]],
                            Field(min_length=1, max_length=2)]
    authentication_secret: Annotated[ExactSecret, Field(min_length=32, max_length=256)]
    destination_ref: UUID

    @model_validator(mode="after")
    def unique_capabilities(self):
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Capabilities must be unique")
        if any(not 33 <= ord(char) <= 126
               for char in self.authentication_secret.get_secret_value()):
            raise ValueError("Agent authentication must use printable ASCII without spaces")
        return self