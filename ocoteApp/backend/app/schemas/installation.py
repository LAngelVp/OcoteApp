from ipaddress import ip_address
from typing import Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, StrictInt, field_validator, model_validator

from app.schemas.identity import Command, ExactSecret, UserCreate


def https_origin(value: str) -> str:
    origin = urlsplit(value)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path
        or origin.query
        or origin.fragment
        or value != f"https://{origin.netloc}"
    ):
        raise ValueError("An exact HTTPS origin is required")
    if origin.port is not None and not 1 <= origin.port <= 65535:
        raise ValueError("Invalid origin port")
    return value


class Connection(Command):
    mode: Literal["local", "managed"]
    host: str = Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9.:-]+$")
    approved_address: str
    port: int = Field(ge=1, le=65535)
    database: Literal["ocoteAppDatabase"]
    runtime_role: Literal["ocote_runtime"]
    migrator_role: Literal["ocote_migrador"]
    runtime_password: ExactSecret = Field(min_length=1, max_length=1024)
    migrator_password: ExactSecret = Field(min_length=1, max_length=1024)
    sslmode: Literal["disable", "verify-full"]
    ca_pem: str = Field(default="", max_length=65536)

    @model_validator(mode="after")
    def transport(self) -> Self:
        address = ip_address(self.approved_address)
        if address.is_unspecified or address.is_multicast:
            raise ValueError("An approved server address is required")
        if self.runtime_password == self.migrator_password:
            raise ValueError("SQL identities require distinct credentials")
        if self.mode == "local":
            if self.host not in {"127.0.0.1", "::1", "localhost"} or not address.is_loopback:
                raise ValueError("Local PostgreSQL requires loopback")
            if self.sslmode != "disable" or self.ca_pem:
                raise ValueError("Local transport must be explicit")
        else:
            if self.sslmode != "verify-full" or not self.ca_pem or "PRIVATE KEY" in self.ca_pem:
                raise ValueError("Managed PostgreSQL requires verify-full and a public CA")
            try:
                ip_address(self.host)
            except ValueError:
                pass
            else:
                raise ValueError("Managed PostgreSQL requires a certificate hostname")
        return self


class Install(Command):
    connection: Connection
    test_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    admin: UserCreate
    organization_timezone: str

    @field_validator("organization_timezone")
    @classmethod
    def timezone(cls, value):
        ZoneInfo(value)
        return value

    @model_validator(mode="after")
    def first_admin(self) -> Self:
        if self.admin.role != "admin" or self.admin.department_id or not self.admin.is_active:
            raise ValueError("An explicit first administrator is required")
        if self.admin.password in {
            self.connection.runtime_password,
            self.connection.migrator_password,
        }:
            raise ValueError("Administrator credentials must be independent")
        return self


def secret_values(body: Connection) -> dict:
    return {
        name: value.get_secret_value() if isinstance(value, SecretStr) else value
        for name, value in body.__dict__.items()
    }


class PortableLocal(Command):
    database: Literal["ocoteAppDatabase"] = "ocoteAppDatabase"
    port: StrictInt = Field(default=5432, ge=1, le=65535)
    data_directory: str = Field(default="postgres-data", min_length=1, max_length=500)
    postgres_password: ExactSecret = Field(min_length=14, max_length=128)
    migrator_password: ExactSecret = Field(min_length=14, max_length=128)
    runtime_password: ExactSecret = Field(min_length=14, max_length=128)

    @model_validator(mode="after")
    def safe_passwords(self) -> Self:
        values = [value.get_secret_value() for value in (
            self.postgres_password, self.migrator_password, self.runtime_password,
        )]
        if len(set(values)) != 3:
            raise ValueError("Three independent local PostgreSQL credentials are required")
        for value in values:
            classes = sum((any(character.islower() for character in value),
                           any(character.isupper() for character in value),
                           any(character.isdigit() for character in value),
                           any(not character.isalnum() for character in value)))
            if classes < 3 or any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise ValueError("Local credentials require14 characters and3 character classes")
        if any(ord(character) < 32 for character in self.data_directory):
            raise ValueError("Invalid local state path")
        return self

    def connection(self):
        return Connection(mode="local", host="127.0.0.1", approved_address="127.0.0.1",
                          port=self.port, database=self.database, runtime_role="ocote_runtime",
                          migrator_role="ocote_migrador", runtime_password=self.runtime_password,
                          migrator_password=self.migrator_password, sslmode="disable")


class LocalInstall(Command):
    local: PortableLocal
    admin: UserCreate
    organization_timezone: str

    @model_validator(mode="after")
    def explicit_administrator(self) -> Self:
        try:
            ZoneInfo(self.organization_timezone)
        except (ValueError, KeyError):
            raise ValueError("Use an installed IANA timezone") from None
        Install(connection=self.local.connection(), test_id="0" * 32, admin=self.admin,
                organization_timezone=self.organization_timezone)
        if self.admin.password == self.local.postgres_password:
            raise ValueError("Administrator credentials must be independent of PostgreSQL")
        return self
