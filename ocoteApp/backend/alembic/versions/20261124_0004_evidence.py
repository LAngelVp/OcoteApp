"""F5 private immutable evidence, without business configuration or seeds."""

from alembic import op

revision = "20261124_0004"
down_revision = "20261124_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE evidence_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            uploaded_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            original_name VARCHAR(255) NOT NULL CHECK(length(btrim(original_name))>0),
            storage_key VARCHAR(32) NOT NULL UNIQUE CHECK(storage_key ~ '^[0-9a-f]{32}$'),
            media_type VARCHAR(100) NOT NULL
                CHECK(media_type IN ('application/pdf','image/png','image/jpeg')),
            size_bytes BIGINT NOT NULL CHECK(size_bytes BETWEEN 1 AND 10485760),
            sha256 CHAR(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
            scan_engine VARCHAR(32) NOT NULL CHECK(scan_engine='clamav'),
            scan_version VARCHAR(200) NOT NULL CHECK(length(btrim(scan_version))>0),
            scanned_at TIMESTAMPTZ NOT NULL CHECK(scanned_at<=created_at)
        );
        CREATE INDEX ix_evidence_task ON evidence_files(task_id,created_at,id);
        CREATE FUNCTION protect_f5_evidence() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
            RAISE EXCEPTION 'Published evidence is immutable' USING ERRCODE='23514';
        END; $$;
        CREATE TRIGGER evidence_immutable BEFORE UPDATE OR DELETE ON evidence_files
            FOR EACH ROW EXECUTE FUNCTION protect_f5_evidence();
        CREATE TRIGGER evidence_no_truncate BEFORE TRUNCATE ON evidence_files
            FOR EACH STATEMENT EXECUTE FUNCTION protect_f5_evidence();
        REVOKE ALL ON FUNCTION protect_f5_evidence() FROM PUBLIC;
        REVOKE ALL ON evidence_files FROM PUBLIC;
        GRANT SELECT,INSERT ON evidence_files TO ocote_runtime;
    """)


def downgrade():
    raise RuntimeError("Evidence/history cannot be discarded; use an authorized recovery protocol")
