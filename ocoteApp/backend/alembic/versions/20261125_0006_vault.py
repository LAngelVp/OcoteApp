"""F7 vault and verified local integrations, additive and without seeds."""

from alembic import op

revision = "20261125_0006"
down_revision = "20261125_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE deployment_instances (
            id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            singleton BOOLEAN NOT NULL DEFAULT true UNIQUE CHECK(singleton),
            root_key_ref VARCHAR(200) NOT NULL CHECK(length(root_key_ref)>0),
            primary_name VARCHAR(160), primary_contact VARCHAR(254),
            backup_name VARCHAR(160), backup_contact VARCHAR(254),
            CHECK(primary_name IS NULL OR length(btrim(primary_name)) BETWEEN 1 AND 160),
            CHECK(backup_name IS NULL OR length(btrim(backup_name)) BETWEEN 1 AND 160),
            CHECK(primary_contact IS NULL OR length(btrim(primary_contact)) BETWEEN 1 AND 254),
            CHECK(backup_contact IS NULL OR length(btrim(backup_contact)) BETWEEN 1 AND 254),
            CHECK(primary_name IS NULL OR backup_name IS NULL OR
                lower(regexp_replace(btrim(primary_name),'\\s+',' ','g')) <>
                lower(regexp_replace(btrim(backup_name),'\\s+',' ','g'))),
            CHECK(primary_contact IS NULL OR backup_contact IS NULL OR
                lower(regexp_replace(btrim(primary_contact),'\\s+',' ','g')) <>
                lower(regexp_replace(btrim(backup_contact),'\\s+',' ','g')))
        );
        CREATE TABLE configuration_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            request_id UUID NOT NULL, entity_id UUID NOT NULL,
            entity_type VARCHAR(40) NOT NULL,
            reason VARCHAR(1000) NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 1000),
            changed_keys JSONB NOT NULL CHECK(jsonb_typeof(changed_keys)='array')
        );
        CREATE TABLE secret_key_versions (
            id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            instance_id UUID NOT NULL REFERENCES deployment_instances(id) ON DELETE RESTRICT,
            purpose VARCHAR(30) NOT NULL CHECK(purpose IN
                ('jwt_signing','csrf','health_monitor','local_storage','clamav','backup')),
            epoch INTEGER NOT NULL CHECK(epoch>0), root_key_ref VARCHAR(200) NOT NULL,
            algorithm VARCHAR(20) NOT NULL CHECK(algorithm='AES-256-GCM'),
            nonce BYTEA NOT NULL CHECK(octet_length(nonce)=12),
            wrapped_dek BYTEA NOT NULL CHECK(octet_length(wrapped_dek)=48),
            UNIQUE(instance_id,purpose,epoch), UNIQUE(instance_id,nonce),
            UNIQUE(id,purpose)
        );
        CREATE TABLE encrypted_secrets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            owner_id UUID NOT NULL, purpose VARCHAR(30) NOT NULL,
            secret_version INTEGER NOT NULL CHECK(secret_version>0),
            key_id UUID NOT NULL, nonce BYTEA NOT NULL CHECK(octet_length(nonce)=12),
            ciphertext BYTEA NOT NULL CHECK(octet_length(ciphertext) BETWEEN 17 AND 65552),
            FOREIGN KEY(key_id,purpose) REFERENCES secret_key_versions(id,purpose)
                ON DELETE RESTRICT,
            UNIQUE(owner_id,purpose,secret_version), UNIQUE(key_id,nonce)
        );
        CREATE TABLE integration_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            kind VARCHAR(20) NOT NULL UNIQUE CHECK(kind IN ('local_storage','clamav')),
            config JSONB NOT NULL CHECK(jsonb_typeof(config)='object'),
            config_revision INTEGER NOT NULL DEFAULT 1 CHECK(config_revision>0),
            is_active BOOLEAN NOT NULL DEFAULT false,
            tested_version INTEGER, tested_at TIMESTAMPTZ,
            CHECK((tested_version IS NULL)=(tested_at IS NULL)),
            CHECK(tested_version IS NULL OR tested_version BETWEEN 1 AND config_revision),
            CHECK(NOT is_active OR (tested_version IS NOT NULL AND tested_at IS NOT NULL
                AND tested_version=config_revision)),
            CHECK((kind='local_storage' AND jsonb_typeof(config->'root')='string'
                AND length(config->>'root') BETWEEN 1 AND 500
                AND config ? 'root' AND config-'root'='{}'::jsonb) OR
                (kind='clamav' AND config ?& ARRAY['port','timeout']
                AND config-ARRAY['port','timeout']='{}'::jsonb
                AND jsonb_typeof(config->'port')='number'
                AND jsonb_typeof(config->'timeout')='number'
                AND (config->>'port')~'^[0-9]+$' AND (config->>'timeout')~'^[0-9]+$'
                AND (config->>'port')::numeric BETWEEN 1 AND 65535
                AND (config->>'timeout')::numeric BETWEEN 1 AND 8))
        );
        CREATE TABLE integration_health_checks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            integration_id UUID NOT NULL REFERENCES integration_configs(id) ON DELETE RESTRICT,
            config_version INTEGER NOT NULL CHECK(config_version>0),
            status VARCHAR(12) NOT NULL CHECK(status IN ('passed','failed')),
            result_code VARCHAR(80) NOT NULL,
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            request_id UUID NOT NULL
        );
        CREATE FUNCTION protect_f7_record() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
            IF TG_OP IN ('DELETE','TRUNCATE') THEN
                RAISE EXCEPTION 'F7 records cannot be discarded' USING ERRCODE='23514';
            END IF;
            IF TG_OP='INSERT' THEN
                IF NEW.version<>1 THEN
                    RAISE EXCEPTION 'Initial version must be one' USING ERRCODE='23514';
                END IF;
                IF TG_TABLE_NAME='integration_configs' THEN
                    IF NEW.is_active OR NEW.tested_version IS NOT NULL
                        OR NEW.config_revision<>1 THEN
                        RAISE EXCEPTION 'Provider must start unverified' USING ERRCODE='23514';
                    END IF;
                END IF;
                RETURN NEW;
            END IF;
            IF TG_TABLE_NAME NOT IN ('deployment_instances','integration_configs') THEN
                RAISE EXCEPTION 'F7 append-only record' USING ERRCODE='23514';
            END IF;
            IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at OR
                NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
                RAISE EXCEPTION 'F7 identity/version conflict' USING ERRCODE='23514';
            END IF;
            IF TG_TABLE_NAME='deployment_instances' THEN
                IF NEW.root_key_ref<>OLD.root_key_ref OR NEW.singleton<>OLD.singleton THEN
                    RAISE EXCEPTION 'F7 root identity immutable' USING ERRCODE='23514';
                END IF;
            ELSE
                IF NEW.kind<>OLD.kind THEN
                    RAISE EXCEPTION 'F7 provider kind immutable' USING ERRCODE='23514';
                END IF;
                IF NEW.config<>OLD.config AND
                    (NEW.is_active OR NEW.tested_version IS NOT NULL OR
                        NEW.config_revision<>OLD.config_revision+1) THEN
                    RAISE EXCEPTION 'Changed configuration requires new test'
                        USING ERRCODE='23514';
                END IF;
                IF NEW.config=OLD.config AND NEW.config_revision<>OLD.config_revision THEN
                    RAISE EXCEPTION 'Stable configuration revision' USING ERRCODE='23514';
                END IF;
                IF NEW.is_active AND NOT EXISTS (
                    SELECT 1 FROM integration_health_checks h WHERE h.integration_id=NEW.id
                    AND h.config_version=NEW.config_revision AND h.status='passed'
                    AND h.created_at>=clock_timestamp()-interval '15 minutes'
                ) THEN
                    RAISE EXCEPTION 'Activation requires fresh version-bound test'
                        USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        REVOKE ALL ON deployment_instances,configuration_revisions,secret_key_versions,
            encrypted_secrets,integration_configs,integration_health_checks FROM PUBLIC;
        GRANT SELECT,UPDATE ON deployment_instances TO ocote_runtime;
        GRANT SELECT,INSERT,UPDATE ON integration_configs TO ocote_runtime;
        GRANT SELECT,INSERT ON configuration_revisions,secret_key_versions,
            encrypted_secrets,integration_health_checks TO ocote_runtime;
        REVOKE ALL ON FUNCTION protect_f7_record() FROM PUBLIC;
    """)
    for table in (
        "deployment_instances",
        "configuration_revisions",
        "secret_key_versions",
        "encrypted_secrets",
        "integration_configs",
        "integration_health_checks",
    ):
        operations = (
            "INSERT OR UPDATE OR DELETE"
            if table in {"deployment_instances", "integration_configs"}
            else "UPDATE OR DELETE"
        )
        op.execute(
            f"CREATE TRIGGER protect_{table} BEFORE {operations} ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_f7_record()"
        )
        op.execute(
            f"CREATE TRIGGER no_truncate_{table} BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION protect_f7_record()"
        )


def downgrade():
    raise RuntimeError("Vault history cannot be discarded; use authorized isolated recovery")
