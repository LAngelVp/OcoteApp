"""F10 private notifications, transports and signed read-only calendar feeds."""

from alembic import op

revision = "20261126_0009"
down_revision = "20261125_0008"
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
CHANNELS = (
    "cardinality(channels) BETWEEN 1 AND 3 "
    "AND channels <@ ARRAY['in_app','email','messaging'] "
    "AND array_position(channels,NULL) IS NULL"
)
TABLES = {
    "notification_connectors": (
        MUTABLE,
        """
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        scope_kind VARCHAR(20) NOT NULL CHECK(scope_kind IN ('organization','department')),
        department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
        provider VARCHAR(20) NOT NULL CHECK(provider IN ('smtp','slack','teams','telegram')),
        config JSONB NOT NULL CHECK(jsonb_typeof(config)='object' AND NOT
            config ?| ARRAY['credential','password','token','webhook_url','bot_token']),
        secret_id UUID REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
        config_revision INTEGER NOT NULL CHECK(config_revision>0), is_active BOOLEAN NOT NULL,
        tested_version INTEGER, tested_at TIMESTAMPTZ,
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        CHECK((scope_kind='department')=(department_id IS NOT NULL)),
        CHECK((tested_version IS NULL)=(tested_at IS NULL)),
        UNIQUE NULLS NOT DISTINCT(provider,name,scope_kind,department_id)
    """,
    ),
    "notification_connector_checks": (
        IDENTITY,
        """
        connector_id UUID NOT NULL REFERENCES notification_connectors(id) ON DELETE RESTRICT,
        config_version INTEGER NOT NULL CHECK(config_version>0),
        status VARCHAR(12) NOT NULL CHECK(status IN ('passed','failed')),
        result_code VARCHAR(80) NOT NULL CHECK(result_code IN
            ('VERIFIED','PROVIDER_UNAVAILABLE_OR_UNSAFE')),
        latency_ms INTEGER NOT NULL CHECK(latency_ms BETWEEN 0 AND 120000),
        actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, request_id UUID NOT NULL
    """,
    ),
    "notification_rules": (
        MUTABLE,
        f"""
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
        trigger VARCHAR(32) NOT NULL CHECK(trigger IN
            ('assignment','mention','upcoming_due','overdue',
            'due_date_request','due_date_decision','impediment','evaluation_finalized')),
        recipient_mode VARCHAR(32) NOT NULL CHECK(recipient_mode IN
            ('assignee','mentioned','requester','department_leaders','admins','evaluator')),
        channels TEXT[] NOT NULL CHECK({CHANNELS}),
        connector_ids UUID[] NOT NULL CHECK(cardinality(connector_ids)<=20
            AND array_position(connector_ids,NULL) IS NULL),
        threshold_days INTEGER CHECK(threshold_days BETWEEN 0 AND 365),
        day_basis VARCHAR(12) NOT NULL CHECK(day_basis IN ('natural','business')),
        max_age_hours INTEGER NOT NULL CHECK(max_age_hours BETWEEN 1 AND 720),
        max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 10),
        retry_base_seconds INTEGER NOT NULL CHECK(retry_base_seconds BETWEEN 5 AND 300),
        enabled BOOLEAN NOT NULL, created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        CHECK((trigger IN ('upcoming_due','overdue'))=(threshold_days IS NOT NULL))
    """,
    ),
    "notification_preferences": (
        MUTABLE,
        f"""
        user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
        channels TEXT[] NOT NULL CHECK({CHANNELS}), opt_in BOOLEAN NOT NULL,
        quiet_start VARCHAR(5), quiet_end VARCHAR(5), timezone VARCHAR(64) NOT NULL,
        CHECK((quiet_start IS NULL AND quiet_end IS NULL) OR
            (quiet_start IS NOT NULL AND quiet_end IS NOT NULL AND quiet_start<>quiet_end
             AND quiet_start~'^([01][0-9]|2[0-3]):[0-5][0-9]$'
             AND quiet_end~'^([01][0-9]|2[0-3]):[0-5][0-9]$'))
    """,
    ),
    "notifications": (
        MUTABLE,
        """
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        outbox_id UUID NOT NULL REFERENCES transactional_outbox(id) ON DELETE RESTRICT,
        rule_id UUID NOT NULL REFERENCES notification_rules(id) ON DELETE RESTRICT,
        rule_version INTEGER NOT NULL CHECK(rule_version>0),
        safe_projection JSONB NOT NULL CHECK(jsonb_typeof(safe_projection)='object'
            AND safe_projection-ARRAY['trigger','resource_id','resource_type']='{}'::jsonb),
        in_app BOOLEAN NOT NULL, available_at TIMESTAMPTZ NOT NULL,
        read_at TIMESTAMPTZ, expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at),
        CHECK(read_at IS NULL OR read_at>=created_at),
        UNIQUE(user_id,outbox_id,rule_id,rule_version)
    """,
    ),
    "notification_deliveries": (
        MUTABLE,
        """
        notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE RESTRICT,
        connector_id UUID NOT NULL REFERENCES notification_connectors(id) ON DELETE RESTRICT,
        config_revision INTEGER NOT NULL CHECK(config_revision>0),
        channel VARCHAR(20) NOT NULL CHECK(channel IN ('email','messaging')),
        attempt_no INTEGER NOT NULL CHECK(attempt_no BETWEEN 1 AND 10),
        state VARCHAR(20) NOT NULL CHECK(state IN
            ('pending','sending','accepted','failed','cancelled','ambiguous')),
        result_code VARCHAR(80), next_attempt_at TIMESTAMPTZ NOT NULL,
        lease_token UUID, lease_until TIMESTAMPTZ,
        CHECK((state='sending')=(lease_token IS NOT NULL AND lease_until IS NOT NULL)),
        CHECK((lease_token IS NULL)=(lease_until IS NULL)),
        UNIQUE(notification_id,connector_id,attempt_no)
    """,
    ),
    "notification_dispatches": (
        IDENTITY,
        """
        outbox_id UUID NOT NULL REFERENCES transactional_outbox(id) ON DELETE RESTRICT,
        rule_id UUID NOT NULL REFERENCES notification_rules(id) ON DELETE RESTRICT,
        rule_version INTEGER NOT NULL CHECK(rule_version>0),
        recipient_count INTEGER NOT NULL CHECK(recipient_count BETWEEN 0 AND 1000),
        UNIQUE(outbox_id,rule_id,rule_version)
    """,
    ),
    "calendar_feeds": (
        MUTABLE,
        """
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        token_hash VARCHAR(64) NOT NULL UNIQUE CHECK(token_hash~'^[0-9a-f]{64}$'),
        signing_secret_id UUID NOT NULL REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at
            AND expires_at<=created_at+interval '90 days'),
        revoked_at TIMESTAMPTZ CHECK(revoked_at IS NULL OR revoked_at>=created_at)
    """,
    ),
}
APPEND_ONLY = {"notification_connector_checks", "notification_dispatches"}
IMMUTABLE = {
    "notification_connectors": "provider,created_by",
    "notification_rules": "created_by",
    "notification_preferences": "user_id",
    "notifications": (
        "user_id,outbox_id,rule_id,rule_version,safe_projection,in_app,available_at,expires_at"
    ),
    "notification_deliveries": "notification_id,connector_id,config_revision,channel,attempt_no",
    "calendar_feeds": "owner_user_id,name,token_hash,signing_secret_id,expires_at",
}


def upgrade():
    for table, (identity, columns) in TABLES.items():
        op.execute(f"CREATE TABLE {table} ({identity},{columns})")
    op.execute("""
        ALTER TABLE service_principals DROP CONSTRAINT service_principals_approved_scopes_check;
        ALTER TABLE service_principals ADD CONSTRAINT ck_f10_principal_scopes
            CHECK(cardinality(approved_scopes) BETWEEN 1 AND 3
                AND approved_scopes <@
                    ARRAY['tasks:create','subtasks:create','notifications:dispatch']
                AND array_position(approved_scopes,NULL) IS NULL);
        ALTER TABLE feature_flags DROP CONSTRAINT ck_f9_installed_module;
        ALTER TABLE feature_flags ADD CONSTRAINT ck_f10_installed_module CHECK(code IN
            ('subtasks','due_date_requests','kanban','timeline','analytics','evaluations','exports',
             'integrations','calendar','comments','dependencies','impediments','tags','custom_fields',
             'templates','recurrence','search','saved_views','notifications','email_notifications',
             'corporate_messaging','calendar_feeds'));
        ALTER TABLE secret_key_versions DROP CONSTRAINT ck_f8_secret_purpose;
        ALTER TABLE secret_key_versions ADD CONSTRAINT ck_f10_secret_purpose CHECK(purpose IN
            ('jwt_signing','csrf','health_monitor','local_storage','clamav','backup','object_storage',
             'notifications','calendar_feed'));
        ALTER TABLE transactional_outbox ADD COLUMN evaluation_id UUID
            REFERENCES evaluations(id) ON DELETE RESTRICT;
        ALTER TABLE transactional_outbox DROP CONSTRAINT transactional_outbox_event_type_check,
            DROP CONSTRAINT transactional_outbox_payload_check;
        DO $$ DECLARE identity text; BEGIN
            FOR identity IN SELECT conname FROM pg_constraint
                WHERE conrelid='public.transactional_outbox'::regclass AND contype='c'
                AND pg_get_constraintdef(oid) LIKE '%num_nonnulls(task_id%'
            LOOP EXECUTE format('ALTER TABLE transactional_outbox DROP CONSTRAINT %I',identity);
            END LOOP;
        END $$;
        ALTER TABLE transactional_outbox ADD CONSTRAINT ck_f10_outbox_entity
            CHECK(num_nonnulls(task_id,objective_id,evaluation_id)=1),
            ADD CONSTRAINT ck_f10_outbox_type CHECK(event_type IN
            ('dependency_changed','impediment_changed','comment_changed','recurrence_generated',
             'assignment','upcoming_due','overdue','due_date_request','due_date_decision','evaluation_finalized')),
            ADD CONSTRAINT ck_f10_outbox_payload CHECK(jsonb_typeof(payload)='object' AND
                payload-ARRAY['resource_id','version','owner_user_id','rule_id','scheduled_for','requester_id']='{}'::jsonb);
        CREATE FUNCTION guard_f10_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_TABLE_NAME='notification_connectors' THEN
                IF NEW.config->>'provider' IS DISTINCT FROM NEW.provider THEN
                    RAISE EXCEPTION 'F10_PROVIDER_MISMATCH' USING ERRCODE='23514';
                END IF;
                IF NEW.secret_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM encrypted_secrets
                    WHERE id=NEW.secret_id AND owner_id=NEW.id AND purpose='notifications') THEN
                    RAISE EXCEPTION 'F10_SECRET_OWNER' USING ERRCODE='23514';
                END IF;
                IF NEW.is_active AND (NEW.tested_version IS DISTINCT FROM NEW.config_revision
                    OR NEW.tested_at<clock_timestamp()-interval '10 minutes'
                    OR NOT EXISTS(SELECT 1 FROM notification_connector_checks
                        WHERE connector_id=NEW.id AND config_version=NEW.config_revision
                        AND status='passed'
                        AND created_at>=clock_timestamp()-interval '10 minutes')) THEN
                    RAISE EXCEPTION 'F10_TEST_REQUIRED' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND (NEW.config,NEW.secret_id,NEW.scope_kind,NEW.department_id)
                    IS DISTINCT FROM (OLD.config,OLD.secret_id,OLD.scope_kind,OLD.department_id)
                    AND (NEW.config_revision<>OLD.config_revision+1 OR NEW.is_active
                         OR NEW.tested_version IS NOT NULL) THEN
                    RAISE EXCEPTION 'F10_RETEST_REQUIRED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='calendar_feeds' THEN
                IF NOT EXISTS(SELECT 1 FROM encrypted_secrets WHERE id=NEW.signing_secret_id
                    AND owner_id=NEW.id AND purpose='calendar_feed') THEN
                    RAISE EXCEPTION 'F10_FEED_SIGNING_OWNER' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND OLD.revoked_at IS NOT NULL THEN
                    RAISE EXCEPTION 'F10_FEED_REVOKED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='notification_preferences' THEN
                IF NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=NEW.timezone) THEN
                    RAISE EXCEPTION 'F10_TIMEZONE_REQUIRED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='notifications' AND TG_OP='UPDATE' THEN
                IF OLD.read_at IS NOT NULL OR NEW.read_at IS NULL THEN
                    RAISE EXCEPTION 'F10_READ_ONCE' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='notification_deliveries' AND TG_OP='UPDATE' THEN
                IF OLD.state NOT IN ('pending','sending') OR
                    (OLD.state='sending' AND NEW.state IN ('pending','sending')) THEN
                    RAISE EXCEPTION 'F10_TERMINAL_DELIVERY' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION f10_history_event() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NEW.event_type IN ('task_created','assignment_changed') THEN
                INSERT INTO transactional_outbox(event_id,event_type,schema_version,task_id,
                    actor_id,actor_service_id,department_id,payload)
                    SELECT NEW.id,'assignment',1,t.id,NEW.actor_id,NEW.actor_service_id,
                        o.department_id,jsonb_build_object('resource_id',t.id,
                            'version',t.version,'owner_user_id',t.assignee_id)
                    FROM tasks t JOIN objectives o ON o.id=t.objective_id WHERE t.id=NEW.task_id;
            END IF;
            RETURN NULL;
        END $$;
        CREATE TRIGGER f10_history_event AFTER INSERT ON task_history
            FOR EACH ROW EXECUTE FUNCTION f10_history_event();
        CREATE FUNCTION f10_date_request_event() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_OP='INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
                INSERT INTO transactional_outbox(event_id,event_type,schema_version,task_id,
                    actor_id,department_id,payload)
                    SELECT gen_random_uuid(),CASE WHEN TG_OP='INSERT' THEN 'due_date_request'
                        ELSE 'due_date_decision' END,1,t.id,
                        CASE WHEN TG_OP='INSERT' THEN NEW.requested_by ELSE NEW.decided_by END,
                        o.department_id,jsonb_build_object('resource_id',t.id,'version',NEW.version,
                            'requester_id',NEW.requested_by)
                    FROM tasks t JOIN objectives o ON o.id=t.objective_id WHERE t.id=NEW.task_id;
            END IF;
            RETURN NULL;
        END $$;
        CREATE TRIGGER f10_date_request_event AFTER INSERT OR UPDATE ON due_date_requests
            FOR EACH ROW EXECUTE FUNCTION f10_date_request_event();
        CREATE FUNCTION f10_evaluation_event() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF to_jsonb(NEW)->>'status'='final' AND
                (TG_OP='INSERT' OR to_jsonb(OLD)->>'status'<>'final') THEN
                INSERT INTO transactional_outbox(event_id,event_type,schema_version,evaluation_id,
                    actor_id,department_id,payload)
                    VALUES(gen_random_uuid(),'evaluation_finalized',1,
                    NEW.id,NEW.evaluator_id,NEW.department_id,
                    jsonb_build_object('resource_id',NEW.id,'version',NEW.version,
                        'owner_user_id',NEW.evaluator_id));
            END IF;
            RETURN NULL;
        END $$;
        CREATE TRIGGER f10_evaluation_event AFTER INSERT OR UPDATE ON evaluations
            FOR EACH ROW EXECUTE FUNCTION f10_evaluation_event();
        REVOKE ALL ON FUNCTION guard_f10_record(),f10_history_event(),
            f10_date_request_event(),f10_evaluation_event() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION guard_f10_record(),f10_history_event(),
            f10_date_request_event(),f10_evaluation_event() TO ocote_runtime;
        CREATE INDEX ix_f10_notification_owner ON notifications(user_id,read_at,created_at,id);
        CREATE INDEX ix_f10_delivery_due ON notification_deliveries(state,next_attempt_at,id);
        CREATE INDEX ix_f10_rule_scope ON notification_rules(enabled,department_id,trigger,id);
        CREATE INDEX ix_f10_feed_owner ON calendar_feeds(owner_user_id,expires_at,id);
        CREATE INDEX ix_f10_outbox_evaluation ON transactional_outbox(evaluation_id,created_at,id);
    """)
    for table in TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,ocote_runtime")
        if table in APPEND_ONLY:
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION protect_f9_record('append')"
            )
            privileges = "SELECT,INSERT"
        else:
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION protect_f9_record('{IMMUTABLE[table]}')"
            )
            op.execute(
                f"CREATE TRIGGER guard_{table} BEFORE INSERT OR UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION guard_f10_record()"
            )
            op.execute(
                f"CREATE CONSTRAINT TRIGGER z_f10_audit_{table} AFTER INSERT OR UPDATE ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_f9_record()"
            )
            privileges = "SELECT,INSERT,UPDATE"
        op.execute(
            f"CREATE TRIGGER truncate_{table} BEFORE TRUNCATE ON {table} "
            "EXECUTE FUNCTION protect_f9_record('append')"
        )
        op.execute(f"GRANT {privileges} ON {table} TO ocote_runtime")
    op.execute("""
        DO $$ DECLARE column_record record; BEGIN
            FOR column_record IN SELECT k.table_name,k.column_name
                FROM information_schema.key_column_usage k
                JOIN information_schema.table_constraints c
                    ON c.constraint_schema=k.constraint_schema
                    AND c.constraint_name=k.constraint_name AND c.table_name=k.table_name
                WHERE c.constraint_type='FOREIGN KEY' AND k.table_schema='public'
                    AND k.table_name IN ('notification_connectors','notification_connector_checks',
                    'notification_rules','notification_preferences','notifications',
                    'notification_deliveries','notification_dispatches','calendar_feeds')
            LOOP EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(%I,created_at,id)',
                'ix_f10_fk_'||column_record.table_name||'_'||column_record.column_name,
                column_record.table_name,column_record.column_name);
            END LOOP;
        END $$;
    """)


def downgrade():
    raise RuntimeError("F10 history requires approved fix-forward or isolated restore")
