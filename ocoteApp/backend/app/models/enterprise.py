from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class Configured:
    configuration_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("configuration_revisions.id", ondelete="RESTRICT")
    )


class SecurityPolicy(Configured, Mutable, Base):
    __tablename__ = "security_policies"
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("deployment_instances.id"), unique=True)
    password_min_length: Mapped[int]
    require_upper: Mapped[bool]
    require_lower: Mapped[bool]
    require_digit: Mapped[bool]
    require_symbol: Mapped[bool]
    access_ttl_seconds: Mapped[int]
    refresh_absolute_seconds: Mapped[int]
    idle_timeout_seconds: Mapped[int]
    failed_attempt_threshold: Mapped[int]
    failed_window_seconds: Mapped[int]
    lockout_seconds: Mapped[int]
    page_sizes: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    import_max_rows: Mapped[int]
    import_max_bytes: Mapped[int]
    export_max_bytes: Mapped[int]


class FeatureFlag(Configured, Mutable, Base):
    __tablename__ = "feature_flags"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    enabled: Mapped[bool]


class PrivateAsset(Configured, Identity, Base):
    __tablename__ = "private_assets"
    kind: Mapped[str] = mapped_column(String(20))
    media_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int]
    height: Mapped[int]
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scan_version: Mapped[str] = mapped_column(String(200))


class OrganizationProfile(Configured, Mutable, Base):
    __tablename__ = "organization_profiles"
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("deployment_instances.id"), unique=True)
    logo_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("private_assets.id"))
    welcome_text: Mapped[str] = mapped_column(String(500))
    footer_text: Mapped[str] = mapped_column(String(500))
    token_overrides: Mapped[dict] = mapped_column(JSONB)


class CalendarConfig(Configured, Mutable, Base):
    __tablename__ = "calendar_configs"
    name: Mapped[str] = mapped_column(String(120))
    scope_kind: Mapped[str] = mapped_column(String(20))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"))
    weekday_mask: Mapped[int]
    inheritance: Mapped[str] = mapped_column(String(12))


class CalendarHoliday(Configured, Mutable, Base):
    __tablename__ = "calendar_holidays"
    calendar_id: Mapped[UUID] = mapped_column(ForeignKey("calendar_configs.id"))
    holiday_date: Mapped[date]
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean)