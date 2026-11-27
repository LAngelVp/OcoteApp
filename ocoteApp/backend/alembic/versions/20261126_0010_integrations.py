"""F11 federated identity and scoped integration persistence, without business seeds."""

from alembic import op

revision = "20261126_0010"
down_revision = "20261126_0009"
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
TABLES = {
    "external_identities": (
        MUTABLE,
        """
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        issuer VARCHAR(512) NOT NULL CHECK(length(btrim(issuer)) BETWEEN 1 AND 512),
        subject VARCHAR(512) NOT NULL CHECK(length(btrim(subject)) BETWEEN 1 AND 512),
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        last_authenticated_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
        CHECK(last_authenticated_at IS NULL OR last_authenticated_at>=created_at),
        CHECK(revoked_at IS NULL OR revoked_at>=created_at), UNIQUE(issuer,subject)
        """,
    ),
    "sso_transactions": (
        MUTABLE,
        """
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        config_revision INTEGER NOT NULL CHECK(config_revision>0),
        purpose VARCHAR(12) NOT NULL CHECK(purpose IN ('login','bind','probe')),
        initiating_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
        state_hash VARCHAR(64) NOT NULL UNIQUE CHECK(state_hash~'^[0-9a-f]{64}$'),
        browser_hash VARCHAR(64) NOT NULL CHECK(browser_hash~'^[0-9a-f]{64}$'),
        context_secret_id UUID NOT NULL REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
        state VARCHAR(12) NOT NULL CHECK(state IN ('pending','verified','consumed','failed')),
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at
            AND expires_at<=created_at+interval '10 minutes'),
        issuer VARCHAR(512), subject VARCHAR(512), authenticated_at TIMESTAMPTZ,
        consumed_at TIMESTAMPTZ,
        CHECK((purpose='login')=(initiating_user_id IS NULL)),
        CHECK((issuer IS NULL)=(subject IS NULL)),
        CHECK((issuer IS NULL)=(authenticated_at IS NULL)),
        CHECK(issuer IS NULL OR (length(btrim(issuer)) BETWEEN 1 AND 512
            AND length(btrim(subject)) BETWEEN 1 AND 512)),
        CHECK(state NOT IN ('verified','consumed') OR issuer IS NOT NULL),
        CHECK((state='consumed')=(consumed_at IS NOT NULL)),
        CHECK(authenticated_at IS NULL OR authenticated_at BETWEEN created_at AND expires_at),
        CHECK(consumed_at IS NULL OR consumed_at BETWEEN authenticated_at AND expires_at)
        """,
    ),
    "sso_assertion_uses": (
        IDENTITY,
        """
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        transaction_id UUID NOT NULL UNIQUE REFERENCES sso_transactions(id) ON DELETE RESTRICT,
        assertion_id VARCHAR(256) NOT NULL CHECK(length(btrim(assertion_id)) BETWEEN 1 AND 256),
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>created_at),
        UNIQUE(integration_id,assertion_id)
        """,
    ),
    "api_keys": (
        MUTABLE,
        """
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        service_principal_id UUID NOT NULL REFERENCES service_principals(id) ON DELETE RESTRICT,
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        principal_token_version INTEGER NOT NULL CHECK(principal_token_version>0),
        owner_token_version INTEGER NOT NULL CHECK(owner_token_version>0),
        rate_per_minute INTEGER NOT NULL CHECK(rate_per_minute BETWEEN 1 AND 1000),
        scopes TEXT[] NOT NULL CHECK(cardinality(scopes) BETWEEN 1 AND 3
            AND scopes <@ ARRAY['tasks:read','tasks:create','tasks:update_metadata']
            AND array_position(scopes,NULL) IS NULL),
        department_ids UUID[] NOT NULL CHECK(cardinality(department_ids) BETWEEN 1 AND 100
            AND array_position(department_ids,NULL) IS NULL),
        allowed_networks TEXT[] CHECK(allowed_networks IS NULL OR
            (cardinality(allowed_networks) BETWEEN 1 AND 100
                AND array_position(allowed_networks,NULL) IS NULL)),
        token_hash VARCHAR(64) NOT NULL UNIQUE CHECK(token_hash~'^[0-9a-f]{64}$'),
        pepper_secret_id UUID NOT NULL REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
        expires_at TIMESTAMPTZ NOT NULL CHECK(expires_at>=created_at+interval '1 day'
            AND expires_at<=created_at+interval '90 days'),
        revoked_at TIMESTAMPTZ CHECK(revoked_at IS NULL OR revoked_at>=created_at),
        rotated_from_id UUID UNIQUE REFERENCES api_keys(id) ON DELETE RESTRICT
        """,
    ),
    "task_external_links": (
        MUTABLE,
        """
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        repository_id VARCHAR(128) NOT NULL CHECK(repository_id~'^[1-9][0-9]*$'),
        external_id VARCHAR(128) NOT NULL,
        kind VARCHAR(20) NOT NULL
            CHECK(kind IN ('issue','pull_request','merge_request','commit','branch')),
        canonical_url VARCHAR(2048) NOT NULL CHECK(canonical_url~'^https://'),
        safe_projection JSONB NOT NULL CHECK(jsonb_typeof(safe_projection)='object'
            AND safe_projection-ARRAY['state','title','updated_at']='{}'::jsonb),
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        deactivated_at TIMESTAMPTZ CHECK(deactivated_at IS NULL OR deactivated_at>=created_at),
        CHECK((kind='commit' AND external_id~'^([0-9a-f]{40}|[0-9a-f]{64})$')
            OR (kind='branch' AND external_id~'^[a-zA-Z0-9_][a-zA-Z0-9_./-]{0,127}$'
                AND external_id!~'[.][.]' AND external_id!~'(^|/)[.]'
                AND external_id!~'/$' AND external_id!~'//'
                AND external_id!~'([.]|[.]lock)(/|$)')
            OR (kind NOT IN ('commit','branch') AND external_id~'^[1-9][0-9]*$')),
        UNIQUE(task_id,integration_id,repository_id,kind,external_id)
        """,
    ),
    "webhook_inbox": (
        IDENTITY,
        """
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        delivery_id VARCHAR(200) NOT NULL CHECK(length(btrim(delivery_id)) BETWEEN 1 AND 200),
        body_hash VARCHAR(64) NOT NULL CHECK(body_hash~'^[0-9a-f]{64}$'),
        event_type VARCHAR(80) NOT NULL CHECK(length(btrim(event_type)) BETWEEN 1 AND 80),
        safe_projection JSONB NOT NULL CHECK(jsonb_typeof(safe_projection)='object'
            AND safe_projection-ARRAY['repository_id','external_id','kind','state','title',
                'updated_at']='{}'::jsonb),
        request_id UUID NOT NULL, UNIQUE(integration_id,delivery_id)
        """,
    ),
    "webhook_subscriptions": (
        MUTABLE,
        """
        integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        event_types TEXT[] NOT NULL CHECK(cardinality(event_types) BETWEEN 1 AND 16
            AND event_types <@ ARRAY['dependency_changed','impediment_changed','comment_changed',
                'recurrence_generated','assignment','upcoming_due','overdue','due_date_request',
                'due_date_decision','evaluation_finalized']
            AND array_position(event_types,NULL) IS NULL),
        department_ids UUID[] NOT NULL CHECK(cardinality(department_ids) BETWEEN 1 AND 100
            AND array_position(department_ids,NULL) IS NULL),
        max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 10),
        retry_base_seconds INTEGER NOT NULL CHECK(retry_base_seconds BETWEEN 5 AND 300),
        max_delay_seconds INTEGER NOT NULL CHECK(max_delay_seconds BETWEEN 300 AND 86400),
        enabled BOOLEAN NOT NULL
        """,
    ),
    "webhook_deliveries": (
        MUTABLE,
        """
        subscription_id UUID NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE RESTRICT,
        subscription_version INTEGER NOT NULL CHECK(subscription_version>0),
        outbox_id UUID NOT NULL REFERENCES transactional_outbox(id) ON DELETE RESTRICT,
        idempotency_key VARCHAR(128) NOT NULL
            CHECK(length(btrim(idempotency_key)) BETWEEN 1 AND 128),
        config_revision INTEGER NOT NULL CHECK(config_revision>0),
        signing_secret_id UUID NOT NULL REFERENCES encrypted_secrets(id) ON DELETE RESTRICT,
        body BYTEA NOT NULL CHECK(octet_length(body) BETWEEN 1 AND 1048576),
        state VARCHAR(20) NOT NULL CHECK(state IN
            ('pending','sending','delivered','dead_letter','cancelled')),
        attempt_count INTEGER NOT NULL CHECK(attempt_count BETWEEN 0 AND 10),
        max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 10),
        retry_base_seconds INTEGER NOT NULL CHECK(retry_base_seconds BETWEEN 5 AND 300),
        max_delay_seconds INTEGER NOT NULL CHECK(max_delay_seconds BETWEEN 300 AND 86400),
        next_attempt_at TIMESTAMPTZ NOT NULL, lease_token UUID, lease_until TIMESTAMPTZ,
        retry_of_id UUID REFERENCES webhook_deliveries(id) ON DELETE RESTRICT,
        requested_by UUID REFERENCES users(id) ON DELETE RESTRICT,
        CHECK(attempt_count<=max_attempts),
        CHECK((state='sending')=(lease_token IS NOT NULL AND lease_until IS NOT NULL)),
        CHECK((lease_token IS NULL)=(lease_until IS NULL)),
        CHECK((retry_of_id IS NULL)=(requested_by IS NULL)),
        CHECK(retry_of_id IS NULL OR retry_of_id<>id),
        UNIQUE(subscription_id,idempotency_key)
        """,
    ),
    "webhook_attempts": (
        IDENTITY,
        """
        delivery_id UUID NOT NULL REFERENCES webhook_deliveries(id) ON DELETE RESTRICT,
        attempt_no INTEGER NOT NULL CHECK(attempt_no BETWEEN 1 AND 10),
        lease_token UUID NOT NULL, signed_at TIMESTAMPTZ NOT NULL CHECK(signed_at<=created_at),
        outcome VARCHAR(20) NOT NULL CHECK(outcome IN
            ('accepted','retryable','rejected','ambiguous')),
        status_code INTEGER CHECK(status_code BETWEEN 100 AND 599),
        result_code VARCHAR(80) NOT NULL CHECK(result_code IN
            ('ACCEPTED','RETRYABLE','REJECTED','TRANSPORT_UNAVAILABLE','LEASE_EXPIRED')),
        latency_ms INTEGER NOT NULL CHECK(latency_ms BETWEEN 0 AND 120000),
        CHECK((outcome='ambiguous')=(status_code IS NULL)),
        CHECK((outcome='accepted' AND status_code BETWEEN 200 AND 299)
            OR (outcome='retryable' AND (status_code IN (408,429) OR status_code>=500))
            OR (outcome='rejected' AND status_code BETWEEN 300 AND 499
                AND status_code NOT IN (408,429))
            OR (outcome='ambiguous' AND status_code IS NULL)),
        UNIQUE(delivery_id,attempt_no), UNIQUE(lease_token)
        """,
    ),
}
APPEND_ONLY = {"sso_assertion_uses", "webhook_inbox", "webhook_attempts"}
IMMUTABLE = {
    "external_identities": "integration_id,user_id,issuer,subject,created_by",
    "sso_transactions": (
        "integration_id,config_revision,purpose,initiating_user_id,state_hash,browser_hash,"
        "context_secret_id,expires_at"
    ),
    "api_keys": (
        "name,service_principal_id,owner_user_id,principal_token_version,owner_token_version,"
        "rate_per_minute,scopes,department_ids,allowed_networks,"
        "token_hash,pepper_secret_id,expires_at,rotated_from_id"
    ),
    "task_external_links": (
        "task_id,integration_id,repository_id,external_id,kind,canonical_url,created_by"
    ),
    "webhook_subscriptions": "integration_id,owner_user_id",
    "webhook_deliveries": (
        "subscription_id,subscription_version,outbox_id,idempotency_key,config_revision,"
        "signing_secret_id,body,max_attempts,retry_base_seconds,max_delay_seconds,"
        "retry_of_id,requested_by"
    ),
}


def upgrade():
    for table, (identity, columns) in TABLES.items():
        op.execute(f"CREATE TABLE {table} ({identity},{columns})")
    op.execute("""
        DO $$ DECLARE previous_expression text; BEGIN
            SELECT pg_get_expr(conbin,conrelid) INTO STRICT previous_expression
                FROM pg_constraint WHERE conrelid='public.audit_events'::regclass
                AND conname='audit_events_event_type_check';
            ALTER TABLE audit_events DROP CONSTRAINT audit_events_event_type_check;
            EXECUTE format('ALTER TABLE audit_events
                ADD CONSTRAINT audit_events_event_type_check
                CHECK((%s) OR event_type IN (''service_authenticated'',
                    ''federation_started'',''federation_verified'',''federation_failed'',
                    ''federation_consumed'',''external_identity_provisioned'',
                    ''external_identity_revoked'',''external_identity_bound'',
                    ''external_identity_authenticated''))', previous_expression);
        END $$;
        ALTER TABLE refresh_sessions ADD COLUMN external_identity_id UUID
            REFERENCES external_identities(id) ON DELETE RESTRICT,
            ADD COLUMN federated_authenticated_at TIMESTAMPTZ,
            ADD COLUMN federated_revocation_deadline TIMESTAMPTZ,
            ADD CONSTRAINT ck_f11_federated_session CHECK(
                num_nonnulls(external_identity_id,federated_authenticated_at,
                    federated_revocation_deadline) IN (0,3)
                AND (external_identity_id IS NULL OR
                    (federated_revocation_deadline>federated_authenticated_at
                     AND federated_revocation_deadline<=
                        federated_authenticated_at+interval '1 hour')));
        ALTER TABLE service_principals DROP CONSTRAINT ck_f10_principal_scopes,
            ADD CONSTRAINT ck_f11_principal_scopes
                CHECK(cardinality(approved_scopes) BETWEEN 1 AND 5
                AND approved_scopes <@ ARRAY['tasks:create','subtasks:create',
                    'notifications:dispatch','tasks:read','tasks:update_metadata']
                AND array_position(approved_scopes,NULL) IS NULL);
        ALTER TABLE feature_flags DROP CONSTRAINT ck_f10_installed_module,
            ADD CONSTRAINT ck_f11_installed_module CHECK(code IN
                ('subtasks','due_date_requests','kanban','timeline','analytics','evaluations','exports',
                 'integrations','calendar','comments','dependencies','impediments','tags','custom_fields',
                 'templates','recurrence','search','saved_views','notifications','email_notifications',
                 'corporate_messaging','calendar_feeds','sso','devops','api_keys','outgoing_webhooks'));
        ALTER TABLE secret_key_versions DROP CONSTRAINT ck_f10_secret_purpose,
            ADD CONSTRAINT ck_f11_secret_purpose CHECK(purpose IN
                ('jwt_signing','csrf','health_monitor','local_storage','clamav','backup','object_storage',
                 'notifications','calendar_feed','integrations','service_keys','sso_context'));
        DO $$ DECLARE previous_expression text; BEGIN
            SELECT pg_get_expr(conbin,conrelid) INTO STRICT previous_expression
                FROM pg_constraint WHERE conrelid='public.integration_configs'::regclass
                AND conname='ck_f8_integration_kind';
            ALTER TABLE integration_configs DROP CONSTRAINT ck_f8_integration_kind;
            EXECUTE format('ALTER TABLE integration_configs ADD CONSTRAINT ck_f11_integration_kind
                CHECK((%s) OR kind IN (''sso'',''devops'',''outgoing_webhook''))',
                previous_expression);
            SELECT pg_get_expr(conbin,conrelid) INTO STRICT previous_expression
                FROM pg_constraint WHERE conrelid='public.integration_configs'::regclass
                AND conname='ck_f8_integration_scope';
            ALTER TABLE integration_configs DROP CONSTRAINT ck_f8_integration_scope;
            EXECUTE format('ALTER TABLE integration_configs ADD CONSTRAINT ck_f11_integration_scope
                CHECK((%s) OR (kind IN (''sso'',''devops'',''outgoing_webhook'')
                    AND provider IS NOT NULL AND name IS NOT NULL
                    AND length(btrim(name)) BETWEEN 1 AND 120 AND scope_kind IS NOT NULL
                    AND scope_kind IN (''organization'',''department'')
                    AND (scope_kind=''department'')=(department_id IS NOT NULL)
                    AND configuration_revision_id IS NOT NULL
                    AND ((kind=''sso'' AND provider IN (''oidc'',''saml'',''ldap''))
                        OR (kind=''devops'' AND provider IN (''github'',''gitlab''))
                        OR (kind=''outgoing_webhook'' AND provider=''outgoing_webhook''))))',
                previous_expression);
            SELECT pg_get_expr(conbin,conrelid) INTO STRICT previous_expression
                FROM pg_constraint WHERE conrelid='public.integration_configs'::regclass
                AND conname='ck_f8_integration_config';
            ALTER TABLE integration_configs DROP CONSTRAINT ck_f8_integration_config;
            EXECUTE format('ALTER TABLE integration_configs ADD CONSTRAINT ck_f11_integration_config
                CHECK((%s) OR (kind IN (''sso'',''devops'',''outgoing_webhook'')
                    AND jsonb_typeof(config)=''object'' AND config ? ''provider''
                    AND config->>''provider'' IS NOT DISTINCT FROM provider AND NOT config ?|
                        ARRAY[''credential'',''password'',''client_secret'',''access_token'',
                            ''webhook_secret'',''private_key'',''bind_password'']))',previous_expression);
        END $$;
        CREATE UNIQUE INDEX uq_f11_provider_name_scope ON integration_configs
            (provider,lower(name),scope_kind,department_id) NULLS NOT DISTINCT
            WHERE kind IN ('sso','devops','outgoing_webhook');
        CREATE FUNCTION guard_f11_integration() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NEW.secret_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM encrypted_secrets
                WHERE id=NEW.secret_id AND owner_id=NEW.id AND purpose='integrations') THEN
                RAISE EXCEPTION 'F11_SECRET_OWNER' USING ERRCODE='23514';
            END IF;
            IF (NEW.provider<>'oidc' OR NEW.config->>'token_auth_method' IS DISTINCT FROM 'none')
                AND NEW.secret_id IS NULL THEN
                RAISE EXCEPTION 'F11_SECRET_REQUIRED' USING ERRCODE='23514';
            END IF;
            IF NEW.kind='sso' AND (NOT NEW.config ?& ARRAY['emergency_admin_id',
                'revocation_window_seconds','jit_enabled','jit_mappings']
                OR jsonb_typeof(NEW.config->'jit_enabled') IS DISTINCT FROM 'boolean'
                OR jsonb_typeof(NEW.config->'jit_mappings') IS DISTINCT FROM 'array'
                OR jsonb_typeof(NEW.config->'revocation_window_seconds') IS DISTINCT FROM 'number'
                OR NOT (NEW.config->>'revocation_window_seconds')~'^[0-9]+$'
                OR (NEW.config->>'revocation_window_seconds')::numeric NOT BETWEEN 30 AND 3600) THEN
                RAISE EXCEPTION 'F11_SSO_POLICY_REQUIRED' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER guard_f11_integration BEFORE INSERT OR UPDATE ON integration_configs
            FOR EACH ROW WHEN(NEW.kind IN ('sso','devops','outgoing_webhook'))
            EXECUTE FUNCTION guard_f11_integration();
        CREATE CONSTRAINT TRIGGER audit_f11_integration
            AFTER INSERT OR UPDATE ON integration_configs
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            WHEN(NEW.kind IN ('sso','devops','outgoing_webhook'))
            EXECUTE FUNCTION audit_f8_record();
        CREATE FUNCTION guard_f11_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE network text; attempt_outcome text; BEGIN
            IF TG_TABLE_NAME='external_identities' THEN
                IF NOT EXISTS(SELECT 1 FROM integration_configs WHERE id=NEW.integration_id
                    AND kind='sso') THEN
                    RAISE EXCEPTION 'F11_SSO_PROVIDER_REQUIRED' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND OLD.revoked_at IS NOT NULL THEN
                    RAISE EXCEPTION 'F11_IDENTITY_REVOKED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='sso_transactions' THEN
                IF NOT EXISTS(SELECT 1 FROM integration_configs WHERE id=NEW.integration_id
                    AND kind='sso' AND config_revision=NEW.config_revision)
                    OR NOT EXISTS(SELECT 1 FROM encrypted_secrets WHERE id=NEW.context_secret_id
                        AND owner_id=NEW.id AND purpose='sso_context') THEN
                    RAISE EXCEPTION 'F11_SSO_CONTEXT_REQUIRED' USING ERRCODE='23514';
                END IF;
                IF TG_OP='INSERT' AND (NEW.state<>'pending' OR NEW.issuer IS NOT NULL
                    OR NEW.consumed_at IS NOT NULL) THEN
                    RAISE EXCEPTION 'F11_SSO_INITIAL_STATE' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND (OLD.state NOT IN ('pending','verified')
                    OR (OLD.state='pending' AND NEW.state NOT IN ('verified','failed'))
                    OR (OLD.state='verified' AND (NEW.state NOT IN ('consumed','failed')
                        OR (NEW.issuer,NEW.subject,NEW.authenticated_at) IS DISTINCT FROM
                            (OLD.issuer,OLD.subject,OLD.authenticated_at)))
                    OR (NEW.state<>'failed' AND NEW.expires_at<=clock_timestamp())) THEN
                    RAISE EXCEPTION 'F11_SSO_ONE_USE' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='api_keys' THEN
                IF NOT EXISTS(SELECT 1 FROM encrypted_secrets WHERE id=NEW.pepper_secret_id
                    AND owner_id=NEW.id AND purpose='service_keys') THEN
                    RAISE EXCEPTION 'F11_KEY_PEPPER_OWNER' USING ERRCODE='23514';
                END IF;
                IF cardinality(NEW.scopes)<>(SELECT count(DISTINCT value)
                    FROM unnest(NEW.scopes) value) OR cardinality(NEW.department_ids)<>
                    (SELECT count(DISTINCT value) FROM unnest(NEW.department_ids) value) THEN
                    RAISE EXCEPTION 'F11_KEY_UNIQUE_SCOPE' USING ERRCODE='23514';
                END IF;
                IF NEW.allowed_networks IS NOT NULL THEN
                    FOREACH network IN ARRAY NEW.allowed_networks LOOP
                        BEGIN
                            IF network::cidr::text<>network THEN
                                RAISE EXCEPTION 'F11_KEY_NETWORK' USING ERRCODE='23514';
                            END IF;
                        EXCEPTION WHEN invalid_text_representation THEN
                            RAISE EXCEPTION 'F11_KEY_NETWORK' USING ERRCODE='23514';
                        END;
                    END LOOP;
                END IF;
                IF TG_OP='INSERT' AND NEW.rotated_from_id IS NOT NULL AND NOT EXISTS(
                    SELECT 1 FROM api_keys WHERE id=NEW.rotated_from_id AND revoked_at IS NOT NULL
                    AND owner_user_id=NEW.owner_user_id
                    AND service_principal_id=NEW.service_principal_id) THEN
                    RAISE EXCEPTION 'F11_KEY_ROTATION_OWNER' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND (OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL) THEN
                    RAISE EXCEPTION 'F11_KEY_REVOKED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='task_external_links' THEN
                IF NOT EXISTS(SELECT 1 FROM integration_configs WHERE id=NEW.integration_id
                    AND kind='devops' AND ((provider='github' AND NEW.kind<>'merge_request')
                        OR (provider='gitlab' AND NEW.kind<>'pull_request'))) THEN
                    RAISE EXCEPTION 'F11_DEVOPS_PROVIDER_REQUIRED' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' AND OLD.deactivated_at IS NOT NULL THEN
                    RAISE EXCEPTION 'F11_LINK_DEACTIVATED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='webhook_subscriptions' THEN
                IF NOT EXISTS(SELECT 1 FROM integration_configs WHERE id=NEW.integration_id
                    AND kind='outgoing_webhook') THEN
                    RAISE EXCEPTION 'F11_WEBHOOK_PROVIDER_REQUIRED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='webhook_deliveries' THEN
                IF NOT EXISTS(SELECT 1 FROM webhook_subscriptions subscription
                    JOIN encrypted_secrets secret ON secret.owner_id=subscription.integration_id
                    WHERE subscription.id=NEW.subscription_id AND secret.id=NEW.signing_secret_id
                    AND secret.purpose='integrations') THEN
                    RAISE EXCEPTION 'F11_WEBHOOK_SIGNING_OWNER' USING ERRCODE='23514';
                END IF;
                IF TG_OP='INSERT' AND (NEW.state<>'pending' OR NEW.attempt_count<>0) THEN
                    RAISE EXCEPTION 'F11_DELIVERY_INITIAL_STATE' USING ERRCODE='23514';
                END IF;
                IF TG_OP='INSERT' AND NEW.retry_of_id IS NOT NULL AND NOT EXISTS(
                    SELECT 1 FROM webhook_deliveries WHERE id=NEW.retry_of_id
                    AND state IN ('delivered','dead_letter','cancelled')
                    AND subscription_id=NEW.subscription_id AND outbox_id=NEW.outbox_id
                    AND body=NEW.body) THEN
                    RAISE EXCEPTION 'F11_REPLAY_IDENTITY' USING ERRCODE='23514';
                END IF;
                IF TG_OP='UPDATE' THEN
                    IF OLD.state NOT IN ('pending','sending') OR
                        (OLD.state='pending' AND NEW.state NOT IN ('sending','cancelled')) OR
                        (OLD.state='pending' AND NEW.state='sending' AND
                            (NEW.attempt_count<>OLD.attempt_count+1
                                OR NEW.lease_until<=clock_timestamp())) OR
                        (OLD.state='pending' AND NEW.state='cancelled' AND
                            NEW.attempt_count<>OLD.attempt_count) OR
                        (OLD.state='sending' AND (NEW.state='sending' OR
                            NEW.attempt_count<>OLD.attempt_count)) THEN
                        RAISE EXCEPTION 'F11_DELIVERY_TRANSITION' USING ERRCODE='23514';
                    END IF;
                    IF OLD.state='sending' THEN
                        SELECT outcome INTO attempt_outcome FROM webhook_attempts
                            WHERE delivery_id=OLD.id AND attempt_no=OLD.attempt_count
                            AND lease_token=OLD.lease_token;
                        IF NOT FOUND THEN
                            RAISE EXCEPTION 'F11_ATTEMPT_REQUIRED' USING ERRCODE='23514';
                        END IF;
                        IF (NEW.state='delivered')<>(attempt_outcome='accepted') OR
                            (NEW.state='pending' AND
                                (attempt_outcome NOT IN ('retryable','ambiguous')
                                 OR NEW.attempt_count>=NEW.max_attempts)) OR
                            (NEW.state='dead_letter' AND attempt_outcome='accepted') THEN
                            RAISE EXCEPTION 'F11_ATTEMPT_OUTCOME' USING ERRCODE='23514';
                        END IF;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION guard_f11_append() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_TABLE_NAME='sso_assertion_uses' THEN
                IF NOT EXISTS(SELECT 1 FROM sso_transactions WHERE id=NEW.transaction_id
                    AND integration_id=NEW.integration_id AND state='pending'
                    AND expires_at>clock_timestamp()) THEN
                    RAISE EXCEPTION 'F11_ASSERTION_CORRELATION' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='webhook_inbox' THEN
                IF NOT EXISTS(SELECT 1 FROM integration_configs WHERE id=NEW.integration_id
                    AND kind='devops') THEN
                    RAISE EXCEPTION 'F11_INBOX_PROVIDER_REQUIRED' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='webhook_attempts' THEN
                PERFORM 1 FROM webhook_deliveries WHERE id=NEW.delivery_id AND state='sending'
                    AND lease_token=NEW.lease_token AND attempt_count=NEW.attempt_no
                    AND ((lease_until>clock_timestamp() AND NEW.result_code<>'LEASE_EXPIRED')
                        OR (lease_until<=clock_timestamp() AND NEW.result_code='LEASE_EXPIRED'
                            AND NEW.outcome='ambiguous')) FOR UPDATE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'F11_DELIVERY_FENCED' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        REVOKE ALL ON FUNCTION guard_f11_integration(),guard_f11_record(),guard_f11_append()
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION guard_f11_integration(),guard_f11_record(),guard_f11_append()
            TO ocote_runtime;
        CREATE INDEX ix_f11_session_identity ON refresh_sessions(external_identity_id);
        CREATE INDEX ix_f11_identity_user ON external_identities(user_id,revoked_at);
        CREATE INDEX ix_f11_sso_expiry ON sso_transactions(state,expires_at,id);
        CREATE INDEX ix_f11_key_principal ON api_keys(service_principal_id,revoked_at,expires_at);
        CREATE INDEX ix_f11_key_rate ON audit_events(entity_id,created_at)
            WHERE entity_type='api_keys' AND event_type='service_authenticated';
        CREATE INDEX ix_f11_link_task ON task_external_links(task_id,deactivated_at,created_at,id);
        CREATE INDEX ix_f11_delivery_due ON webhook_deliveries(state,next_attempt_at,id);
    """)
    for table in TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC,ocote_runtime")
        if table in APPEND_ONLY:
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION protect_f9_record('append')"
            )
            op.execute(
                f"CREATE TRIGGER guard_{table} BEFORE INSERT ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION guard_f11_append()"
            )
            privileges = "SELECT,INSERT"
        else:
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION protect_f9_record('{IMMUTABLE[table]}')"
            )
            op.execute(
                f"CREATE TRIGGER guard_{table} BEFORE INSERT OR UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION guard_f11_record()"
            )
            op.execute(
                f"CREATE CONSTRAINT TRIGGER z_f11_audit_{table} AFTER INSERT OR UPDATE ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION audit_f9_record()"
            )
            privileges = "SELECT,INSERT,UPDATE"
        op.execute(
            f"CREATE TRIGGER truncate_{table} BEFORE TRUNCATE ON {table} "
            "EXECUTE FUNCTION protect_f9_record('append')"
        )
        op.execute(f"GRANT {privileges} ON {table} TO ocote_runtime")
    op.execute("""
        DO $$ DECLARE reference record; BEGIN
            FOR reference IN SELECT k.table_name,k.column_name
                FROM information_schema.key_column_usage k
                JOIN information_schema.table_constraints c
                    ON c.constraint_schema=k.constraint_schema
                    AND c.constraint_name=k.constraint_name AND c.table_name=k.table_name
                WHERE c.constraint_type='FOREIGN KEY' AND k.table_schema='public'
                    AND k.table_name IN ('external_identities','sso_transactions',
                        'sso_assertion_uses','api_keys','task_external_links','webhook_inbox',
                        'webhook_subscriptions','webhook_deliveries','webhook_attempts')
            LOOP EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(%I,created_at,id)',
                'ix_f11_'||reference.table_name||'_'||reference.column_name,
                reference.table_name,reference.column_name);
            END LOOP;
        END $$;
    """)


def downgrade():
    raise RuntimeError("F11 history cannot be discarded; use authorized isolated recovery")