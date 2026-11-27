from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from app.schemas.identity import Command, ExactSecret, Version

Purpose = Literal["local_storage", "clamav", "backup", "jwt_signing", "csrf", "health_monitor",
                  "object_storage", "notifications", "calendar_feed", "integrations",
                  "service_keys", "sso_context"]
Kind = Literal["local_storage", "clamav"]
Reason = Annotated[str, Field(min_length=10, max_length=1000)]


class Change(Command):
    expected_version: Annotated[StrictInt, Field(ge=0)]
    reason: Reason


class Custody(Change):
    expected_version: Version
    primary_name: Annotated[str, Field(min_length=1, max_length=160)] | None
    primary_contact: Annotated[str, Field(min_length=1, max_length=254)] | None
    backup_name: Annotated[str, Field(min_length=1, max_length=160)] | None
    backup_contact: Annotated[str, Field(min_length=1, max_length=254)] | None

    @model_validator(mode="after")
    def independent(self):
        for first, second in (
            (self.primary_name, self.backup_name),
            (self.primary_contact, self.backup_contact),
        ):
            if (
                first
                and second
                and " ".join(first.casefold().split()) == " ".join(second.casefold().split())
            ):
                raise ValueError("Primary and backup must be independent")
        return self


class LocalStorage(Command):
    root: Annotated[str, Field(min_length=1, max_length=500)]


class ClamAVConfig(Command):
    port: Annotated[StrictInt, Field(ge=1, le=65535)]
    timeout: Annotated[StrictInt, Field(ge=1, le=8)]


class IntegrationWrite(Change):
    config: LocalStorage | ClamAVConfig


class Activation(Change):
    expected_version: Version
    is_active: StrictBool


class SecretWrite(Change):
    value: Annotated[ExactSecret, Field(min_length=1, max_length=16384)]


class Rotate(Change):
    expected_version: Version
    purpose: Purpose
