"""F9 scoped execution and collaboration, without business seeds."""

from alembic import op

revision = "20261125_0008"
down_revision = "20261125_0007"
branch_labels = None
depends_on = None

IDENTITY = """
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
"""
MUTABLE = (
    IDENTITY
    + """,
updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at)
"""
)
SCOPE = """
scope_kind VARCHAR(20) NOT NULL CHECK(scope_kind IN ('organization','department')),
department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
CHECK((scope_kind='department')=(department_id IS NOT NULL))
"""
ENTITY = """
plan_id UUID REFERENCES annual_plans(id) ON DELETE RESTRICT,
objective_id UUID REFERENCES objectives(id) ON DELETE RESTRICT,
task_id UUID REFERENCES tasks(id) ON DELETE RESTRICT
"""
TABLES = {
    "service_principals": (
        MUTABLE,
        """
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        approved_scopes TEXT[] NOT NULL CHECK(cardinality(approved_scopes) BETWEEN 1 AND 2
            AND approved_scopes <@ ARRAY['tasks:create','subtasks:create']
            AND array_position(approved_scopes,NULL) IS NULL),
        department_ids UUID[] NOT NULL CHECK(cardinality(department_ids) BETWEEN 1 AND 100
            AND array_position(department_ids,NULL) IS NULL),
        is_active BOOLEAN NOT NULL, token_version INTEGER NOT NULL CHECK(token_version>0),
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
    """,
    ),
    "job_runs": (
        MUTABLE,
        """
        kind VARCHAR(40) NOT NULL CHECK(kind='recurrence'),
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        service_principal_id UUID NOT NULL REFERENCES service_principals(id) ON DELETE RESTRICT,
        request_id UUID NOT NULL, idempotency_key UUID NOT NULL,
        input_hash VARCHAR(64) NOT NULL CHECK(input_hash~'^[0-9a-f]{64}$'),
        state VARCHAR(20) NOT NULL CHECK(state IN ('running','succeeded','paused','failed')),
        attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 1000),
        retry_of_id UUID REFERENCES job_runs(id) ON DELETE RESTRICT,
        lease_token UUID, lease_until TIMESTAMPTZ, next_run_at TIMESTAMPTZ,
        configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
        CHECK((lease_token IS NULL)=(lease_until IS NULL)),
        UNIQUE(kind,owner_user_id,idempotency_key)
    """,
    ),
    "transactional_outbox": (
        IDENTITY,
        """
        event_id UUID NOT NULL UNIQUE,
        event_type VARCHAR(40) NOT NULL CHECK(event_type IN
            ('dependency_changed','impediment_changed','comment_changed','recurrence_generated')),
        schema_version INTEGER NOT NULL CHECK(schema_version=1),
        task_id UUID REFERENCES tasks(id) ON DELETE RESTRICT,
        objective_id UUID REFERENCES objectives(id) ON DELETE RESTRICT,
        actor_id UUID REFERENCES users(id) ON DELETE RESTRICT,
        actor_service_id UUID REFERENCES service_principals(id) ON DELETE RESTRICT,
        department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
        payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object'
            AND payload-ARRAY['resource_id','version','owner_user_id']='{}'::jsonb),
        CHECK(num_nonnulls(task_id,objective_id)=1),
        CHECK(num_nonnulls(actor_id,actor_service_id)=1)
    """,
    ),
    "task_dependencies": (
        MUTABLE,
        """
        predecessor_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        successor_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        active BOOLEAN NOT NULL,
        CHECK(predecessor_task_id<>successor_task_id),
        UNIQUE(predecessor_task_id,successor_task_id)
    """,
    ),
    "task_impediments": (
        MUTABLE,
        """
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 2000),
        severity VARCHAR(12) NOT NULL CHECK(severity IN ('low','medium','high','critical')),
        kind VARCHAR(20) NOT NULL CHECK(kind IN ('internal','external','resource','decision')),
        required_area VARCHAR(120) CHECK(length(btrim(required_area)) BETWEEN 1 AND 120),
        opened_at TIMESTAMPTZ NOT NULL, closed_at TIMESTAMPTZ, resolution TEXT,
        CHECK((closed_at IS NULL AND resolution IS NULL) OR
            (closed_at>=opened_at AND length(btrim(resolution)) BETWEEN 10 AND 2000
             AND closed_at IS NOT NULL AND resolution IS NOT NULL))
    """,
    ),
    "templates": (
        MUTABLE,
        SCOPE
        + """,
        entity_type VARCHAR(12) NOT NULL CHECK(entity_type IN ('plan','objective','task')),
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        name_normalized VARCHAR(120) NOT NULL CHECK(name_normalized=lower(btrim(name))),
        current_version INTEGER NOT NULL CHECK(current_version>0), is_active BOOLEAN NOT NULL,
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        UNIQUE NULLS NOT DISTINCT(entity_type,name_normalized,scope_kind,department_id)
    """,
    ),
    "template_versions": (
        IDENTITY,
        """
        template_id UUID NOT NULL REFERENCES templates(id) ON DELETE RESTRICT,
        template_version INTEGER NOT NULL CHECK(template_version>0),
        schema_version INTEGER NOT NULL CHECK(schema_version=1),
        payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object'
            AND octet_length(payload::text)<=65536 AND payload-ARRAY['title','description',
                'horizon_type','priority_id','duration_days','subtasks','tag_ids','custom_fields',
                'objectives','tasks','start_offset_days']='{}'::jsonb),
        payload_hash VARCHAR(64) NOT NULL CHECK(payload_hash~'^[0-9a-f]{64}$'),
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        UNIQUE(template_id,template_version)
    """,
    ),
    "recurrence_schedules": (
        MUTABLE,
        """
        template_version_id UUID NOT NULL REFERENCES template_versions(id) ON DELETE RESTRICT,
        owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        service_principal_id UUID NOT NULL REFERENCES service_principals(id) ON DELETE RESTRICT,
        objective_id UUID NOT NULL REFERENCES objectives(id) ON DELETE RESTRICT,
        assignee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        calendar_id UUID NOT NULL REFERENCES calendar_configs(id) ON DELETE RESTRICT,
        configuration_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
        calendar_snapshot JSONB NOT NULL CHECK(jsonb_typeof(calendar_snapshot)='object'
            AND calendar_snapshot ?& ARRAY['weekday_mask','holidays','calendar_versions']
            AND calendar_snapshot-ARRAY['weekday_mask','holidays','calendar_versions']='{}'::jsonb),
        timezone VARCHAR(64) NOT NULL CHECK(length(timezone) BETWEEN 1 AND 64),
        frequency VARCHAR(12) NOT NULL CHECK(frequency IN ('daily','weekly','monthly','yearly')),
        interval INTEGER NOT NULL CHECK(interval BETWEEN 1 AND 366),
        start_date DATE NOT NULL, end_date DATE, occurrence_count INTEGER,
        end_policy VARCHAR(12) NOT NULL CHECK(end_policy IN ('skip','last_day')),
        non_business_policy VARCHAR(12) NOT NULL
            CHECK(non_business_policy IN ('keep','skip','next','previous')),
        missed_policy VARCHAR(12) NOT NULL CHECK(missed_policy IN ('skip','catch_up')),
        next_due_at DATE, enabled BOOLEAN NOT NULL,
        CHECK(num_nonnulls(end_date,occurrence_count)=1),
        CHECK(end_date IS NULL OR end_date>=start_date),
        CHECK(occurrence_count IS NULL OR occurrence_count BETWEEN 1 AND 1000)
    """,
    ),
    "recurrence_occurrences": (
        IDENTITY,
        ENTITY
        + """,
        schedule_id UUID NOT NULL REFERENCES recurrence_schedules(id) ON DELETE RESTRICT,
        job_id UUID NOT NULL REFERENCES job_runs(id) ON DELETE RESTRICT,
        scheduled_for DATE NOT NULL, effective_date DATE NOT NULL,
        timezone VARCHAR(64) NOT NULL CHECK(length(timezone) BETWEEN 1 AND 64),
        calendar_revision_id UUID NOT NULL REFERENCES configuration_revisions(id),
        result VARCHAR(12) NOT NULL CHECK(result IN ('generated','skipped')),
        CHECK((result='generated' AND num_nonnulls(plan_id,objective_id,task_id)=1)
            OR (result='skipped' AND num_nonnulls(plan_id,objective_id,task_id)=0)),
        UNIQUE(schedule_id,scheduled_for)
    """,
    ),
    "custom_field_definitions": (
        MUTABLE,
        SCOPE
        + """,
        entity_type VARCHAR(12) NOT NULL CHECK(entity_type IN ('plan','objective','task')),
        key VARCHAR(64) NOT NULL CHECK(key~'^[a-z][a-z0-9_]{0,63}$'),
        label VARCHAR(120) NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 120),
        data_type VARCHAR(12) NOT NULL CHECK(data_type IN
            ('text','number','date','boolean','select','multi_select','url')),
        constraints JSONB NOT NULL CHECK(jsonb_typeof(constraints)='object'
            AND constraints-ARRAY['min_length','max_length','min','max']='{}'::jsonb),
        required_stage_ids UUID[] NOT NULL CHECK(cardinality(required_stage_ids)<=50
            AND array_position(required_stage_ids,NULL) IS NULL),
        required_on_create BOOLEAN NOT NULL, active BOOLEAN NOT NULL,
        UNIQUE NULLS NOT DISTINCT(entity_type,key,scope_kind,department_id)
    """,
    ),
    "custom_field_options": (
        MUTABLE,
        """
        definition_id UUID NOT NULL REFERENCES custom_field_definitions(id) ON DELETE RESTRICT,
        code VARCHAR(64) NOT NULL CHECK(code~'^[a-z][a-z0-9_]{0,63}$'),
        label VARCHAR(120) NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 120),
        position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 10000),
        is_active BOOLEAN NOT NULL, UNIQUE(definition_id,code)
    """,
    ),
    "custom_field_values": (
        MUTABLE,
        ENTITY
        + """,
        definition_id UUID NOT NULL REFERENCES custom_field_definitions(id) ON DELETE RESTRICT,
        text_value TEXT CHECK(length(text_value)<=2048), number_value NUMERIC(18,4),
        date_value DATE, boolean_value BOOLEAN,
        option_id UUID REFERENCES custom_field_options(id) ON DELETE RESTRICT,
        option_ids UUID[] CHECK(cardinality(option_ids) BETWEEN 1 AND 50
            AND array_position(option_ids,NULL) IS NULL),
        CHECK(num_nonnulls(plan_id,objective_id,task_id)=1),
        CHECK(num_nonnulls(text_value,number_value,date_value,boolean_value,option_id,option_ids)<=1),
        UNIQUE NULLS NOT DISTINCT(definition_id,plan_id,objective_id,task_id)
    """,
    ),
    "tags": (
        MUTABLE,
        SCOPE
        + """,
        name_normalized VARCHAR(60) NOT NULL CHECK(name_normalized=lower(btrim(label))),
        label VARCHAR(60) NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 60),
        color_code VARCHAR(12) NOT NULL CHECK(color_code IN ('forest','rust','ink','danger')),
        is_active BOOLEAN NOT NULL,
        UNIQUE NULLS NOT DISTINCT(name_normalized,scope_kind,department_id)
    """,
    ),
    "entity_tags": (
        MUTABLE,
        ENTITY
        + """,
        tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
        assigned_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        active BOOLEAN NOT NULL, CHECK(num_nonnulls(plan_id,objective_id,task_id)=1),
        UNIQUE NULLS NOT DISTINCT(tag_id,plan_id,objective_id,task_id)
    """,
    ),
    "comments": (
        MUTABLE,
        """
        task_id UUID REFERENCES tasks(id) ON DELETE RESTRICT,
        objective_id UUID REFERENCES objectives(id) ON DELETE RESTRICT,
        author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        parent_comment_id UUID REFERENCES comments(id) ON DELETE RESTRICT,
        current_revision INTEGER NOT NULL CHECK(current_revision>0), annulled_at TIMESTAMPTZ,
        CHECK(num_nonnulls(task_id,objective_id)=1), CHECK(parent_comment_id IS DISTINCT FROM id)
    """,
    ),
    "comment_revisions": (
        IDENTITY,
        """
        comment_id UUID NOT NULL REFERENCES comments(id) ON DELETE RESTRICT,
        author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        revision_no INTEGER NOT NULL CHECK(revision_no>0),
        body TEXT NOT NULL CHECK(length(btrim(body)) BETWEEN 1 AND 10000),
        reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 2000),
        annulment BOOLEAN NOT NULL, UNIQUE(comment_id,revision_no)
    """,
    ),
    "comment_mentions": (
        IDENTITY,
        """
        comment_revision_id UUID NOT NULL REFERENCES comment_revisions(id) ON DELETE RESTRICT,
        mentioned_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        notification_event_id UUID REFERENCES transactional_outbox(id) ON DELETE RESTRICT,
        UNIQUE(comment_revision_id,mentioned_user_id)
    """,
    ),
    "saved_views": (
        MUTABLE,
        """
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        scope_kind VARCHAR(20) NOT NULL CHECK(scope_kind IN
            ('personal','department','organization')),
        department_id UUID REFERENCES departments(id) ON DELETE RESTRICT,
        entity_type VARCHAR(12) NOT NULL
            CHECK(entity_type IN ('plan','objective','task','comment')),
        name VARCHAR(120) NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
        filter_schema_version INTEGER NOT NULL CHECK(filter_schema_version=1),
        filters JSONB NOT NULL CHECK(jsonb_typeof(filters)='object' AND filters-ARRAY[
            'q','entity_type','tag_ids','blocked','stage_id','assignee_id','custom_fields']='{}'::jsonb),
        active BOOLEAN NOT NULL, CHECK((scope_kind='department')=(department_id IS NOT NULL)),
        UNIQUE NULLS NOT DISTINCT(owner_id,name,entity_type,scope_kind,department_id)
    """,
    ),
}
APPEND_ONLY = {
    "transactional_outbox",
    "template_versions",
    "recurrence_occurrences",
    "comment_revisions",
    "comment_mentions",
}
IMMUTABLE = {
    "service_principals": "created_by",
    "job_runs": (
        "kind,owner_user_id,service_principal_id,request_id,idempotency_key,"
        "input_hash,attempt,retry_of_id"
    ),
    "task_dependencies": "predecessor_task_id,successor_task_id,created_by",
    "task_impediments": "task_id,owner_user_id,reason,severity,kind,required_area,opened_at",
    "templates": "entity_type,scope_kind,department_id,created_by",
    "recurrence_schedules": "owner_user_id",
    "custom_field_definitions": "entity_type,key,data_type,scope_kind,department_id",
    "custom_field_options": "definition_id,code",
    "custom_field_values": "definition_id,plan_id,objective_id,task_id",
    "tags": "scope_kind,department_id",
    "entity_tags": "tag_id,plan_id,objective_id,task_id,assigned_by",
    "comments": "task_id,objective_id,author_id,parent_comment_id",
    "saved_views": "owner_id,entity_type,scope_kind,department_id",
}


def upgrade():
    for table, (identity, columns) in TABLES.items():
        op.execute(f"CREATE TABLE {table} ({identity},{columns})")
    op.execute("""
        ALTER TABLE task_history ALTER COLUMN actor_id DROP NOT NULL,
            ADD COLUMN actor_service_id UUID REFERENCES service_principals(id) ON DELETE RESTRICT,
            ADD COLUMN actor_kind VARCHAR(12) GENERATED ALWAYS AS
                (CASE WHEN actor_service_id IS NOT NULL THEN 'service' ELSE 'human' END) STORED,
            ADD CONSTRAINT ck_f9_history_actor CHECK(num_nonnulls(actor_id,actor_service_id)=1);
        ALTER TABLE audit_events
            ADD COLUMN actor_service_id UUID REFERENCES service_principals(id) ON DELETE RESTRICT,
            ADD COLUMN actor_kind VARCHAR(12) GENERATED ALWAYS AS (CASE
                WHEN actor_service_id IS NOT NULL THEN 'service'
                WHEN actor_id IS NOT NULL THEN 'human' ELSE 'anonymous' END) STORED,
            ADD CONSTRAINT ck_f9_audit_actor CHECK(num_nonnulls(actor_id,actor_service_id)<=1);
        ALTER TABLE task_history DROP CONSTRAINT task_history_event_type_check,
            ADD CONSTRAINT ck_f9_history_type CHECK(event_type IN
                ('task_created','task_updated','stage_changed','assignment_changed',
                 'due_date_changed','schedule_changed','subtask_created','subtask_updated',
                 'subtask_completed','subtask_due_date_changed','subtask_schedule_changed',
                 'evidence_added','dependency_changed','impediment_changed','metadata_changed',
                 'comment_changed','recurrence_generated'));
        DO $$ DECLARE constraint_name text; BEGIN
            FOR constraint_name IN SELECT conname FROM pg_constraint
                WHERE conrelid='public.feature_flags'::regclass AND contype='c'
                    AND pg_get_constraintdef(oid) LIKE '%code%'
            LOOP EXECUTE format('ALTER TABLE feature_flags DROP CONSTRAINT %I',constraint_name);
            END LOOP;
        END $$;
        ALTER TABLE feature_flags ADD CONSTRAINT ck_f9_installed_module CHECK(code IN
            ('subtasks','due_date_requests','kanban','timeline','analytics','evaluations','exports',
             'integrations','calendar','comments','dependencies','impediments','tags','custom_fields',
             'templates','recurrence','search','saved_views'));
        CREATE INDEX ix_f9_history_service ON task_history(actor_service_id,created_at,id);
        CREATE INDEX ix_f9_audit_service ON audit_events(actor_service_id,created_at,id);
        CREATE INDEX ix_f9_dependency_successor ON task_dependencies(successor_task_id,active,id);
        CREATE INDEX ix_f9_dependency_predecessor
            ON task_dependencies(predecessor_task_id,active,id);
        CREATE INDEX ix_f9_impediment_open ON task_impediments(task_id,closed_at,created_at,id);
        CREATE INDEX ix_f9_comments_task ON comments(task_id,created_at,id);
        CREATE INDEX ix_f9_comments_objective ON comments(objective_id,created_at,id);
        CREATE INDEX ix_f9_comments_parent ON comments(parent_comment_id,id);
        CREATE INDEX ix_f9_schedule_due ON recurrence_schedules(enabled,next_due_at,id);
        CREATE INDEX ix_f9_jobs_due ON job_runs(state,next_run_at,id);
        CREATE INDEX ix_f9_outbox_time ON transactional_outbox(created_at,id);
        CREATE INDEX ix_f9_fields_type ON custom_field_definitions
            (entity_type,department_id,active,created_at,id);
        CREATE INDEX ix_f9_options_order ON custom_field_options(definition_id,position,id);
        CREATE INDEX ix_f9_values_number ON custom_field_values(definition_id,number_value);
        CREATE INDEX ix_f9_values_date ON custom_field_values(definition_id,date_value);
        CREATE INDEX ix_f9_values_boolean ON custom_field_values(definition_id,boolean_value);
        CREATE INDEX ix_f9_values_text ON custom_field_values(definition_id,text_value);
        CREATE INDEX ix_f9_views_owner ON saved_views(owner_id,scope_kind,created_at,id);
        CREATE INDEX ix_f9_search_tasks ON tasks USING GIN
            (to_tsvector('spanish',title || ' ' || description));
        CREATE INDEX ix_f9_search_objectives ON objectives USING GIN
            (to_tsvector('spanish',title || ' ' || description));
        CREATE INDEX ix_f9_search_plans ON annual_plans USING GIN(to_tsvector('spanish',title));
        CREATE INDEX ix_f9_search_comments
            ON comment_revisions USING GIN(to_tsvector('spanish',body));
        CREATE FUNCTION protect_f9_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ DECLARE field text; BEGIN
            IF TG_OP IN ('DELETE','TRUNCATE') OR TG_ARGV[0]='append' THEN
                RAISE EXCEPTION 'F9_APPEND_ONLY' USING ERRCODE='23514';
            END IF;
            IF TG_OP='INSERT' THEN
                IF NEW.version<>1 THEN
                    RAISE EXCEPTION 'F9_INITIAL_VERSION' USING ERRCODE='23514';
                END IF;
            ELSE
                IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at
                    OR NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
                    RAISE EXCEPTION 'F9_VERSION_CONFLICT' USING ERRCODE='23514';
                END IF;
                FOREACH field IN ARRAY string_to_array(TG_ARGV[0],',') LOOP
                    IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(OLD)->field THEN
                        RAISE EXCEPTION 'F9_IMMUTABLE_IDENTITY' USING ERRCODE='23514';
                    END IF;
                END LOOP;
                IF (TG_TABLE_NAME='job_runs' AND to_jsonb(OLD)->>'state'<>'running')
                    OR (TG_TABLE_NAME='task_impediments'
                        AND to_jsonb(OLD)->>'closed_at' IS NOT NULL)
                    OR (TG_TABLE_NAME='comments'
                        AND to_jsonb(OLD)->>'annulled_at' IS NOT NULL) THEN
                    RAISE EXCEPTION 'F9_TERMINAL_RECORD' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE FUNCTION audit_f9_record() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM audit_events a
                WHERE a.entity_type=TG_TABLE_NAME AND a.entity_id=NEW.id
                    AND a.after_data->>'version'=NEW.version::text
                    AND a.created_at>=transaction_timestamp()) THEN
                RAISE EXCEPTION 'F9_AUDIT_REQUIRED' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
        END $$;
        CREATE FUNCTION guard_f9_dependency() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE plan_id uuid; department uuid; other_plan uuid; other_department uuid; BEGIN
            IF current_setting('transaction_isolation')<>'read committed' THEN
                RAISE EXCEPTION 'F9_DAG_REQUIRES_READ_COMMITTED' USING ERRCODE='23514';
            END IF;
            SELECT o.annual_plan_id,o.department_id INTO STRICT plan_id,department
                FROM tasks t JOIN objectives o ON o.id=t.objective_id
                WHERE t.id=NEW.predecessor_task_id;
            SELECT o.annual_plan_id,o.department_id INTO STRICT other_plan,other_department
                FROM tasks t JOIN objectives o ON o.id=t.objective_id
                WHERE t.id=NEW.successor_task_id;
            IF plan_id<>other_plan OR department<>other_department THEN
                RAISE EXCEPTION 'DEPENDENCY_SCOPE_MISMATCH' USING ERRCODE='23514';
            END IF;
            PERFORM 1 FROM annual_plans WHERE id=plan_id AND status='active' FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'PLAN_NOT_EDITABLE' USING ERRCODE='23514'; END IF;
            PERFORM 1 FROM tasks WHERE id IN (NEW.predecessor_task_id,NEW.successor_task_id)
                ORDER BY id FOR UPDATE;
            IF EXISTS(SELECT 1 FROM tasks
                WHERE id IN (NEW.predecessor_task_id,NEW.successor_task_id)
                    AND completed_at IS NOT NULL) THEN
                RAISE EXCEPTION 'TASK_COMPLETED' USING ERRCODE='23514';
            END IF;
            IF NEW.active AND EXISTS(WITH RECURSIVE reach(id) AS (
                SELECT NEW.successor_task_id UNION
                SELECT d.successor_task_id FROM task_dependencies d JOIN reach r
                    ON d.predecessor_task_id=r.id WHERE d.active AND d.id<>NEW.id
            ) SELECT 1 FROM reach WHERE id=NEW.predecessor_task_id) THEN
                RAISE EXCEPTION 'DEPENDENCY_CYCLE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_dependency BEFORE INSERT OR UPDATE ON task_dependencies
            FOR EACH ROW EXECUTE FUNCTION guard_f9_dependency();
        CREATE FUNCTION guard_f9_completion() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF OLD.completed_at IS NULL AND NEW.completed_at IS NOT NULL THEN
                PERFORM 1 FROM annual_plans p JOIN objectives o ON o.annual_plan_id=p.id
                    WHERE o.id=NEW.objective_id FOR UPDATE OF p;
                IF EXISTS(SELECT 1 FROM task_dependencies d JOIN tasks t
                    ON t.id=d.predecessor_task_id WHERE d.successor_task_id=NEW.id
                        AND d.active AND t.completed_at IS NULL) THEN
                    RAISE EXCEPTION 'PENDING_PREDECESSORS' USING ERRCODE='23514';
                END IF;
                IF EXISTS(SELECT 1 FROM task_impediments
                    WHERE task_id=NEW.id AND closed_at IS NULL) THEN
                    RAISE EXCEPTION 'OPEN_IMPEDIMENTS' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_completion BEFORE UPDATE ON tasks
            FOR EACH ROW EXECUTE FUNCTION guard_f9_completion();
        CREATE FUNCTION guard_f9_comment() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE parent comments; cursor_id uuid; depth integer:=1; closed boolean; BEGIN
            SELECT p.status='closed' OR coalesce(t.completed_at IS NOT NULL,false) INTO closed
                FROM objectives o JOIN annual_plans p ON p.id=o.annual_plan_id
                LEFT JOIN tasks t ON t.id=NEW.task_id
                WHERE o.id=coalesce(NEW.objective_id,t.objective_id);
            IF closed IS DISTINCT FROM false THEN
                RAISE EXCEPTION 'COMMENT_RESOURCE_CLOSED' USING ERRCODE='23514';
            END IF;
            cursor_id:=NEW.parent_comment_id;
            WHILE cursor_id IS NOT NULL LOOP
                SELECT * INTO STRICT parent FROM comments WHERE id=cursor_id;
                depth:=depth+1;
                IF depth>5 OR parent.id=NEW.id OR
                    ROW(parent.task_id,parent.objective_id) IS DISTINCT FROM
                    ROW(NEW.task_id,NEW.objective_id) THEN
                    RAISE EXCEPTION 'COMMENT_DEPTH_OR_RESOURCE' USING ERRCODE='23514';
                END IF;
                cursor_id:=parent.parent_comment_id;
            END LOOP;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_comment BEFORE INSERT OR UPDATE ON comments
            FOR EACH ROW EXECUTE FUNCTION guard_f9_comment();
        CREATE FUNCTION guard_f9_revision() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM comment_revisions r WHERE r.comment_id=NEW.id
                AND r.revision_no=NEW.current_revision
                AND r.annulment=(NEW.annulled_at IS NOT NULL)) THEN
                RAISE EXCEPTION 'COMMENT_REVISION_REQUIRED' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER z_f9_comment_revision AFTER INSERT OR UPDATE ON comments
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_f9_revision();
        CREATE FUNCTION guard_f9_typed_value() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE definition custom_field_definitions; department uuid; entity text; BEGIN
            PERFORM f9_resource_department(NEW.plan_id,NEW.objective_id,NEW.task_id);
            SELECT * INTO STRICT definition FROM custom_field_definitions
                WHERE id=NEW.definition_id FOR UPDATE;
            IF NEW.task_id IS NOT NULL THEN
                entity:='task'; SELECT o.department_id INTO department
                    FROM tasks t JOIN objectives o ON o.id=t.objective_id WHERE t.id=NEW.task_id;
            ELSIF NEW.objective_id IS NOT NULL THEN
                entity:='objective'; SELECT department_id INTO department FROM objectives
                    WHERE id=NEW.objective_id;
            ELSE entity:='plan'; department:=NULL; END IF;
            IF NOT definition.active OR entity<>definition.entity_type
                OR (definition.department_id IS NOT NULL
                    AND definition.department_id IS DISTINCT FROM department) THEN
                RAISE EXCEPTION 'CUSTOM_FIELD_SCOPE' USING ERRCODE='23514';
            END IF;
            IF num_nonnulls(NEW.text_value,NEW.number_value,NEW.date_value,
                NEW.boolean_value,NEW.option_id,NEW.option_ids)=0 THEN RETURN NEW; END IF;
            IF NOT (CASE definition.data_type
                WHEN 'text' THEN NEW.text_value IS NOT NULL AND length(btrim(NEW.text_value))>0
                    AND length(NEW.text_value) BETWEEN
                        coalesce((definition.constraints->>'min_length')::integer,0)
                        AND coalesce((definition.constraints->>'max_length')::integer,2000)
                WHEN 'url' THEN NEW.text_value IS NOT NULL
                    AND NEW.text_value~'^https://[^/?#[:space:]@]+([/?#]|$)'
                WHEN 'number' THEN NEW.number_value IS NOT NULL
                    AND NEW.number_value::text NOT IN ('NaN','Infinity','-Infinity')
                    AND (NOT definition.constraints ? 'min'
                        OR NEW.number_value>=(definition.constraints->>'min')::numeric)
                    AND (NOT definition.constraints ? 'max'
                        OR NEW.number_value<=(definition.constraints->>'max')::numeric)
                WHEN 'date' THEN NEW.date_value IS NOT NULL
                WHEN 'boolean' THEN NEW.boolean_value IS NOT NULL
                WHEN 'select' THEN EXISTS(SELECT 1 FROM custom_field_options
                    WHERE id=NEW.option_id AND definition_id=definition.id AND is_active)
                WHEN 'multi_select' THEN NEW.option_ids IS NOT NULL
                    AND cardinality(NEW.option_ids)=(SELECT count(DISTINCT id)
                        FROM custom_field_options WHERE id=ANY(NEW.option_ids)
                            AND definition_id=definition.id AND is_active)
                ELSE false END) THEN
                RAISE EXCEPTION 'CUSTOM_FIELD_TYPE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_typed_value BEFORE INSERT OR UPDATE ON custom_field_values
            FOR EACH ROW EXECUTE FUNCTION guard_f9_typed_value();
        REVOKE ALL ON FUNCTION protect_f9_record(),audit_f9_record(),guard_f9_dependency(),
            guard_f9_completion(),guard_f9_comment(),guard_f9_revision(),guard_f9_typed_value()
            FROM PUBLIC;
    """)
    for table in ("annual_plans", "objectives", "tasks"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN template_version_id UUID "
            "REFERENCES template_versions(id) ON DELETE RESTRICT"
        )
        op.execute(f"CREATE INDEX ix_f9_{table}_template ON {table}(template_version_id)")
    op.execute("""
        CREATE FUNCTION f9_resource_department(plan_key uuid,objective_key uuid,task_key uuid)
        RETURNS uuid LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE department uuid; current_plan uuid; plan_state text; finished timestamptz; BEGIN
            IF task_key IS NOT NULL THEN
                SELECT o.department_id,o.annual_plan_id,t.completed_at INTO STRICT
                    department,current_plan,finished FROM tasks t JOIN objectives o
                    ON o.id=t.objective_id WHERE t.id=task_key;
            ELSIF objective_key IS NOT NULL THEN
                SELECT department_id,annual_plan_id INTO STRICT department,current_plan
                    FROM objectives WHERE id=objective_key;
            ELSE current_plan:=plan_key; END IF;
            SELECT status INTO STRICT plan_state FROM annual_plans
                WHERE id=current_plan FOR UPDATE;
            IF task_key IS NOT NULL THEN
                PERFORM 1 FROM tasks WHERE id=task_key FOR UPDATE;
                SELECT completed_at INTO finished FROM tasks WHERE id=task_key;
            END IF;
            IF plan_state='closed' OR finished IS NOT NULL
                OR (task_key IS NOT NULL AND plan_state<>'active') THEN
                RAISE EXCEPTION 'F9_RESOURCE_CLOSED' USING ERRCODE='23514';
            END IF;
            RETURN department;
        END $$;
        CREATE FUNCTION guard_f9_tag() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE department uuid; tag tags; BEGIN
            department:=f9_resource_department(NEW.plan_id,NEW.objective_id,NEW.task_id);
            SELECT * INTO STRICT tag FROM tags WHERE id=NEW.tag_id FOR SHARE;
            IF NEW.active AND (NOT tag.is_active OR (tag.department_id IS NOT NULL
                AND tag.department_id IS DISTINCT FROM department)) THEN
                RAISE EXCEPTION 'TAG_NOT_APPLICABLE_OR_ACTIVE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_tag BEFORE INSERT OR UPDATE ON entity_tags
            FOR EACH ROW EXECUTE FUNCTION guard_f9_tag();
        CREATE FUNCTION guard_f9_principal() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF cardinality(NEW.department_ids)<>(SELECT count(DISTINCT id) FROM departments
                    WHERE id=ANY(NEW.department_ids) AND (NOT NEW.is_active OR is_active))
                OR cardinality(NEW.approved_scopes)<>(SELECT count(DISTINCT value)
                    FROM unnest(NEW.approved_scopes) value) THEN
                RAISE EXCEPTION 'RECURRENCE_SCOPE_NOT_APPROVED' USING ERRCODE='23514';
            END IF;
            IF TG_OP='UPDATE' THEN
                IF NEW.token_version<>OLD.token_version+1 THEN
                    RAISE EXCEPTION 'F9_PRINCIPAL_EPOCH_REQUIRED' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_principal BEFORE INSERT OR UPDATE ON service_principals
            FOR EACH ROW EXECUTE FUNCTION guard_f9_principal();
        CREATE FUNCTION guard_f9_schedule() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF TG_OP='INSERT' THEN
                IF NEW.enabled THEN
                    RAISE EXCEPTION 'RECURRENCE_CREATE_DISABLED' USING ERRCODE='23514';
                END IF;
            ELSIF EXISTS(SELECT 1 FROM recurrence_occurrences WHERE schedule_id=NEW.id) THEN
                IF (to_jsonb(NEW)-ARRAY['enabled','next_due_at','updated_at','version'])
                    IS DISTINCT FROM
                    (to_jsonb(OLD)-ARRAY['enabled','next_due_at','updated_at','version']) THEN
                    RAISE EXCEPTION 'RECURRENCE_USED_RULE_IMMUTABLE' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_schedule BEFORE INSERT OR UPDATE ON recurrence_schedules
            FOR EACH ROW EXECUTE FUNCTION guard_f9_schedule();
        CREATE FUNCTION guard_f9_impediment() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ DECLARE department uuid; BEGIN
            department:=f9_resource_department(NULL,NULL,NEW.task_id);
            IF TG_OP='INSERT' AND NOT EXISTS(SELECT 1 FROM users u JOIN tasks t ON t.id=NEW.task_id
                WHERE u.id=NEW.owner_user_id AND u.is_active AND u.department_id=department
                    AND (u.role IN ('admin','lider')
                        OR (u.role='colaborador' AND u.id=t.assignee_id))) THEN
                RAISE EXCEPTION 'INVALID_IMPEDIMENT_OWNER' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_impediment BEFORE INSERT OR UPDATE ON task_impediments
            FOR EACH ROW EXECUTE FUNCTION guard_f9_impediment();
        CREATE FUNCTION guard_f9_mention() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM comment_revisions r JOIN comments c ON c.id=r.comment_id
                LEFT JOIN tasks t ON t.id=c.task_id JOIN objectives o
                    ON o.id=coalesce(c.objective_id,t.objective_id)
                JOIN users u ON u.id=NEW.mentioned_user_id
                WHERE r.id=NEW.comment_revision_id AND u.is_active
                    AND (u.role IN ('admin','gerente')
                        OR (u.role='lider' AND u.department_id=o.department_id)
                        OR (u.role='colaborador' AND u.id=t.assignee_id))
                    AND strpos(r.body,'@'||u.display_name)>0) THEN
                RAISE EXCEPTION 'MENTION_NOT_VISIBLE_OR_LITERAL' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER a_f9_mention BEFORE INSERT ON comment_mentions
            FOR EACH ROW EXECUTE FUNCTION guard_f9_mention();
        CREATE FUNCTION guard_f9_required() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$
        DECLARE entity text; entity_key uuid; department uuid; stage uuid; creating boolean:=false;
                definition custom_field_definitions; BEGIN
            IF TG_TABLE_NAME='custom_field_values' THEN
                entity:=CASE WHEN NEW.task_id IS NOT NULL THEN 'task'
                    WHEN NEW.objective_id IS NOT NULL THEN 'objective' ELSE 'plan' END;
                entity_key:=coalesce(NEW.task_id,NEW.objective_id,NEW.plan_id);
            ELSE
                entity:=TG_ARGV[0]; entity_key:=NEW.id; creating:=TG_OP='INSERT';
                IF NOT creating AND (entity<>'task' OR
                    to_jsonb(NEW)->'stage_id' IS NOT DISTINCT FROM to_jsonb(OLD)->'stage_id') THEN
                    RETURN NULL;
                END IF;
            END IF;
            IF entity='task' THEN
                SELECT o.department_id,t.stage_id INTO department,stage FROM tasks t
                    JOIN objectives o ON o.id=t.objective_id WHERE t.id=entity_key;
            ELSIF entity='objective' THEN
                SELECT department_id INTO department FROM objectives WHERE id=entity_key;
            END IF;
            FOR definition IN SELECT * FROM custom_field_definitions d WHERE d.active
                AND d.entity_type=entity AND (d.department_id IS NULL OR d.department_id=department)
                AND ((creating AND d.required_on_create) OR stage=ANY(d.required_stage_ids)) LOOP
                IF NOT EXISTS(SELECT 1 FROM custom_field_values v
                    WHERE v.definition_id=definition.id
                    AND coalesce(v.task_id,v.objective_id,v.plan_id)=entity_key
                    AND num_nonnulls(v.text_value,v.number_value,v.date_value,v.boolean_value,
                        v.option_id,v.option_ids)=1) THEN
                    RAISE EXCEPTION 'CUSTOM_FIELD_REQUIRED' USING ERRCODE='23514';
                END IF;
            END LOOP;
            RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER z_f9_value_required AFTER INSERT OR UPDATE ON custom_field_values
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_f9_required();
        CREATE FUNCTION guard_f9_template_origin() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,public AS $$ BEGIN
            IF NEW.template_version_id IS DISTINCT FROM OLD.template_version_id THEN
                RAISE EXCEPTION 'F9_TEMPLATE_ORIGIN_IMMUTABLE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        REVOKE ALL ON FUNCTION f9_resource_department(uuid,uuid,uuid),guard_f9_tag(),
            guard_f9_principal(),guard_f9_schedule(),guard_f9_impediment(),guard_f9_mention(),
            guard_f9_required(),guard_f9_template_origin() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION f9_resource_department(uuid,uuid,uuid) TO ocote_runtime;
    """)
    for table, entity in (("annual_plans", "plan"), ("objectives", "objective"), ("tasks", "task")):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER z_f9_required AFTER INSERT OR UPDATE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION guard_f9_required('{entity}')"
        )
        op.execute(
            f"CREATE TRIGGER a_f9_template_origin BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION guard_f9_template_origin()"
        )
    for table in TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON {table} FROM ocote_runtime")
        if table in APPEND_ONLY:
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION protect_f9_record('append')"
            )
            privileges = "SELECT,INSERT"
        else:
            fields = IMMUTABLE[table]
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE INSERT OR UPDATE OR DELETE "
                f"ON {table} FOR EACH ROW EXECUTE FUNCTION protect_f9_record('{fields}')"
            )
            op.execute(
                f"CREATE CONSTRAINT TRIGGER z_f9_audit_{table} AFTER INSERT OR UPDATE "
                f"ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION audit_f9_record()"
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
                    AND k.table_name IN ('service_principals','job_runs','transactional_outbox',
                        'task_dependencies','task_impediments','templates','template_versions',
                        'recurrence_schedules','recurrence_occurrences','custom_field_definitions',
                        'custom_field_options','custom_field_values','tags','entity_tags',
                        'comments','comment_revisions','comment_mentions','saved_views')
            LOOP EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(%I,created_at,id)',
                'ix_f9_fk_'||column_record.table_name||'_'||column_record.column_name,
                column_record.table_name,column_record.column_name);
            END LOOP;
        END $$;
    """)


def downgrade():
    raise RuntimeError("F9 history requires approved fix-forward or isolated restore")
