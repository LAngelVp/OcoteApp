import ipaddress
import re
from datetime import datetime
from email.headerregistry import Address
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from app.schemas.collaboration import PrincipalWrite as CollaborationPrincipalWrite
from app.schemas.enterprise import Reauthenticated
from app.schemas.identity import Command, ExactSecret
from app.schemas.platform import Change

Provider = Literal["smtp", "slack", "teams", "telegram"]
Channel = Literal["in_app", "email", "messaging"]
Trigger = Literal[
    "assignment",
    "mention",
    "upcoming_due",
    "overdue",
    "due_date_request",
    "due_date_decision",
    "impediment",
    "evaluation_finalized",
]


def email_address(value):
    try:
        if not value.isascii() or any(character in value for character in "\r\n\x00"):
            raise ValueError
        address = Address(addr_spec=value)
        if not address.username or not address.domain or address.addr_spec != value:
            raise ValueError
    except (ValueError, IndexError):
        raise ValueError("An exact email address is required") from None
    return value


class NetworkConfig(Command):
    host: Annotated[
        str, Field(min_length=1, max_length=253, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")
    ]
    approved_addresses: Annotated[list[str], Field(min_length=1, max_length=16)]
    connect_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=10)]
    read_timeout_seconds: Annotated[StrictInt, Field(ge=1, le=15)]
    rate_per_minute: Annotated[StrictInt, Field(ge=1, le=1000)]
    audience_approved: StrictBool

    @field_validator("approved_addresses")
    @classmethod
    def addresses(cls, values):
        result = []
        for value in values:
            address = ipaddress.ip_address(value)
            if (
                address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_unspecified
                or address.is_reserved
                or address.version == 6
                and address.ipv4_mapped
            ):
                raise ValueError("Unsafe address")
            result.append(str(address))
        if len(set(result)) != len(result):
            raise ValueError("Duplicate addresses")
        return result


class SMTPConfig(NetworkConfig):
    provider: Literal["smtp"]
    port: Annotated[StrictInt, Field(ge=1, le=65535)]
    security: Literal["tls", "starttls"]
    allow_private_endpoint: StrictBool
    authentication: Literal["none", "login"]
    username: Annotated[str, Field(min_length=1, max_length=254)] | None
    sender_email: Annotated[str, Field(min_length=3, max_length=254)]
    sender_name: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[^\r\n\x00]+$")]
    test_recipient: Annotated[str, Field(min_length=3, max_length=254)]

    _emails = field_validator("sender_email", "test_recipient")(email_address)

    @model_validator(mode="after")
    def approved(self):
        if (self.authentication == "login") != (self.username is not None):
            raise ValueError("Explicit SMTP authentication is required")
        if not self.allow_private_endpoint and any(
            not ipaddress.ip_address(value).is_global for value in self.approved_addresses
        ):
            raise ValueError("Private SMTP endpoint is not approved")
        return self


class ChatConfig(NetworkConfig):
    provider: Literal["slack", "teams", "telegram"]
    allow_private_endpoint: Literal[False]
    destination: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[^\r\n\x00]+$")]

    @model_validator(mode="after")
    def approved(self):
        expected = {"slack": "hooks.slack.com", "telegram": "api.telegram.org"}
        if self.provider in expected and self.host != expected[self.provider]:
            raise ValueError("Unsupported provider host")
        if self.provider == "teams" and not any(
            self.host.endswith(suffix)
            for suffix in (".webhook.office.com", ".logic.azure.com", ".api.powerplatform.com")
        ):
            raise ValueError("Unsupported Teams host")
        if any(not ipaddress.ip_address(value).is_global for value in self.approved_addresses):
            raise ValueError("Public provider endpoint required")
        if self.provider == "telegram" and not re.fullmatch(
            r"-?[0-9]{1,20}|@[a-zA-Z0-9_]{5,64}", self.destination
        ):
            raise ValueError("Invalid Telegram destination")
        return self


ConnectorConfig = Annotated[SMTPConfig | ChatConfig, Field(discriminator="provider")]


class ConnectorWrite(Reauthenticated):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    scope_kind: Literal["organization", "department"]
    department_id: UUID | None
    config: ConnectorConfig
    credential: Annotated[ExactSecret, Field(min_length=1, max_length=16384)] | None = None

    @model_validator(mode="after")
    def scoped(self):
        if (self.scope_kind == "department") != (self.department_id is not None):
            raise ValueError("Explicit department scope required")
        return self


class ConnectorTest(Reauthenticated):
    destination: Annotated[str, Field(min_length=1, max_length=254)]
    confirmed: Literal[True]


class PrincipalWrite(Reauthenticated, CollaborationPrincipalWrite):
    pass


class RuleWrite(Reauthenticated):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    department_id: UUID | None
    trigger: Trigger
    recipient_mode: Literal[
        "assignee", "mentioned", "requester", "department_leaders", "admins", "evaluator"
    ]
    channels: Annotated[list[Channel], Field(min_length=1, max_length=3)]
    connector_ids: Annotated[list[UUID], Field(max_length=20)]
    threshold_days: Annotated[StrictInt, Field(ge=0, le=365)] | None
    day_basis: Literal["natural", "business"]
    max_age_hours: Annotated[StrictInt, Field(ge=1, le=720)]
    max_attempts: Annotated[StrictInt, Field(ge=1, le=10)]
    retry_base_seconds: Annotated[StrictInt, Field(ge=5, le=300)]
    enabled: StrictBool

    @model_validator(mode="after")
    def bounded(self):
        if (self.trigger in {"upcoming_due", "overdue"}) != (self.threshold_days is not None):
            raise ValueError("Threshold only applies to date triggers")
        if len(set(self.channels)) != len(self.channels) or len(set(self.connector_ids)) != len(
            self.connector_ids
        ):
            raise ValueError("Duplicate channels or connectors")
        if (set(self.channels) - {"in_app"}) and not self.connector_ids:
            raise ValueError("External channels require explicit connectors")
        return self


class PreferencesWrite(Change):
    channels: Annotated[list[Channel], Field(min_length=1, max_length=3)]
    opt_in: StrictBool
    quiet_start: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")] | None
    quiet_end: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")] | None
    timezone: Annotated[str, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("An installed IANA timezone is required") from None
        if (
            (self.quiet_start is None) != (self.quiet_end is None)
            or (self.quiet_start is not None and self.quiet_start == self.quiet_end)
            or len(set(self.channels)) != len(self.channels)
        ):
            raise ValueError("Invalid quiet hours or duplicate channels")
        return self


class FeedCreate(Change):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("An offset-aware expiration is required")
        return value
