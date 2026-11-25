"""F1 technical release ledger; no identity or business tables."""

import sqlalchemy as sa

from alembic import op

revision = "20261124_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("application_version", sa.String(40), nullable=False),
        sa.Column("artifact_sha256", sa.CHAR(64), nullable=False),
        sa.Column("manifest_sha256", sa.CHAR(64), nullable=False),
        sa.Column("source_revision", sa.String(128), nullable=True),
        sa.Column("target_revision", sa.String(128), nullable=False),
        sa.Column("operator_ref", sa.String(120), nullable=False),
        sa.Column("deployment_mode", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("status", sa.String(12), server_default="running", nullable=False),
        sa.Column("backup_manifest_sha256", sa.CHAR(64), nullable=True),
        sa.Column("backup_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_code", sa.String(64), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["retry_of_id"],
            ["release_history.id"],
            ondelete="RESTRICT",
            name="fk_release_history_retry",
        ),
        sa.UniqueConstraint("request_id", name="uq_release_history_request_id"),
        sa.CheckConstraint("version > 0", name="ck_release_history_version"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_release_history_updated"),
        sa.CheckConstraint("retry_of_id <> id", name="ck_release_history_retry"),
        sa.CheckConstraint(
            "artifact_sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$' "
            "AND (backup_manifest_sha256 IS NULL OR "
            "backup_manifest_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_release_history_hashes",
        ),
        sa.CheckConstraint(
            "deployment_mode IN ('local', 'managed')",
            name="ck_release_history_mode",
        ),
        sa.CheckConstraint(
            "phase IN ('preflight','backup','migration','seeds','validation',"
            "'reopening','complete')",
            name="ck_release_history_phase",
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','aborted')",
            name="ck_release_history_status",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND result_code IS NULL) OR "
            "(status <> 'running' AND finished_at IS NOT NULL AND "
            "finished_at >= created_at AND result_code IS NOT NULL)",
            name="ck_release_history_terminal",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR (phase = 'complete' AND "
            "(source_revision IS NULL OR (backup_verified_at IS NOT NULL AND "
            "backup_manifest_sha256 IS NOT NULL)))",
            name="ck_release_history_success",
        ),
        sa.CheckConstraint(
            "backup_verified_at IS NULL OR (backup_manifest_sha256 IS NOT NULL AND "
            "backup_verified_at >= created_at)",
            name="ck_release_history_backup",
        ),
        schema="public",
    )
    op.create_index("ix_release_history_created", "release_history", ["created_at", "id"])
    op.create_index(
        "ix_release_history_application",
        "release_history",
        ["application_version", "created_at"],
    )
    op.create_index("ix_release_history_retry", "release_history", ["retry_of_id"])
    op.execute("""
        CREATE FUNCTION public.protect_release_history() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Release records cannot be deleted' USING ERRCODE = '23514';
            END IF;
            IF OLD.status <> 'running' THEN
                RAISE EXCEPTION 'Terminal release is immutable' USING ERRCODE = '23514';
            END IF;
            IF (to_jsonb(NEW) - ARRAY['updated_at','version','phase','status',
                'backup_manifest_sha256','backup_verified_at','finished_at','result_code'])
                IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['updated_at','version','phase','status',
                'backup_manifest_sha256','backup_verified_at','finished_at','result_code'])
               OR NEW.version <> OLD.version + 1 OR NEW.updated_at < OLD.updated_at THEN
                RAISE EXCEPTION 'Invalid release transition' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_release_history BEFORE UPDATE OR DELETE ON public.release_history
        FOR EACH ROW EXECUTE FUNCTION public.protect_release_history()
    """)
    op.execute("REVOKE ALL ON FUNCTION public.protect_release_history() FROM PUBLIC")
    op.execute("REVOKE ALL ON public.release_history, public.alembic_version FROM PUBLIC")
    op.execute("GRANT SELECT ON public.release_history, public.alembic_version TO ocote_runtime")


def downgrade() -> None:
    raise RuntimeError(
        "Release history is preserved; use an approved fix-forward or isolated restore"
    )
