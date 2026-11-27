from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Identity, Mutable


class ImportJob(Mutable, Base):
    __tablename__ = "import_jobs"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_runs.id"), unique=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"))
    entity_type: Mapped[str] = mapped_column(String(12))
    file_format: Mapped[str] = mapped_column(String(8))
    file_hash: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int]
    scan_version: Mapped[str] = mapped_column(String(200))
    headers: Mapped[list] = mapped_column(JSONB)
    mapping: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(20))
    row_count: Mapped[int]
    error_count: Mapped[int]
    preview_attempts: Mapped[int]
    config_hash: Mapped[str | None] = mapped_column(String(64))
    preview_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    key_id: Mapped[UUID] = mapped_column(ForeignKey("secret_key_versions.id"))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    commit_key: Mapped[UUID | None]
    result_ids: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))


class ImportRow(Identity, Base):
    __tablename__ = "import_rows"
    import_id: Mapped[UUID] = mapped_column(ForeignKey("import_jobs.id"))
    preview_version: Mapped[int]
    row_number: Mapped[int]
    row_hash: Mapped[str] = mapped_column(String(64))
    errors: Mapped[list] = mapped_column(JSONB)
    key_id: Mapped[UUID] = mapped_column(ForeignKey("secret_key_versions.id"))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class ExportJob(Mutable, Base):
    __tablename__ = "export_jobs"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_runs.id"), unique=True)
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    final_evaluation_id: Mapped[UUID] = mapped_column(ForeignKey("evaluations.id"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id"))
    file_format: Mapped[str] = mapped_column(String(8))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calculation_version: Mapped[str] = mapped_column(String(40))
    organization_timezone: Mapped[str] = mapped_column(String(100))
    row_count: Mapped[int]
    byte_count: Mapped[int]
    result_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    key_id: Mapped[UUID] = mapped_column(ForeignKey("secret_key_versions.id"))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class RetentionPolicy(Mutable, Base):
    __tablename__ = "retention_policies"
    category: Mapped[str] = mapped_column(String(30), unique=True)
    minimum_days: Mapped[int]
    legal_hold: Mapped[bool]
    responsible_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    approval_ref: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class BackupRecord(Mutable, Base):
    __tablename__ = "backup_records"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_runs.id"), unique=True)
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("deployment_instances.id"))
    source_backup_id: Mapped[UUID | None] = mapped_column(ForeignKey("backup_records.id"))
    source_revision: Mapped[str] = mapped_column(String(32))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    dump_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    encrypted_key_ref: Mapped[str] = mapped_column(String(200))
    private_location_ref: Mapped[UUID]
    restore_verified: Mapped[bool]
    duration_ms: Mapped[int] = mapped_column(BigInteger)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))