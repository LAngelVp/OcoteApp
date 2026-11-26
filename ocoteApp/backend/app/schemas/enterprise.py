import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, model_validator

from app.core.branding import validate_palette
from app.core.object_storage import endpoint_parts
from app.schemas.identity import Command, ExactSecret
from app.schemas.platform import Change

MODULES = {
    "subtasks",
    "due_date_requests",
    "kanban",
    "timeline",
    "analytics",
    "evaluations",
    "exports",
    "integrations",
    "calendar",
    "comments",
    "dependencies",
    "impediments",
    "tags",
    "custom_fields",
    "templates",
    "recurrence",
    "search",
    "saved_views",
    "notifications",
    "email_notifications",
    "corporate_messaging",
    "calendar_feeds",
}
FUTURE_MODULES = set()


def civil_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("An ISO civil date is required")
    return date.fromisoformat(value)


CivilDate = Annotated[date, BeforeValidator(civil_date)]


class Reauthenticated(Change):
    current_password: Annotated[ExactSecret, Field(min_length=1, max_length=128)]


class PolicyValues(Command):
    password_min_length: Annotated[StrictInt, Field(ge=12, le=64)]
    require_upper: StrictBool
    require_lower: StrictBool
    require_digit: StrictBool
    require_symbol: StrictBool
    access_ttl_seconds: Annotated[StrictInt, Field(ge=60, le=600)]
    refresh_absolute_seconds: Annotated[StrictInt, Field(ge=3600, le=604800)]
    idle_timeout_seconds: Annotated[StrictInt, Field(ge=60, le=3600)]
    failed_attempt_threshold: Annotated[StrictInt, Field(ge=3, le=10)]
    failed_window_seconds: Annotated[StrictInt, Field(ge=60, le=900)]
    lockout_seconds: Annotated[StrictInt, Field(ge=60, le=3600)]
    page_sizes: Annotated[list[StrictInt], Field(min_length=1, max_length=4)]
    import_max_rows: Annotated[StrictInt, Field(ge=1, le=1000)]
    import_max_bytes: Annotated[StrictInt, Field(ge=1, le=10485760)]
    export_max_bytes: Annotated[StrictInt, Field(ge=1, le=16777216)]

    @model_validator(mode="after")
    def pages(self):
        if (
            5 not in self.page_sizes
            or len(set(self.page_sizes)) != len(self.page_sizes)
            or set(self.page_sizes) - {5, 10, 20, 50}
        ):
            raise ValueError("Page sizes must be a unique subset of 5/10/20/50 retaining 5")
        return self


class PolicyWrite(Reauthenticated):
    values: PolicyValues


class FlagWrite(Reauthenticated):
    code: Annotated[str, Field(min_length=1, max_length=40)]
    enabled: StrictBool

    @model_validator(mode="after")
    def installed(self):
        if self.code not in MODULES | FUTURE_MODULES:
            raise ValueError("Unknown module")
        if self.enabled and self.code not in MODULES:
            raise ValueError("Module is not installed or authorized")
        return self


class BrandingWrite(Reauthenticated):
    organization_name: Annotated[str, Field(min_length=1, max_length=160)]
    organization_name_version: Annotated[StrictInt, Field(ge=0)]
    welcome_text: Annotated[str, Field(max_length=500)]
    footer_text: Annotated[str, Field(max_length=500)]
    token_overrides: dict[str, str]
    logo_asset_id: UUID | None

    @model_validator(mode="after")
    def accessible(self):
        validate_palette(self.token_overrides)
        if any(
            "<" in value or ">" in value
            for value in (self.organization_name, self.welcome_text, self.footer_text)
        ):
            raise ValueError("Plain text only")
        return self


class CalendarWrite(Reauthenticated):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    scope_kind: Literal["organization", "department"]
    department_id: UUID | None
    weekday_mask: Annotated[StrictInt, Field(ge=1, le=127)]
    inheritance: Literal["inherit", "replace"]

    @model_validator(mode="after")
    def scope(self):
        if (self.scope_kind == "department") != (self.department_id is not None):
            raise ValueError("Explicit department required only for department scope")
        if self.scope_kind == "organization" and self.inheritance != "replace":
            raise ValueError("Organization calendar cannot inherit itself")
        return self


class HolidayWrite(Reauthenticated):
    holiday_date: CivilDate
    name: Annotated[str, Field(min_length=1, max_length=120)]
    is_active: StrictBool


class BrandingReset(Reauthenticated):
    organization_name_version: Annotated[StrictInt, Field(ge=0)]


class LogoUpload(Reauthenticated):
    media_type: Literal["image/png", "image/jpeg"]
    content: Annotated[ExactSecret, Field(min_length=4, max_length=1398104)]


class CalendarPreview(Command):
    department_id: UUID | None = None
    start_date: CivilDate
    days: Annotated[StrictInt, Field(ge=0, le=365)]
    mode: Literal["natural", "business"]


class ObjectActivation(Reauthenticated):
    is_active: StrictBool


class ObjectConfig(Command):
    endpoint: Annotated[str, Field(min_length=1, max_length=2048)]
    isolation_prefix: Annotated[str, Field(min_length=1, max_length=200)]
    connect_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=10)]
    read_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=30)]
    evidence_max_bytes: Annotated[StrictInt, Field(ge=1, le=10485760)]
    allowed_mime: Annotated[
        list[Literal["application/pdf", "image/png", "image/jpeg"]],
        Field(min_length=1, max_length=3),
    ]
    retention_days: None
    private_access_attested: StrictBool
    approved_addresses: Annotated[list[str], Field(min_length=1, max_length=32)]
    allow_private_endpoint: StrictBool

    @model_validator(mode="after")
    def safe_destination(self):
        import ipaddress

        endpoint_parts(self.endpoint)
        if (
            not self.private_access_attested
            or ".." in self.isolation_prefix
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_/-]*", self.isolation_prefix)
            or "//" in self.isolation_prefix
            or self.isolation_prefix.endswith("/")
            or len(set(self.allowed_mime)) != len(self.allowed_mime)
        ):
            raise ValueError("An isolated prefix, unique MIME and privacy attestation are required")
        for address in self.approved_addresses:
            parsed = ipaddress.ip_address(address)
            if (
                parsed.is_link_local
                or parsed.is_multicast
                or parsed.is_unspecified
                or parsed.is_reserved
                or (parsed.version == 6 and parsed.ipv4_mapped)
                or (not parsed.is_global and not self.allow_private_endpoint)
            ):
                raise ValueError("Explicit destination approval is required; metadata is forbidden")
        return self


class S3Config(ObjectConfig):
    provider: Literal["s3"]
    bucket: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")]
    region: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    address_style: Literal["virtual_hosted", "path"]

    @model_validator(mode="after")
    def valid_bucket(self):
        if (
            ".." in self.bucket
            or ".-" in self.bucket
            or "-." in self.bucket
            or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", self.bucket)
        ):
            raise ValueError("Invalid bucket name")
        return self


class AzureConfig(ObjectConfig):
    provider: Literal["azure_blob"]
    container: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")]
    account_name: Annotated[str, Field(pattern=r"^[a-z0-9]{3,24}$")]
    auth: Literal["shared_key"]

    @model_validator(mode="after")
    def valid_container(self):
        if "--" in self.container:
            raise ValueError("Invalid container name")
        return self


class S3Credentials(Command):
    access_key: Annotated[ExactSecret, Field(min_length=1, max_length=256)]
    secret_key: Annotated[ExactSecret, Field(min_length=1, max_length=1024)]
    session_token: Annotated[ExactSecret, Field(min_length=1, max_length=16384)] | None = None


class AzureCredentials(Command):
    account_key: Annotated[ExactSecret, Field(min_length=1, max_length=1024)]


class ObjectWrite(Reauthenticated):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    scope_kind: Literal["organization", "department"]
    department_id: UUID | None
    config: Annotated[S3Config | AzureConfig, Field(discriminator="provider")]
    credentials: S3Credentials | AzureCredentials | None = None

    @model_validator(mode="after")
    def bound_scope(self):
        if (self.scope_kind == "department") != (self.department_id is not None):
            raise ValueError("Department required only for department scope")
        expected = S3Credentials if self.config.provider == "s3" else AzureCredentials
        if self.credentials is not None and not isinstance(self.credentials, expected):
            raise ValueError("Credentials belong to another provider")
        return self
