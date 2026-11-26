"""F8 typed configuration, institutional branding and isolated object providers."""

from alembic import op

revision = "20261125_0007"
down_revision = "20261125_0006"
branch_labels = None
depends_on = None

MUTABLE = (
    "security_policies", "feature_flags", "organization_profiles", "calendar_configs",
    "calendar_holidays",
)


def upgrade():
    op.execute("""
        ALTER TABLE configuration_revisions
            ADD COLUMN sequence BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE;
        GRANT USAGE,SELECT ON SEQUENCE configuration_revisions_sequence_seq TO ocote_runtime;
        ALTER TABLE users ADD COLUMN failed_attempt_count INTEGER NOT NULL DEFAULT 0
            CHECK(failed_attempt_count BETWEEN 0 AND 1000000),
            ADD COLUMN failed_window_at TIMESTAMPTZ,
            ADD COLUMN locked_until TIMESTAMPTZ;
        ALTER TABLE refresh_sessions ADD COLUMN last_seen_at TIMESTAMPTZ,
            ADD CONSTRAINT ck_session_seen CHECK(last_seen_at IS NULL OR last_seen_at>=created_at);
        CREATE TABLE security_policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            instance_id UUID NOT NULL UNIQUE REFERENCES deployment_instances(id) ON DELETE RESTRICT,
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            password_min_length INTEGER NOT NULL CHECK(password_min_length BETWEEN 12 AND 64),
            require_upper BOOLEAN NOT NULL, require_lower BOOLEAN NOT NULL,
            require_digit BOOLEAN NOT NULL, require_symbol BOOLEAN NOT NULL,
            access_ttl_seconds INTEGER NOT NULL CHECK(access_ttl_seconds BETWEEN 60 AND 600),
            refresh_absolute_seconds INTEGER NOT NULL
                CHECK(refresh_absolute_seconds BETWEEN 3600 AND 604800),
            idle_timeout_seconds INTEGER NOT NULL CHECK(idle_timeout_seconds BETWEEN 60 AND 3600),
            failed_attempt_threshold INTEGER NOT NULL
                CHECK(failed_attempt_threshold BETWEEN 3 AND 10),
            failed_window_seconds INTEGER NOT NULL CHECK(failed_window_seconds BETWEEN 60 AND 900),
            lockout_seconds INTEGER NOT NULL CHECK(lockout_seconds BETWEEN 60 AND 3600),
            page_sizes INTEGER[] NOT NULL CHECK(cardinality(page_sizes) BETWEEN 1 AND 4
                AND page_sizes <@ ARRAY[5,10,20,50] AND 5=ANY(page_sizes)
                AND array_position(page_sizes,NULL) IS NULL),
            import_max_rows INTEGER NOT NULL CHECK(import_max_rows BETWEEN 1 AND 1000),
            import_max_bytes INTEGER NOT NULL CHECK(import_max_bytes BETWEEN 1 AND 10485760),
            export_max_bytes INTEGER NOT NULL CHECK(export_max_bytes BETWEEN 1 AND 16777216)
        );
        CREATE TABLE feature_flags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            code VARCHAR(40) NOT NULL UNIQUE CHECK(code IN
                ('subtasks','due_date_requests','kanban','timeline','analytics','evaluations',
                 'exports','integrations','calendar','comments','dependencies','tags','custom_fields')),
            enabled BOOLEAN NOT NULL CHECK(NOT enabled OR code IN
                ('subtasks','due_date_requests','kanban','timeline','analytics','evaluations',
                 'exports','integrations','calendar'))
        );
        CREATE TABLE private_assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            kind VARCHAR(20) NOT NULL CHECK(kind='logo'),
            media_type VARCHAR(40) NOT NULL CHECK(media_type IN ('image/png','image/jpeg')),
            size_bytes INTEGER NOT NULL CHECK(size_bytes BETWEEN 1 AND 1048576),
            sha256 VARCHAR(64) NOT NULL CHECK(sha256~'^[0-9a-f]{64}$'),
            content BYTEA NOT NULL CHECK(octet_length(content)=size_bytes
                AND encode(sha256(content),'hex')=sha256),
            width INTEGER NOT NULL CHECK(width BETWEEN 1 AND 4096),
            height INTEGER NOT NULL CHECK(height BETWEEN 1 AND 4096 AND width*height<=4194304),
            scanned_at TIMESTAMPTZ NOT NULL, scan_version VARCHAR(200) NOT NULL
                CHECK(scan_version LIKE 'ClamAV %')
        );
        CREATE TABLE organization_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            instance_id UUID NOT NULL UNIQUE REFERENCES deployment_instances(id) ON DELETE RESTRICT,
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            logo_asset_id UUID REFERENCES private_assets(id) ON DELETE RESTRICT,
            welcome_text VARCHAR(500) NOT NULL, footer_text VARCHAR(500) NOT NULL,
            token_overrides JSONB NOT NULL CHECK(jsonb_typeof(token_overrides)='object'
                AND token_overrides-ARRAY['primary','primary-dark','on-primary','focus']
                    ='{}'::jsonb)
        );
        CREATE TABLE calendar_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
            scope_kind VARCHAR(20) NOT NULL CHECK(scope_kind IN ('organization','department')),
            department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
            weekday_mask INTEGER NOT NULL CHECK(weekday_mask BETWEEN 1 AND 127),
            inheritance VARCHAR(12) NOT NULL CHECK(inheritance IN ('inherit','replace')),
            CHECK((scope_kind='department')=(department_id IS NOT NULL)),
            CHECK(scope_kind='department' OR inheritance='replace'),
            UNIQUE NULLS NOT DISTINCT(scope_kind,department_id)
        );
        CREATE TABLE calendar_holidays (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
            calendar_id UUID NOT NULL REFERENCES calendar_configs(id) ON DELETE RESTRICT,
            holiday_date DATE NOT NULL, name VARCHAR(120) NOT NULL
                CHECK(length(btrim(name)) BETWEEN 1 AND 120), is_active BOOLEAN NOT NULL,
            UNIQUE(calendar_id,holiday_date)
        );
        ALTER TABLE integration_configs
            DROP CONSTRAINT integration_configs_kind_key,
            DROP CONSTRAINT integration_configs_kind_check,
            ADD CONSTRAINT ck_f8_integration_kind CHECK(kind IN
                ('local_storage','clamav','object_storage')),
            ADD COLUMN provider VARCHAR(20),
            ADD COLUMN name VARCHAR(120),
            ADD COLUMN scope_kind VARCHAR(20),
            ADD COLUMN department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
            ADD COLUMN secret_id UUID REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
            ADD COLUMN configuration_revision_id UUID REFERENCES configuration_revisions(id),
            ADD CONSTRAINT ck_f8_integration_scope CHECK(
                (kind IN ('local_storage','clamav') AND provider IS NULL AND name IS NULL
                    AND scope_kind IS NULL AND department_id IS NULL AND secret_id IS NULL) OR
                (kind='object_storage' AND provider IS NOT NULL
                    AND provider IN ('s3','azure_blob') AND name IS NOT NULL
                    AND length(btrim(name)) BETWEEN 1 AND 120 AND scope_kind IS NOT NULL
                    AND scope_kind IN ('organization','department')
                    AND (scope_kind='department')=(department_id IS NOT NULL)
                    AND secret_id IS NOT NULL AND configuration_revision_id IS NOT NULL));
        DO $$ DECLARE constraint_name text; BEGIN
            SELECT conname INTO STRICT constraint_name FROM pg_constraint
            WHERE conrelid='public.integration_configs'::regclass AND contype='c'
                AND pg_get_constraintdef(oid) LIKE '%config ?%';
            EXECUTE format('ALTER TABLE integration_configs DROP CONSTRAINT %I',constraint_name);
        END $$;
        ALTER TABLE integration_configs ADD CONSTRAINT ck_f8_integration_config CHECK(
            jsonb_typeof(config)='object' AND (
                (kind='local_storage' AND config ? 'root'
                    AND jsonb_typeof(config->'root')='string'
                    AND length(config->>'root') BETWEEN 1 AND 500 AND config-'root'='{}'::jsonb)
                OR (kind='clamav' AND config ?& ARRAY['port','timeout']
                    AND config-ARRAY['port','timeout']='{}'::jsonb
                    AND jsonb_typeof(config->'port')='number'
                    AND jsonb_typeof(config->'timeout')='number'
                    AND (config->>'port')~'^[0-9]+$' AND (config->>'timeout')~'^[0-9]+$'
                    AND (config->>'port')::numeric BETWEEN 1 AND 65535
                    AND (config->>'timeout')::numeric BETWEEN 1 AND 8)
                OR (kind='object_storage' AND config ?& ARRAY['endpoint','isolation_prefix',
                    'connect_timeout_seconds','read_timeout_seconds','allowed_mime',
                    'evidence_max_bytes','private_access_attested','approved_addresses']
                    AND config->>'private_access_attested'='true'
                    AND jsonb_typeof(config->'endpoint')='string'
                    AND config->>'endpoint'~'^https://'
                    AND jsonb_typeof(config->'isolation_prefix')='string'
                    AND length(config->>'isolation_prefix') BETWEEN 1 AND 200
                    AND jsonb_typeof(config->'approved_addresses')='array'
                    AND jsonb_array_length(config->'approved_addresses') BETWEEN 1 AND 32
                    AND jsonb_typeof(config->'allowed_mime')='array'
                    AND jsonb_array_length(config->'allowed_mime') BETWEEN 1 AND 3
                    AND (config->>'evidence_max_bytes')~'^[0-9]+$'
                    AND (config->>'evidence_max_bytes')::numeric BETWEEN 1 AND 10485760
                    AND (config->>'connect_timeout_seconds')~'^[0-9]+$'
                    AND (config->>'connect_timeout_seconds')::numeric BETWEEN 1 AND 10
                    AND (config->>'read_timeout_seconds')~'^[0-9]+$'
                    AND (config->>'read_timeout_seconds')::numeric BETWEEN 1 AND 30)));
        CREATE UNIQUE INDEX uq_f8_local_kind ON integration_configs(kind)
            WHERE kind IN ('local_storage','clamav');
        CREATE UNIQUE INDEX uq_f8_provider_name_scope ON integration_configs
            (provider,lower(name),scope_kind,department_id) NULLS NOT DISTINCT
            WHERE kind='object_storage';
        ALTER TABLE secret_key_versions DROP CONSTRAINT secret_key_versions_purpose_check,
            ADD CONSTRAINT ck_f8_secret_purpose CHECK(purpose IN
                ('jwt_signing','csrf','health_monitor','local_storage','clamav','backup',
                 'object_storage'));
        ALTER TABLE evidence_files
            ADD COLUMN storage_config_id UUID REFERENCES integration_configs(id) ON DELETE RESTRICT,
            ADD COLUMN storage_config_version INTEGER,
            ADD CONSTRAINT ck_f8_evidence_provider CHECK(
                (storage_config_id IS NULL AND storage_config_version IS NULL) OR
                (storage_config_id IS NOT NULL AND storage_config_version>0));
        CREATE INDEX ix_f8_evidence_storage ON evidence_files(storage_config_id);
        CREATE INDEX ix_f8_integration_department ON integration_configs
            (department_id,is_active,id);
        CREATE INDEX ix_f8_integration_secret ON integration_configs(secret_id);
        CREATE INDEX ix_f8_profile_logo ON organization_profiles(logo_asset_id);
        CREATE INDEX ix_f8_calendar_department ON calendar_configs(department_id,created_at,id);
        CREATE INDEX ix_f8_holiday_date ON calendar_holidays(calendar_id,holiday_date,id);
        CREATE INDEX ix_f8_health_version ON integration_health_checks
            (integration_id,config_version,created_at,id);
        CREATE FUNCTION protect_f8_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_OP IN ('DELETE','TRUNCATE') THEN
                RAISE EXCEPTION 'F8 records cannot be discarded' USING ERRCODE='23514';
            END IF;
            IF TG_TABLE_NAME='private_assets' THEN
                RAISE EXCEPTION 'F8 asset immutable' USING ERRCODE='23514';
            END IF;
            IF TG_OP='INSERT' THEN
                IF NEW.version<>1 THEN
                    RAISE EXCEPTION 'Initial version one required' USING ERRCODE='23514';
                END IF;
            ELSE
                IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at
                    OR NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at
                    OR NEW.configuration_revision_id=OLD.configuration_revision_id THEN
                    RAISE EXCEPTION 'F8 immutable identity/revision' USING ERRCODE='23514';
                END IF;
                IF TG_TABLE_NAME='feature_flags' THEN
                    IF NEW.code<>OLD.code THEN
                        RAISE EXCEPTION 'Stable module code' USING ERRCODE='23514';
                    END IF;
                END IF;
                IF TG_TABLE_NAME IN ('organization_profiles','security_policies') THEN
                    IF NEW.instance_id<>OLD.instance_id THEN
                        RAISE EXCEPTION 'Stable instance' USING ERRCODE='23514';
                    END IF;
                END IF;
                IF TG_TABLE_NAME='calendar_holidays' THEN
                    IF NEW.calendar_id<>OLD.calendar_id OR NEW.holiday_date<>OLD.holiday_date THEN
                        RAISE EXCEPTION 'Stable holiday identity' USING ERRCODE='23514';
                    END IF;
                END IF;
                IF TG_TABLE_NAME='calendar_configs' THEN
                    IF NEW.scope_kind<>OLD.scope_kind OR
                        NEW.department_id IS DISTINCT FROM OLD.department_id THEN
                        RAISE EXCEPTION 'Stable calendar scope' USING ERRCODE='23514';
                    END IF;
                END IF;
            END IF;
            IF TG_TABLE_NAME='security_policies' THEN
                IF cardinality(NEW.page_sizes)<>
                    (SELECT count(DISTINCT value) FROM unnest(NEW.page_sizes) value) THEN
                    RAISE EXCEPTION 'Unique page sizes required' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION audit_f8_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM configuration_revisions r JOIN audit_events a
                    ON a.request_id=r.request_id AND a.actor_id=r.actor_id
                    AND a.entity_id=r.entity_id AND a.entity_type=r.entity_type
                WHERE r.id=NEW.configuration_revision_id AND r.entity_id=NEW.id
                    AND r.entity_type=TG_TABLE_NAME AND a.event_type='administration_changed'
            ) THEN RAISE EXCEPTION 'Atomic configuration revision/audit required'
                USING ERRCODE='23514'; END IF;
            RETURN NULL;
        END $$;
        CREATE FUNCTION protect_f8_integration() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ DECLARE changed boolean; BEGIN
            IF TG_OP='DELETE' THEN
                RAISE EXCEPTION 'No provider deletion' USING ERRCODE='23514';
            END IF;
            IF TG_OP='INSERT' THEN
                IF NEW.version<>1 OR NEW.config_revision<>1 OR NEW.is_active
                    OR NEW.tested_version IS NOT NULL THEN
                    RAISE EXCEPTION 'Unverified initial provider' USING ERRCODE='23514';
                END IF;
            ELSE
                IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at
                    OR NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at
                    OR NEW.kind<>OLD.kind OR NEW.provider IS DISTINCT FROM OLD.provider THEN
                    RAISE EXCEPTION 'Provider identity/version immutable' USING ERRCODE='23514';
                END IF;
                changed := (NEW.config,NEW.secret_id,NEW.scope_kind,NEW.department_id,NEW.name)
                    IS DISTINCT FROM
                    (OLD.config,OLD.secret_id,OLD.scope_kind,OLD.department_id,OLD.name);
                IF changed AND (NEW.is_active OR NEW.tested_version IS NOT NULL
                    OR NEW.config_revision<>OLD.config_revision+1) THEN
                    RAISE EXCEPTION 'Provider change invalidates test' USING ERRCODE='23514';
                END IF;
                IF NOT changed AND NEW.config_revision<>OLD.config_revision THEN
                    RAISE EXCEPTION 'Stable configuration revision' USING ERRCODE='23514';
                END IF;
                IF changed AND (NEW.config,NEW.scope_kind,NEW.department_id) IS DISTINCT FROM
                    (OLD.config,OLD.scope_kind,OLD.department_id) AND EXISTS(
                        SELECT 1 FROM evidence_files WHERE storage_config_id=OLD.id) THEN
                    RAISE EXCEPTION 'Existing objects require explicit migration'
                        USING ERRCODE='23514';
                END IF;
            END IF;
            IF NEW.is_active AND NOT EXISTS(SELECT 1 FROM integration_health_checks h
                WHERE h.integration_id=NEW.id AND h.config_version=NEW.config_revision
                    AND h.status='passed' AND h.created_at>=clock_timestamp()-interval '10 minutes')
            THEN RAISE EXCEPTION 'Fresh tested version required' USING ERRCODE='23514'; END IF;
            IF NEW.kind='object_storage' AND NOT EXISTS(SELECT 1 FROM encrypted_secrets s
                WHERE s.id=NEW.secret_id AND s.owner_id=NEW.id AND s.purpose='object_storage')
            THEN RAISE EXCEPTION 'Provider-bound secret required' USING ERRCODE='23514'; END IF;
            RETURN NEW;
        END $$;
        DROP TRIGGER protect_integration_configs ON integration_configs;
        CREATE TRIGGER protect_integration_configs BEFORE INSERT OR UPDATE OR DELETE
            ON integration_configs FOR EACH ROW EXECUTE FUNCTION protect_f8_integration();
        REVOKE ALL ON FUNCTION protect_f8_record(),audit_f8_record(),protect_f8_integration()
            FROM PUBLIC;
    """)
    for table in (*MUTABLE, "private_assets"):
        operations = "INSERT OR UPDATE OR DELETE" if table in MUTABLE else "UPDATE OR DELETE"
        op.execute(f"CREATE TRIGGER protect_{table} BEFORE {operations} ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION protect_f8_record()")
        op.execute(f"CREATE TRIGGER no_truncate_{table} BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION protect_f8_record()")
        op.execute(f"CREATE CONSTRAINT TRIGGER audit_{table} AFTER INSERT OR UPDATE ON {table} "
                   "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_f8_record()")
        op.execute(f"CREATE INDEX ix_f8_revision_{table} ON {table}(configuration_revision_id)")
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        permissions = "SELECT,INSERT,UPDATE" if table in MUTABLE else "SELECT,INSERT"
        op.execute(f"GRANT {permissions} ON {table} TO ocote_runtime")
    op.execute("""
        CREATE CONSTRAINT TRIGGER audit_object_storage AFTER INSERT OR UPDATE
            ON integration_configs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            WHEN(NEW.kind='object_storage') EXECUTE FUNCTION audit_f8_record();
    """)


def downgrade():
    raise RuntimeError("F8 history cannot be discarded; use authorized isolated recovery")