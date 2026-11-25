"""F3 operational core, without business seeds."""

from alembic import op

revision = "20261124_0003"
down_revision = "20261124_0002"
branch_labels = None
depends_on = None

MUTABLE = """
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
CHECK(updated_at >= created_at)
"""


def upgrade():
    op.execute(f"""
        CREATE TABLE annual_plans ({MUTABLE},
            title VARCHAR(200) NOT NULL CHECK(btrim(title) <> ''),
            horizon_type VARCHAR(12) NOT NULL REFERENCES horizon_types(code) ON DELETE RESTRICT,
            start_date DATE NOT NULL, due_date DATE NOT NULL CHECK(start_date <= due_date),
            status VARCHAR(12) NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','active','closed')),
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            activated_at TIMESTAMPTZ, closed_at TIMESTAMPTZ,
            CHECK((status='draft' AND activated_at IS NULL AND closed_at IS NULL) OR
                  (status='active' AND activated_at IS NOT NULL AND closed_at IS NULL) OR
                  (status='closed' AND activated_at IS NOT NULL AND closed_at >= activated_at
                   AND closed_at IS NOT NULL))
        );
        CREATE TABLE objectives ({MUTABLE},
            annual_plan_id UUID NOT NULL REFERENCES annual_plans(id) ON DELETE RESTRICT,
            department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
            title VARCHAR(200) NOT NULL CHECK(btrim(title) <> ''),
            description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 10000),
            horizon_type VARCHAR(12) NOT NULL REFERENCES horizon_types(code) ON DELETE RESTRICT,
            start_date DATE NOT NULL, due_date DATE NOT NULL CHECK(start_date <= due_date),
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
        );
        CREATE TABLE tasks ({MUTABLE},
            objective_id UUID NOT NULL REFERENCES objectives(id) ON DELETE RESTRICT,
            assignee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            stage_id UUID NOT NULL REFERENCES workflow_stages(id) ON DELETE RESTRICT,
            priority_id UUID NOT NULL REFERENCES priorities(id) ON DELETE RESTRICT,
            title VARCHAR(200) NOT NULL CHECK(btrim(title) <> ''),
            description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 10000),
            start_date DATE NOT NULL, original_due_date DATE NOT NULL, due_date DATE NOT NULL,
            completed_at TIMESTAMPTZ,
            CHECK(start_date <= original_due_date AND start_date <= due_date)
        );
        CREATE TABLE subtasks ({MUTABLE},
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            title VARCHAR(200) NOT NULL CHECK(btrim(title) <> ''),
            start_date DATE NOT NULL, original_due_date DATE NOT NULL, due_date DATE NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed')),
            completed_at TIMESTAMPTZ,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            CHECK(start_date <= original_due_date AND start_date <= due_date),
            CHECK((status='completed') = (completed_at IS NOT NULL)), UNIQUE(id,task_id)
        );
        CREATE TABLE task_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            subtask_id UUID,
            actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            event_type VARCHAR(40) NOT NULL CHECK(event_type IN
                ('task_created','task_updated','stage_changed','assignment_changed',
                 'due_date_changed','schedule_changed','subtask_created','subtask_updated',
                 'subtask_completed','subtask_due_date_changed','subtask_schedule_changed',
                 'evidence_added')),
            before_data JSONB NOT NULL CHECK(jsonb_typeof(before_data)='object'),
            after_data JSONB NOT NULL CHECK(jsonb_typeof(after_data)='object'),
            reason TEXT CHECK(reason IS NULL OR length(btrim(reason)) BETWEEN 10 AND 2000),
            request_id UUID NOT NULL,
            FOREIGN KEY(subtask_id,task_id) REFERENCES subtasks(id,task_id) ON DELETE RESTRICT
        );
        CREATE TABLE due_date_requests ({MUTABLE},
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT, subtask_id UUID,
            requested_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            proposed_due_date DATE NOT NULL, previous_due_date DATE NOT NULL,
            task_version_at_request INTEGER NOT NULL CHECK(task_version_at_request > 0),
            subtask_version_at_request INTEGER CHECK(subtask_version_at_request > 0),
            reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 10 AND 2000),
            status VARCHAR(12) NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected','cancelled')),
            decided_by UUID REFERENCES users(id) ON DELETE RESTRICT,
            decision_reason TEXT CHECK(length(btrim(decision_reason)) BETWEEN 10 AND 2000),
            decided_at TIMESTAMPTZ,
            CHECK((subtask_id IS NULL) = (subtask_version_at_request IS NULL)),
            CHECK(proposed_due_date <> previous_due_date),
            CHECK((status='pending' AND decided_by IS NULL AND decision_reason IS NULL
                   AND decided_at IS NULL) OR
                  (status<>'pending' AND decided_by IS NOT NULL AND decision_reason IS NOT NULL
                   AND decided_at IS NOT NULL AND decided_at >= created_at)),
            CHECK(status <> 'approved' OR decided_by <> requested_by),
            FOREIGN KEY(subtask_id,task_id) REFERENCES subtasks(id,task_id) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX uq_due_request_task_pending ON due_date_requests(task_id)
            WHERE status='pending' AND subtask_id IS NULL;
        CREATE UNIQUE INDEX uq_due_request_subtask_pending ON due_date_requests(subtask_id)
            WHERE status='pending' AND subtask_id IS NOT NULL;
        CREATE INDEX ix_plans_period ON annual_plans(start_date,due_date,status);
        CREATE INDEX ix_objectives_scope ON objectives(annual_plan_id,department_id,created_at,id);
        CREATE INDEX ix_objectives_period ON objectives(annual_plan_id,start_date,due_date);
        CREATE INDEX ix_tasks_objective ON tasks(objective_id,stage_id,created_at,id);
        CREATE INDEX ix_tasks_assignee ON tasks(assignee_id,stage_id,created_at,id);
        CREATE INDEX ix_tasks_stage ON tasks(stage_id,created_at,id);
        CREATE INDEX ix_tasks_baseline ON tasks(original_due_date,objective_id);
        CREATE INDEX ix_tasks_due ON tasks(due_date) WHERE completed_at IS NULL;
        CREATE INDEX ix_tasks_priority ON tasks(priority_id,created_at,id);
        CREATE INDEX ix_subtasks_parent ON subtasks(task_id,status,created_at,id);
        CREATE INDEX ix_history_task ON task_history(task_id,created_at,id);
        CREATE INDEX ix_history_subtask ON task_history(subtask_id,created_at,id)
            WHERE subtask_id IS NOT NULL;
        CREATE INDEX ix_history_request ON task_history(request_id);
        CREATE INDEX ix_requests_status ON due_date_requests(status,created_at,id);
        CREATE INDEX ix_requests_task ON due_date_requests(task_id,created_at,id);
        CREATE INDEX ix_requests_actor ON due_date_requests(requested_by,created_at,id);
    """)
    op.execute("""
        CREATE FUNCTION protect_f3_core() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
            IF TG_OP='DELETE' OR TG_TABLE_NAME='task_history' THEN
                RAISE EXCEPTION 'Operational history cannot be removed or edited'
                    USING ERRCODE='23514';
            END IF;
            IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at OR
               NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
                RAISE EXCEPTION 'Invalid identity or version' USING ERRCODE='23514';
            END IF;
            IF TG_TABLE_NAME IN ('tasks','subtasks') THEN
                IF NEW.original_due_date<>OLD.original_due_date OR
                   OLD.completed_at IS NOT NULL OR NEW.created_by<>OLD.created_by THEN
                    RAISE EXCEPTION 'Original dates and completed work are immutable'
                        USING ERRCODE='23514';
                END IF;
                IF TG_TABLE_NAME='tasks' THEN
                    IF NEW.objective_id<>OLD.objective_id THEN
                        RAISE EXCEPTION 'Immutable parent' USING ERRCODE='23514';
                    END IF;
                ELSIF NEW.task_id<>OLD.task_id THEN
                    RAISE EXCEPTION 'Immutable parent' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='annual_plans' THEN
                IF OLD.status='closed' OR NEW.created_by<>OLD.created_by OR
                   NOT (NEW.status=OLD.status OR (OLD.status='draft' AND NEW.status='active')
                        OR (OLD.status='active' AND NEW.status='closed')) OR
                   (OLD.activated_at IS NOT NULL AND NEW.activated_at<>OLD.activated_at) THEN
                    RAISE EXCEPTION 'Invalid plan transition' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='objectives' THEN
                IF NEW.annual_plan_id<>OLD.annual_plan_id OR
                   NEW.department_id<>OLD.department_id OR NEW.created_by<>OLD.created_by THEN
                    RAISE EXCEPTION 'Immutable objective parent' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='due_date_requests' THEN
                IF OLD.status<>'pending' OR NEW.status='pending' OR
                   (to_jsonb(NEW)-ARRAY['updated_at','version','status','decided_by',
                       'decision_reason','decided_at']) IS DISTINCT FROM
                   (to_jsonb(OLD)-ARRAY['updated_at','version','status','decided_by',
                       'decision_reason','decided_at']) THEN
                    RAISE EXCEPTION 'Immutable request or terminal decision' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE FUNCTION copy_f3_original_date() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
            IF NEW.original_due_date<>NEW.due_date THEN
                RAISE EXCEPTION 'Original must equal initial commitment' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$;
        REVOKE ALL ON FUNCTION protect_f3_core(),copy_f3_original_date() FROM PUBLIC;
    """)
    for table in (
        "annual_plans",
        "objectives",
        "tasks",
        "subtasks",
        "due_date_requests",
        "task_history",
    ):
        op.execute(
            f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION protect_f3_core()"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        privileges = "SELECT,INSERT" if table == "task_history" else "SELECT,INSERT,UPDATE"
        op.execute(f"GRANT {privileges} ON {table} TO ocote_runtime")
    for table in ("tasks", "subtasks"):
        op.execute(
            f"CREATE TRIGGER original_{table} BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION copy_f3_original_date()"
        )


def downgrade():
    raise RuntimeError(
        "Operational originals and history require approved fix-forward or isolated restore"
    )
