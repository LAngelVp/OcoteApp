"""F2 empty identity, administration and configuration; no business seeds."""

from alembic import op

revision = "20261124_0002"
down_revision = "20261124_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE departments (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      code VARCHAR(40) NOT NULL UNIQUE CHECK(code ~ '^[a-z][a-z0-9_]*$'),
      name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) > 0),
      is_active BOOLEAN NOT NULL DEFAULT true,
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE TABLE users (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
      email VARCHAR(254) NOT NULL UNIQUE CHECK(email = lower(btrim(email))
        AND email ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'),
      display_name VARCHAR(120) NOT NULL CHECK(length(btrim(display_name)) > 0),
      password_hash TEXT NOT NULL CHECK(password_hash LIKE '$argon2id$%'),
      role VARCHAR(20) NOT NULL CHECK(role IN ('admin','gerente','lider','colaborador')),
      token_version INT NOT NULL DEFAULT 1 CHECK(token_version > 0),
      is_active BOOLEAN NOT NULL DEFAULT true,
      CHECK(role IN ('admin','gerente') OR department_id IS NOT NULL),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE INDEX ix_users_department_active ON users(department_id,is_active);
    CREATE TABLE refresh_sessions (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      family_id UUID NOT NULL, jti_hash CHAR(64) NOT NULL UNIQUE
        CHECK(jti_hash ~ '^[0-9a-f]{64}$'),
      token_version INT NOT NULL CHECK(token_version > 0),
      expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
      replaced_by_id UUID UNIQUE REFERENCES refresh_sessions(id) ON DELETE RESTRICT,
      CHECK(expires_at > created_at),
      CHECK(replaced_by_id IS NULL OR consumed_at IS NOT NULL),
      CHECK(consumed_at IS NULL OR consumed_at >= created_at),
      CHECK(revoked_at IS NULL OR revoked_at >= created_at)
    );
    CREATE INDEX ix_refresh_family ON refresh_sessions(family_id);
    CREATE INDEX ix_refresh_user_revoked ON refresh_sessions(user_id,revoked_at);
    CREATE INDEX ix_refresh_expiration ON refresh_sessions(expires_at);
    CREATE TABLE workflow_stages (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      code VARCHAR(40) NOT NULL UNIQUE CHECK(code ~ '^[a-z][a-z0-9_]*$'),
      name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) > 0),
      position INT NOT NULL CHECK(position >= 0),
      CONSTRAINT uq_stage_position UNIQUE(position) DEFERRABLE INITIALLY DEFERRED,
      kind VARCHAR(12) NOT NULL CHECK(kind IN ('open','blocked','completed')),
      is_initial BOOLEAN NOT NULL DEFAULT false, requires_evidence BOOLEAN NOT NULL DEFAULT false,
      requires_reason BOOLEAN NOT NULL DEFAULT false, is_active BOOLEAN NOT NULL DEFAULT true,
      CHECK(NOT is_initial OR (kind='open' AND is_active
        AND NOT requires_evidence AND NOT requires_reason)),
      CHECK(kind <> 'completed' OR is_active),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE UNIQUE INDEX uq_stage_initial ON workflow_stages((true)) WHERE is_initial;
    CREATE UNIQUE INDEX uq_stage_terminal ON workflow_stages((true)) WHERE kind='completed';
    CREATE TABLE workflow_transitions (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      from_stage_id UUID NOT NULL REFERENCES workflow_stages(id) ON DELETE RESTRICT,
      to_stage_id UUID NOT NULL REFERENCES workflow_stages(id) ON DELETE RESTRICT,
      allowed_roles VARCHAR(20)[] NOT NULL CHECK(cardinality(allowed_roles) > 0
        AND allowed_roles <@ ARRAY['admin','lider','colaborador']::VARCHAR[]
        AND array_position(allowed_roles,NULL) IS NULL),
      is_active BOOLEAN NOT NULL DEFAULT true,
      CHECK(NOT is_active OR 'admin'=ANY(allowed_roles)),
      UNIQUE(from_stage_id,to_stage_id), CHECK(from_stage_id <> to_stage_id),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE INDEX ix_transition_origin_active ON workflow_transitions(from_stage_id,is_active);
    CREATE TABLE audit_events (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      actor_id UUID REFERENCES users(id) ON DELETE RESTRICT,
      event_type VARCHAR(80) NOT NULL CHECK(event_type IN
        ('bootstrap_admin','login_success','login_failed','session_refreshed','refresh_reuse',
         'logout','password_changed','administration_changed','security_denied')),
      entity_type VARCHAR(40) NOT NULL, entity_id UUID,
      before_data JSONB NOT NULL CHECK(jsonb_typeof(before_data)='object'),
      after_data JSONB NOT NULL CHECK(jsonb_typeof(after_data)='object'), request_id UUID NOT NULL,
      outcome VARCHAR(12) NOT NULL CHECK(outcome IN ('success','denied','failure'))
    );
    CREATE INDEX ix_audit_entity ON audit_events(entity_type,entity_id,created_at,id);
    CREATE INDEX ix_audit_actor ON audit_events(actor_id,created_at,id);
    CREATE INDEX ix_audit_request ON audit_events(request_id);
    CREATE TABLE system_settings (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      key VARCHAR(64) NOT NULL UNIQUE CHECK(key IN
        ('organization_name','organization_timezone','evidence_max_bytes','export_max_rows')),
      value JSONB NOT NULL,
      updated_by UUID REFERENCES users(id) ON DELETE RESTRICT,
      CHECK(CASE WHEN key IN ('organization_name','organization_timezone') THEN
        jsonb_typeof(value)='string' AND length(btrim(value #>> '{}')) BETWEEN 1 AND
          CASE WHEN key='organization_name' THEN 160 ELSE 100 END
        WHEN jsonb_typeof(value)='number' THEN
          (value #>> '{}')::NUMERIC=trunc((value #>> '{}')::NUMERIC)
          AND (value #>> '{}')::NUMERIC BETWEEN 1 AND
            CASE WHEN key='evidence_max_bytes' THEN 10485760 ELSE 10000 END
        ELSE false END),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE TABLE priorities (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      code VARCHAR(40) NOT NULL UNIQUE CHECK(code ~ '^[a-z][a-z0-9_]*$'),
      name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) > 0),
      position INT NOT NULL CHECK(position >= 0),
      CONSTRAINT uq_priority_position UNIQUE(position) DEFERRABLE INITIALLY DEFERRED,
      is_active BOOLEAN NOT NULL DEFAULT true, CHECK(code <> 'normal' OR is_active),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE TABLE horizon_types (
      id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INT NOT NULL DEFAULT 1,
      code VARCHAR(12) NOT NULL UNIQUE CHECK(code IN
        ('annual','semiannual','quarterly','monthly','custom')),
      name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) > 0),
      position INT NOT NULL CHECK(position >= 0),
      CONSTRAINT uq_horizon_position UNIQUE(position) DEFERRABLE INITIALLY DEFERRED,
      is_active BOOLEAN NOT NULL DEFAULT true, CHECK(code <> 'custom' OR is_active),
      CHECK(version > 0 AND updated_at >= created_at)
    );
    CREATE FUNCTION protect_f2_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Deletion prohibited'; END IF;
      IF TG_TABLE_NAME='audit_events' THEN RAISE EXCEPTION 'Append-only audit'; END IF;
      IF NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
         OR NEW.version <> OLD.version+1 OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Identity or version conflict';
      END IF;
      IF TG_TABLE_NAME IN ('departments','priorities','horizon_types','workflow_stages') THEN
        IF NEW.code <> OLD.code THEN RAISE EXCEPTION 'Stable code'; END IF;
      END IF;
      IF TG_TABLE_NAME='system_settings' THEN
        IF NEW.key <> OLD.key THEN RAISE EXCEPTION 'Stable key'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in (
        "departments",
        "users",
        "workflow_stages",
        "workflow_transitions",
        "system_settings",
        "priorities",
        "horizon_types",
        "audit_events",
    ):
        op.execute(
            f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_f2_identity()"
        )
    op.execute("""
      REVOKE ALL ON departments,users,refresh_sessions,workflow_stages,workflow_transitions,
        audit_events,system_settings,priorities,horizon_types FROM PUBLIC;
      GRANT SELECT,INSERT,UPDATE ON departments,users,refresh_sessions,workflow_stages,
        workflow_transitions,system_settings,priorities,horizon_types TO ocote_runtime;
      GRANT SELECT,INSERT ON audit_events TO ocote_runtime;
      REVOKE ALL ON FUNCTION protect_f2_identity() FROM PUBLIC;
    """)


def downgrade():
    raise RuntimeError(
        "Destructive identity downgrade prohibited; use approved fix-forward/restore"
    )
