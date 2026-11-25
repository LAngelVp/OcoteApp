from ipaddress import ip_address
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_NAME = "ocoteAppDatabase"


def validate_database_url(value: SecretStr) -> SecretStr:
    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        raise ValueError("Invalid PostgreSQL connection configuration") from None
    if (
        url.drivername != "postgresql+psycopg"
        or url.database != DATABASE_NAME
        or not url.host
        or not url.username
        or url.username == "postgres"
        or not url.password
        or url.port is None
    ):
        raise ValueError("Use psycopg, the exact application database and a dedicated role")
    if set(url.query) - {"sslmode", "sslrootcert"}:
        raise ValueError("Unsupported connection options")
    return value


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    deployment_mode: Literal["local", "managed"] = "local"

    def validate_transport(self, connection: SecretStr) -> None:
        url = make_url(connection.get_secret_value())
        if self.deployment_mode == "local":
            if url.host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Local mode requires a loopback endpoint")
            if self.app_env == "production":
                raise ValueError("Production requires a separately approved deployment profile")
        else:
            if url.query.get("sslmode") != "verify-full":
                raise ValueError("Managed PostgreSQL requires sslmode=verify-full")
            certificate = url.query.get("sslrootcert")
            if not isinstance(certificate, str) or not Path(certificate).is_file():
                raise ValueError("Managed PostgreSQL requires a readable CA file")
            try:
                ip_address(url.host)
            except ValueError:
                pass
            else:
                raise ValueError("Managed PostgreSQL requires a certificate hostname")


class Settings(EnvironmentSettings):
    database_url: SecretStr
    health_token: SecretStr = Field(min_length=32)
    organization_timezone: str
    db_pool_size: int = Field(default=3, ge=1, le=20)
    db_max_overflow: int = Field(default=0, ge=0, le=10)
    db_pool_timeout: int = Field(default=3, ge=1, le=30)
    db_connect_timeout: int = Field(default=3, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    db_lock_timeout_ms: int = Field(default=2000, ge=100, le=30000)
    db_idle_transaction_timeout_ms: int = Field(default=10000, ge=1000, le=60000)

    _database = field_validator("database_url")(validate_database_url)

    @field_validator("organization_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Use an installed IANA timezone") from None
        return value

    @model_validator(mode="after")
    def valid_transport(self) -> Self:
        if make_url(self.database_url.get_secret_value()).username != "ocote_runtime":
            raise ValueError("The API requires its dedicated runtime role")
        self.validate_transport(self.database_url)
        return self


class MigrationSettings(EnvironmentSettings):
    migration_database_url: SecretStr

    _database = field_validator("migration_database_url")(validate_database_url)

    @model_validator(mode="after")
    def valid_transport(self) -> Self:
        if make_url(self.migration_database_url.get_secret_value()).username != "ocote_migrador":
            raise ValueError("Alembic requires its dedicated migration role")
        self.validate_transport(self.migration_database_url)
        return self
