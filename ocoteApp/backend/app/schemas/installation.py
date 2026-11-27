from ipaddress import ip_address
from typing import Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator

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
