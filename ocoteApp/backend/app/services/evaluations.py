from sqlalchemy import delete, select

from app.core.errors import CommandError
from app.models.evaluations import Evaluation, EvaluationItem
from app.models.identity import Department, HorizonType
from app.models.operations import AnnualPlan
from app.schemas.analytics import AnalyticsFilters
from app.services import analytics
from app.services import operations as operation
from app.services.administration import check_version


def scope(query, user):
    operation.permit(user, "admin", "gerente", "lider")
    if user.role == "lider":
        query = query.where(
            Evaluation.department_id == user.department_id, Evaluation.status == "final"
        )
    return query


def visible(db, user, identity):
    record = db.scalar(scope(select(Evaluation).where(Evaluation.id == identity), user))
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def view(db, record, *, limit=5, cursor=None):
    reason = (
        "final"
        if record.status == "final"
        else "period_open"
        if record.period_end >= operation.instant(db).astimezone(operation.timezone(db)).date()
        else "no_data"
        if not record.metrics["task_count"]
        else None
    )
    query = select(EvaluationItem).where(EvaluationItem.evaluation_id == record.id)
    if cursor:
        query = query.where(EvaluationItem.task_id > cursor)
    items = list(db.scalars(query.order_by(EvaluationItem.task_id).limit(limit + 1)))
    return {
        **operation.state(record),
        "can_finalize": reason is None,
        "finalization_reason": reason,
        "items": [item.snapshot_data for item in items[:limit]],
        "next_cursor": items[limit - 1].task_id if len(items) > limit else None,
    }


def capture(db, user, plan, department, start, end):
    if not plan.start_date <= start <= end <= plan.due_date:
        raise CommandError(422, "INVALID_INTERVAL")
    filters = AnalyticsFilters(
        annual_plan_id=plan.id, department_id=department.id, period_start=start, period_end=end
    )
    rows, moment, zone = analytics.collect(db, user, filters)
    label = db.scalar(select(HorizonType.name).where(HorizonType.code == plan.horizon_type))
    metrics = {
        **analytics.summarize(rows),
        "annual_plan": {
            **{
                key: operation.state(plan)[key]
                for key in ("id", "title", "start_date", "due_date", "horizon_type")
            },
            "horizon_name": label,
        },
        "department": {"id": str(department.id), "name": department.name},
        "evaluator": {"id": str(user.id), "display_name": user.display_name},
    }
    return rows, moment, zone, metrics


def replace_items(db, record, rows):
    db.execute(delete(EvaluationItem).where(EvaluationItem.evaluation_id == record.id))
    db.add_all(
        EvaluationItem(evaluation_id=record.id, task_id=row["id"], snapshot_data=row)
        for row in rows
    )
    db.flush()


def create(db, user, body, request):
    operation.permit(user, "admin", "gerente")
    operation.configuration(db)
    plan = operation.visible(db, AnnualPlan, body.annual_plan_id, user)
    department = db.get(Department, body.department_id)
    if department is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    operation.lock_context(db, user, plan=plan, department=department.id)
    rows, moment, zone, metrics = capture(
        db, user, plan, department, body.period_start, body.period_end
    )
    record = Evaluation(
        **body.model_dump(),
        evaluator_id=user.id,
        snapshot_at=moment,
        metrics=metrics,
        calculation_version=analytics.CALCULATION_VERSION,
        organization_timezone=str(zone),
    )
    db.add(record)
    db.flush()
    replace_items(db, record, rows)
    operation.administrative_event(db, request, user, record, {}, "evaluation_created")
    db.flush()
    return view(db, record)


def update(db, user, identity, body, request, *, finalize=False):
    operation.permit(user, "admin", "gerente")
    record = visible(db, user, identity)
    plan = db.get(AnnualPlan, record.annual_plan_id)
    operation.lock_context(db, user, plan=plan, department=record.department_id)
    db.refresh(record, with_for_update=True)
    check_version(record, body.expected_version)
    if record.status != "draft":
        raise CommandError(409, "EVALUATION_FINAL")
    department = db.get(Department, record.department_id)
    rows, moment, zone, metrics = capture(
        db, user, plan, department, record.period_start, record.period_end
    )
    if finalize and (record.period_end >= moment.astimezone(zone).date() or not rows):
        raise CommandError(409, "EVALUATION_NOT_FINALIZABLE")
    before = operation.state(record)
    replace_items(db, record, rows)
    record.metrics, record.snapshot_at = metrics, moment
    record.calculation_version, record.organization_timezone = (
        analytics.CALCULATION_VERSION,
        str(zone),
    )
    record.evaluator_id = user.id
    if finalize:
        record.status, record.summary, record.finalized_at = "final", body.summary, moment
    operation.bump(db, record)
    db.flush()
    operation.administrative_event(
        db,
        request,
        user,
        record,
        before,
        "evaluation_finalized" if finalize else "evaluation_recalculated",
    )
    db.flush()
    return view(db, record)
