"""F12 bounded imports, sealed reports and separate operations metadata; no seeds."""

from alembic import op

revision = "20261126_0011"
down_revision = "20261126_0010"
branch_labels = None
depends_on = None

IDENTITY = (
    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()"
)
MUTABLE = (
    IDENTITY + ", updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), "
    "version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at)"
)
PAYLOAD = """
    key_id UUID NOT NULL REFERENCES secret_key_versions(id) ON DELETE RESTRICT,
    nonce BYTEA NOT NULL CHECK(octet_length(nonce)=12),
    ciphertext BYTEA NOT NULL CHECK(octet_length(ciphertext) BETWEEN 17 AND 16777232),
    UNIQUE(key_id,nonce)
"""
TABLES = {
    "import_jobs": (MUTABLE, """
        job_id UUID NOT NULL UNIQUE REFERENCES job_runs(id) ON DELETE RESTRICT,
        actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
        entity_type VARCHAR(12) NOT NULL CHECK(entity_type IN ('plan','objective','task')),
        file_format VARCHAR(8) NOT NULL CHECK(file_format IN ('csv','xlsx')),
        file_hash VARCHAR(64) NOT NULL CHECK(file_hash~'^[0-9a-f]{64}$'),
        file_size INTEGER NOT NULL CHECK(file_size BETWEEN 1 AND 10485760),
        scan_version VARCHAR(200) NOT NULL CHECK(length(scan_version)>0),
        headers JSONB NOT NULL CHECK(jsonb_typeof(headers)='array'
            AND jsonb_array_length(headers) BETWEEN 1 AND 100),
        mapping JSONB NOT NULL CHECK(jsonb_typeof(mapping)='object'),
        state VARCHAR(20) NOT NULL CHECK(state IN
            ('uploaded','previewed','rejected','committed','expired')),
        row_count INTEGER NOT NULL CHECK(row_count BETWEEN 1 AND 1000),
        error_count INTEGER NOT NULL CHECK(error_count BETWEEN 0 AND 100000),
        preview_attempts INTEGER NOT NULL CHECK(preview_attempts BETWEEN 0 AND 10),
        config_hash VARCHAR(64) CHECK(config_hash IS NULL OR config_hash~'^[0-9a-f]{64}$'),
        preview_hash VARCHAR(64) CHECK(preview_hash IS NULL OR preview_hash~'^[0-9a-f]{64}$'),
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at
            AND expires_at<=created_at+interval '1 day'),
        commit_key UUID, result_ids JSONB,
        CHECK((state='committed')=(commit_key IS NOT NULL AND result_ids IS NOT NULL)),
        CHECK(result_ids IS NULL OR (jsonb_typeof(result_ids)='array'
            AND jsonb_array_length(result_ids)=row_count)),
        CHECK(state NOT IN ('previewed','committed') OR
            (preview_hash IS NOT NULL AND config_hash IS NOT NULL AND error_count=0))
    ,""" + PAYLOAD),
    "import_rows": (IDENTITY, """
        import_id UUID NOT NULL REFERENCES import_jobs(id) ON DELETE RESTRICT,
        preview_version INTEGER NOT NULL CHECK(preview_version BETWEEN 2 AND 11),
        row_number INTEGER NOT NULL CHECK(row_number BETWEEN 1 AND 1000),
        row_hash VARCHAR(64) NOT NULL CHECK(row_hash~'^[0-9a-f]{64}$'),
        errors JSONB NOT NULL CHECK(jsonb_typeof(errors)='array'
            AND jsonb_array_length(errors)<=100),
        UNIQUE(import_id,preview_version,row_number)
    ,""" + PAYLOAD),
    "export_jobs": (MUTABLE, """
        job_id UUID NOT NULL UNIQUE REFERENCES job_runs(id) ON DELETE RESTRICT,
        requester_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        final_evaluation_id UUID NOT NULL REFERENCES evaluations(id) ON DELETE RESTRICT,
        department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
        file_format VARCHAR(8) NOT NULL CHECK(file_format IN ('pdf','xlsx')),
        snapshot_at TIMESTAMPTZ NOT NULL,
        calculation_version VARCHAR(40) NOT NULL CHECK(length(calculation_version)>0),
        organization_timezone VARCHAR(100) NOT NULL CHECK(length(organization_timezone)>0),
        row_count INTEGER NOT NULL CHECK(row_count BETWEEN 0 AND 10000),
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 16777216),
        result_hash VARCHAR(64) NOT NULL CHECK(result_hash~'^[0-9a-f]{64}$'),
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at
            AND expires_at<=created_at+interval '1 day')
    ,""" + PAYLOAD),
    "retention_policies": (MUTABLE, """
        category VARCHAR(30) NOT NULL UNIQUE CHECK(category IN
            ('evidence','audit','task_history','evaluations','releases',
                'import_staging','reports','backups')),
        minimum_days INTEGER NOT NULL CHECK(minimum_days BETWEEN 1 AND 36500),
        legal_hold BOOLEAN NOT NULL,
        responsible_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        approval_ref VARCHAR(200) NOT NULL CHECK(length(btrim(approval_ref)) BETWEEN 10 AND 200),
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
    """),
    "backup_records": (MUTABLE, """
        job_id UUID NOT NULL UNIQUE REFERENCES job_runs(id) ON DELETE RESTRICT,
        instance_id UUID NOT NULL REFERENCES deployment_instances(id) ON DELETE RESTRICT,
        source_backup_id UUID REFERENCES backup_records(id) ON DELETE RESTRICT,
        source_revision VARCHAR(32) NOT NULL CHECK(source_revision~'^[0-9]{8}_[0-9]{4}$'),
        manifest_hash VARCHAR(64) NOT NULL CHECK(manifest_hash~'^[0-9a-f]{64}$'),
        dump_hash VARCHAR(64) NOT NULL CHECK(dump_hash~'^[0-9a-f]{64}$'),
        size_bytes BIGINT NOT NULL CHECK(size_bytes>0),
        encrypted_key_ref VARCHAR(200) NOT NULL CHECK(length(encrypted_key_ref)>0),
        private_location_ref UUID NOT NULL,
        restore_verified BOOLEAN NOT NULL CHECK(restore_verified),
        duration_ms BIGINT NOT NULL CHECK(duration_ms BETWEEN 0 AND 86400000),
        requested_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
    """),
}
APPEND_ONLY = {"import_rows", "export_jobs", "backup_records"}
IMMUTABLE = {
    "import_jobs": "job_id,actor_id,department_id,entity_type,file_format,file_hash,file_size,"
    "scan_version,headers,row_count,expires_at,key_id,nonce,ciphertext",
    "retention_policies": "category,created_by",
}
AUDIT_EVENTS = (
    "f12_job_created", "f12_job_updated", "import_created", "import_previewed",
    "import_committed", "import_expired", "executive_report_created",
    "executive_report_downloaded", "executive_report_failed", "operation_requested",
    "operation_completed", "retention_policy_changed", "operations_agent_changed",
)


def extend_check(table, old_name, new_name, condition):
    condition = condition.replace("'", "''")
    op.execute(f"""
        DO $$ DECLARE previous_expression text; BEGIN
            SELECT pg_get_expr(conbin,conrelid) INTO STRICT previous_expression
                FROM pg_constraint WHERE conrelid='public.{table}'::regclass
                AND conname='{old_name}' AND contype='c';
            ALTER TABLE {table} DROP CONSTRAINT {old_name};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {new_name}
                CHECK((%s) OR ({condition}))',previous_expression);
        END $$;
    """)


def upgrade():
    events = ",".join("'" + event + "'" for event in AUDIT_EVENTS)
    extend_check("audit_events", "audit_events_event_type_check", "audit_events_event_type_check",
                 "event_type IN (" + events + ")")
    extend_check("feature_flags", "ck_f11_installed_module", "ck_f12_installed_module",
                 "code IN ('imports','executive_reports','advanced_operations')")
    extend_check("secret_key_versions", "ck_f11_secret_purpose", "ck_f12_secret_purpose",
                 "purpose IN ('import_staging','report_result','operations_agent')")
    extend_check("job_runs", "job_runs_kind_check", "ck_f12_job_kind",
                 "kind IN ('import','export','backup','restore_verify')")
    op.execute("""
        ALTER TABLE job_runs ALTER COLUMN service_principal_id DROP NOT NULL,
            ALTER COLUMN configuration_revision_id DROP NOT NULL,
            ADD COLUMN operation_payload JSONB,
            ADD CONSTRAINT ck_f12_operation_payload CHECK(
                (kind IN ('backup','restore_verify') AND operation_payload IS NOT NULL
                    AND jsonb_typeof(operation_payload)='object'
                    AND operation_payload ?& ARRAY['destination_ref','source_backup_id']
                    AND operation_payload-ARRAY['destination_ref','source_backup_id']='{}'::jsonb)
                OR (kind NOT IN ('backup','restore_verify') AND operation_payload IS NULL)),
            ADD CONSTRAINT ck_f12_job_actor CHECK(
                (kind='recurrence' AND service_principal_id IS NOT NULL
                    AND configuration_revision_id IS NOT NULL) OR
                (kind IN ('import','export') AND
                    num_nonnulls(service_principal_id,configuration_revision_id) IN (0,2)) OR
                (kind IN ('backup','restore_verify') AND service_principal_id IS NOT NULL
                    AND configuration_revision_id IS NOT NULL));
    """)
    for table, (identity, columns) in TABLES.items():
        op.execute(f"CREATE TABLE {table} ({identity},{columns})")
    extend_check("integration_configs", "ck_f11_integration_kind", "ck_f12_integration_kind",
                 "kind='operations_agent'")
    extend_check("integration_configs", "ck_f11_integration_scope", "ck_f12_integration_scope",
                 "kind='operations_agent' AND provider='local_agent' AND name IS NOT NULL "
                 "AND scope_kind='organization' AND department_id IS NULL "
                 "AND configuration_revision_id IS NOT NULL")
    extend_check("integration_configs", "ck_f11_integration_config", "ck_f12_integration_config",
                 "kind='operations_agent' AND jsonb_typeof(config)='object' AND "
                 "config ?& ARRAY['provider','service_principal_id','capabilities',"
                 "'destination_ref','protocol_version'] AND "
                 "config-ARRAY['provider','service_principal_id','capabilities',"
                 "'destination_ref','protocol_version']='{}'::jsonb AND "
                 "config->>'provider'='local_agent' AND config->>'protocol_version'='1' AND "
                 "jsonb_typeof(config->'capabilities')='array' AND "
                 "jsonb_array_length(config->'capabilities') BETWEEN 1 AND 2 AND "
                 "config->'capabilities' <@ '[\"backup\",\"restore_verify\"]'::jsonb AND "
                 "secret_id IS NOT NULL")
    op.execute("""
        ALTER TABLE integration_configs ADD CONSTRAINT ck_f12_agent_contract CHECK(
            kind<>'operations_agent' OR
            (provider IS NOT NULL AND provider='local_agent' AND name IS NOT NULL
                AND scope_kind IS NOT NULL AND scope_kind='organization'
                AND department_id IS NULL AND secret_id IS NOT NULL
                AND configuration_revision_id IS NOT NULL AND jsonb_typeof(config)='object'
                AND config ?& ARRAY['provider','service_principal_id','capabilities',
                    'destination_ref','protocol_version']
                AND config-ARRAY['provider','service_principal_id','capabilities',
                    'destination_ref','protocol_version']='{}'::jsonb
                AND config->>'provider'='local_agent' AND config->>'protocol_version'='1'
                AND jsonb_typeof(config->'capabilities')='array'
                AND jsonb_array_length(config->'capabilities') BETWEEN 1 AND 2
                AND config->'capabilities' <@ '["backup","restore_verify"]'::jsonb));
        CREATE UNIQUE INDEX uq_f12_local_operations_agent ON integration_configs(kind)
            WHERE kind='operations_agent';
        CREATE INDEX ix_f12_import_actor ON import_jobs(actor_id,created_at,id);
        CREATE INDEX ix_f12_import_expiry ON import_jobs(state,expires_at,id);
        CREATE INDEX ix_f12_rows_preview ON import_rows(import_id,preview_version,row_number);
        CREATE INDEX ix_f12_report_requester ON export_jobs(requester_id,created_at,id);
        CREATE INDEX ix_f12_report_expiry ON export_jobs(expires_at,id);
        CREATE INDEX ix_f12_backup_instance ON backup_records(instance_id,created_at,id);
        CREATE FUNCTION guard_f12_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_TABLE_NAME='import_jobs' THEN
                IF NOT EXISTS(SELECT 1 FROM job_runs j WHERE j.id=NEW.job_id AND j.kind='import'
                    AND j.owner_user_id=NEW.actor_id AND j.input_hash=NEW.file_hash)
                    OR NOT EXISTS(SELECT 1 FROM secret_key_versions k WHERE k.id=NEW.key_id
                        AND k.purpose='import_staging') THEN
                    RAISE EXCEPTION 'F12_IMPORT_IDENTITY' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND (OLD.state IN ('committed','expired')
                    OR NEW.preview_attempts<OLD.preview_attempts
                    OR NEW.preview_attempts>OLD.preview_attempts+1
                    OR NEW.state='uploaded'
                    OR (NEW.state='committed' AND OLD.state<>'previewed')
                    OR (NEW.state IN ('previewed','rejected') AND
                        NEW.preview_attempts<>OLD.preview_attempts+1)) THEN
                    RAISE EXCEPTION 'F12_IMPORT_TRANSITION' USING ERRCODE='23514';
                END IF;
                IF TG_OP='INSERT' AND (NEW.state<>'uploaded' OR NEW.preview_attempts<>0
                    OR NEW.config_hash IS NOT NULL OR NEW.preview_hash IS NOT NULL) THEN
                    RAISE EXCEPTION 'F12_IMPORT_INITIAL_STATE' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='retention_policies' THEN
                IF NOT EXISTS(SELECT 1 FROM users u WHERE u.id=NEW.responsible_user_id
                    AND u.is_active) THEN
                    RAISE EXCEPTION 'F12_RETENTION_RESPONSIBLE' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION guard_f12_append() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ DECLARE
            document jsonb := to_jsonb(NEW); owner_id uuid;
        BEGIN
            IF TG_TABLE_NAME='import_rows' THEN
                IF NOT EXISTS(SELECT 1 FROM import_jobs j WHERE j.id=NEW.import_id
                    AND j.state IN ('previewed','rejected') AND j.version=NEW.preview_version
                    AND j.row_count>=NEW.row_number AND j.key_id=NEW.key_id) THEN
                    RAISE EXCEPTION 'F12_PREVIEW_ROW' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='export_jobs' THEN
                IF NEW.version<>1 OR NOT EXISTS(SELECT 1 FROM job_runs j
                    WHERE j.id=NEW.job_id AND j.kind='export' AND j.owner_user_id=NEW.requester_id)
                    OR NOT EXISTS(SELECT 1 FROM evaluations e WHERE e.id=NEW.final_evaluation_id
                        AND e.status='final' AND e.department_id=NEW.department_id
                        AND e.snapshot_at=NEW.snapshot_at
                        AND e.calculation_version::text=NEW.calculation_version
                        AND e.organization_timezone=NEW.organization_timezone)
                    OR NOT EXISTS(SELECT 1 FROM secret_key_versions k WHERE k.id=NEW.key_id
                        AND k.purpose='report_result') THEN
                    RAISE EXCEPTION 'F12_REPORT_SNAPSHOT' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='backup_records' THEN
                IF NEW.version<>1 OR NOT EXISTS(SELECT 1 FROM job_runs j WHERE j.id=NEW.job_id
                    AND j.kind IN ('backup','restore_verify')
                    AND j.owner_user_id=NEW.requested_by) THEN
                    RAISE EXCEPTION 'F12_BACKUP_JOB' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION audit_f12_append() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM audit_events a WHERE a.entity_type=TG_TABLE_NAME
                AND a.entity_id=NEW.id AND a.request_id IS NOT NULL
                AND a.outcome='success') THEN
                RAISE EXCEPTION 'F12_APPEND_AUDIT_REQUIRED' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION guard_f12_job() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_OP='UPDATE' AND NEW.operation_payload IS DISTINCT FROM OLD.operation_payload THEN
                RAISE EXCEPTION 'F12_JOB_INPUT_IMMUTABLE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER guard_f12_job BEFORE INSERT OR UPDATE ON job_runs
            FOR EACH ROW EXECUTE FUNCTION guard_f12_job();
        CREATE FUNCTION guard_f12_agent() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM service_principals p
                WHERE p.id=(NEW.config->>'service_principal_id')::uuid AND p.is_active)
                OR NOT EXISTS(SELECT 1 FROM encrypted_secrets s WHERE s.id=NEW.secret_id
                    AND s.owner_id=NEW.id AND s.purpose='operations_agent') THEN
                RAISE EXCEPTION 'F12_AGENT_IDENTITY' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER guard_f12_agent BEFORE INSERT OR UPDATE ON integration_configs
            FOR EACH ROW WHEN (NEW.kind='operations_agent') EXECUTE FUNCTION guard_f12_agent();
        CREATE CONSTRAINT TRIGGER audit_f12_agent AFTER INSERT OR UPDATE ON integration_configs
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.kind='operations_agent')
            EXECUTE FUNCTION audit_f8_record();
        REVOKE ALL ON FUNCTION guard_f12_record(),guard_f12_append(),audit_f12_append(),
            guard_f12_job(),guard_f12_agent() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION guard_f12_record(),guard_f12_append(),audit_f12_append(),
            guard_f12_job(),guard_f12_agent() TO ocote_runtime;
    """)
    for table in TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,ocote_runtime")
        if table in APPEND_ONLY:
            op.execute(f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION protect_f9_record('append')")
            op.execute(f"CREATE TRIGGER guard_{table} BEFORE INSERT ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION guard_f12_append()")
            audit_function, privileges = "audit_f12_append", "SELECT,INSERT"
        else:
            op.execute(f"CREATE TRIGGER protect_{table} BEFORE INSERT OR UPDATE OR DELETE "
                       f"ON {table} FOR EACH ROW EXECUTE FUNCTION "
                       f"protect_f9_record('{IMMUTABLE[table]}')")
            op.execute(f"CREATE TRIGGER guard_{table} BEFORE INSERT OR UPDATE ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION guard_f12_record()")
            audit_function, privileges = "audit_f9_record", "SELECT,INSERT,UPDATE"
        operation = "INSERT" if table in APPEND_ONLY else "INSERT OR UPDATE"
        op.execute(f"CREATE CONSTRAINT TRIGGER audit_{table} AFTER {operation} ON {table} "
                   "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                   f"EXECUTE FUNCTION {audit_function}()")
        op.execute(f"CREATE TRIGGER truncate_{table} BEFORE TRUNCATE ON {table} "
                   "EXECUTE FUNCTION protect_f9_record('append')")
        op.execute(f"GRANT {privileges} ON {table} TO ocote_runtime")


def downgrade():
    raise RuntimeError("F12 requires authorized isolated recovery, never destructive downgrade")