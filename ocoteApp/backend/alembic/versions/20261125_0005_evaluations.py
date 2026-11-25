"""F6 evaluation snapshots and internal export audit, without seeds."""

from alembic import op

revision = "20261125_0005"
down_revision = "20261124_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
        CREATE TABLE evaluations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>0 AND updated_at>=created_at),
            annual_plan_id UUID NOT NULL REFERENCES annual_plans(id) ON DELETE RESTRICT,
            department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
            evaluator_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            period_start DATE NOT NULL, period_end DATE NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','final')),
            snapshot_at TIMESTAMPTZ NOT NULL,
            metrics JSONB NOT NULL CHECK(jsonb_typeof(metrics)='object'),
            calculation_version VARCHAR(20) NOT NULL CHECK(length(calculation_version)>0),
            organization_timezone VARCHAR(100) NOT NULL CHECK(length(organization_timezone)>0),
            summary TEXT, finalized_at TIMESTAMPTZ,
            CHECK(period_start<=period_end),
            CHECK((status='final')=(finalized_at IS NOT NULL)),
            CHECK(status<>'final' OR length(btrim(summary)) BETWEEN 10 AND 4000),
            UNIQUE(annual_plan_id,department_id,period_start,period_end),
            CONSTRAINT ex_evaluations_period EXCLUDE USING gist (
                annual_plan_id WITH =, department_id WITH =,
                daterange(period_start,period_end,'[]') WITH &&
            )
        );
        CREATE INDEX ix_evaluations_department ON evaluations(department_id,period_end,status);
        CREATE TABLE evaluation_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            evaluation_id UUID NOT NULL REFERENCES evaluations(id) ON DELETE RESTRICT,
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            snapshot_data JSONB NOT NULL CHECK(jsonb_typeof(snapshot_data)='object'),
            CHECK(snapshot_data->>'id'=task_id::text),
            UNIQUE(evaluation_id,task_id)
        );
        CREATE FUNCTION protect_f6_evaluation() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
            IF TG_OP IN ('TRUNCATE','DELETE') THEN
                RAISE EXCEPTION 'Evaluations cannot be discarded' USING ERRCODE='23514';
            END IF;
            IF TG_OP='UPDATE' THEN
                IF OLD.status='final' OR NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at
                   OR NEW.annual_plan_id<>OLD.annual_plan_id
                   OR NEW.department_id<>OLD.department_id
                   OR NEW.period_start<>OLD.period_start OR NEW.period_end<>OLD.period_end
                   OR NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
                    RAISE EXCEPTION 'Immutable evaluation or invalid version' USING ERRCODE='23514';
                END IF;
            ELSIF NEW.status<>'draft' OR NEW.version<>1 THEN
                RAISE EXCEPTION 'Evaluation must start as draft' USING ERRCODE='23514';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM annual_plans WHERE id=NEW.annual_plan_id
                           AND start_date<=NEW.period_start AND due_date>=NEW.period_end) THEN
                RAISE EXCEPTION 'Evaluation outside plan' USING ERRCODE='23514';
            END IF;
            IF NEW.status='final' AND (
                NEW.summary IS NULL OR length(btrim(NEW.summary)) NOT BETWEEN 10 AND 4000
                OR NEW.period_end >=
                    (clock_timestamp() AT TIME ZONE NEW.organization_timezone)::date
                OR (SELECT count(*) FROM evaluation_items WHERE evaluation_id=NEW.id)=0
                OR (SELECT count(*) FROM evaluation_items WHERE evaluation_id=NEW.id)
                    IS DISTINCT FROM (NEW.metrics->>'task_count')::bigint
            ) THEN
                RAISE EXCEPTION 'Invalid evaluation finalization' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE FUNCTION protect_f6_item() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        DECLARE current_status text;
        BEGIN
            IF TG_OP IN ('TRUNCATE','UPDATE') THEN
                RAISE EXCEPTION 'Snapshot items cannot be updated/truncated' USING ERRCODE='23514';
            END IF;
            SELECT status INTO current_status FROM evaluations
                WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.evaluation_id ELSE NEW.evaluation_id END
                FOR UPDATE;
            IF current_status IS DISTINCT FROM 'draft' THEN
                RAISE EXCEPTION 'Final snapshot is immutable' USING ERRCODE='23514';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER evaluation_protected BEFORE INSERT OR UPDATE OR DELETE ON evaluations
            FOR EACH ROW EXECUTE FUNCTION protect_f6_evaluation();
        CREATE TRIGGER evaluation_no_truncate BEFORE TRUNCATE ON evaluations
            FOR EACH STATEMENT EXECUTE FUNCTION protect_f6_evaluation();
        CREATE TRIGGER evaluation_item_protected
            BEFORE INSERT OR UPDATE OR DELETE ON evaluation_items
            FOR EACH ROW EXECUTE FUNCTION protect_f6_item();
        CREATE TRIGGER evaluation_item_no_truncate BEFORE TRUNCATE ON evaluation_items
            FOR EACH STATEMENT EXECUTE FUNCTION protect_f6_item();
        ALTER TABLE audit_events DROP CONSTRAINT audit_events_event_type_check;
        ALTER TABLE audit_events ADD CONSTRAINT audit_events_event_type_check CHECK(event_type IN
            ('bootstrap_admin','login_success','login_failed','session_refreshed','refresh_reuse',
             'logout','password_changed','administration_changed','security_denied',
             'export_requested','export_prepared','export_failed','export_denied'));
        REVOKE ALL ON evaluations,evaluation_items FROM PUBLIC;
        REVOKE ALL ON FUNCTION protect_f6_evaluation(),protect_f6_item() FROM PUBLIC;
        GRANT SELECT,INSERT,UPDATE ON evaluations TO ocote_runtime;
        GRANT SELECT,INSERT,DELETE ON evaluation_items TO ocote_runtime;
    """)


def downgrade():
    raise RuntimeError("Final snapshots cannot be discarded; use authorized isolated recovery")
