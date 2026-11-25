import csv
import io
import json
import re

from anyio import CancelScope, to_thread
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from starlette.responses import Response

from app.core.errors import CommandError
from app.models.evaluations import EvaluationItem
from app.models.identity import SystemSetting
from app.schemas.analytics import AnalyticsFilters
from app.services import analytics, evaluations
from app.services import operations as operation
from app.services.identity import audit

MAX_BYTES = 16 * 1024 * 1024
CSV_FIELDS = (
    "schema_version",
    "generated_at",
    "snapshot_at",
    "organization_timezone",
    "calculation_version",
    "filters",
    "scope",
    "row_count",
    "evaluation_id",
    "summary",
    "metrics",
    "id",
    "title",
    "annual_plan",
    "department",
    "assignee",
    "stage",
    "priority",
    "horizon",
    "start_date",
    "original_due_date",
    "due_date",
    "completed_at",
    "progress_percent",
    "punctuality_status",
    "baseline_punctuality_status",
    "delay_days",
    "baseline_delay_days",
    "due_date_delta_days",
    "due_date_change_count",
    "version",
)


def neutralize(value):
    if not isinstance(value, str):
        return value
    prefix = re.match(r"^[\s\x00-\x1f\x7f]*", value).group()
    if value[len(prefix) :].startswith(("=", "+", "-", "@")) or any(
        char in prefix for char in "\t\r\n"
    ):
        return "'" + value
    return value


def encode_csv(rows, context):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\r\n"
    )
    writer.writeheader()
    base = {
        key: json.dumps(context[key], sort_keys=True, ensure_ascii=True)
        if isinstance(context.get(key), dict)
        else context.get(key, "")
        for key in CSV_FIELDS[:11]
    }
    for row in rows:
        values = {**base, **{key: row.get(key, "") for key in CSV_FIELDS[11:]}}
        values.update(
            annual_plan=row.get("annual_plan", {}).get("title", ""),
            department=row.get("department", {}).get("name", ""),
            assignee=row.get("assignee", {}).get("display_name", ""),
            stage=row.get("stage", {}).get("name", ""),
            priority=row.get("priority", {}).get("name", ""),
            horizon=row.get("objective", {}).get("horizon_type", ""),
        )
        writer.writerow({key: neutralize(value) for key, value in values.items()})
    return stream.getvalue().encode("utf-8")


def log_export(request, user, event, context, *, outcome="success"):
    with request.app.state.session_factory.begin() as db:
        audit(
            db,
            request,
            event,
            actor=user.id,
            entity="export",
            after=jsonable_encoder(context),
            outcome=outcome,
        )


class ExportResponse(Response):
    def __init__(self, content, *, media_type, filename, failure):
        super().__init__(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
        self.failure = failure

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        except BaseException:
            with CancelScope(shield=True):
                await to_thread.run_sync(self.failure)
            raise


def prepare(db, user, body, request, *, evaluation_id=None):
    context = {"kind": "evaluation" if evaluation_id else "tasks", "format": body.format}
    context["filters"] = body.model_dump(mode="json", exclude_none=True, exclude={"format"})
    if evaluation_id:
        context["evaluation_id"] = str(evaluation_id)
    try:
        operation.permit(user, "admin", "gerente", "lider")
    except CommandError:
        log_export(request, user, "export_denied", context, outcome="denied")
        raise
    try:
        request.app.state.export_limiter.check(
            str(user.id), request.client.host if request.client else "local"
        )
    except CommandError:
        log_export(request, user, "export_denied", context, outcome="denied")
        raise
    log_export(request, user, "export_requested", context)
    try:
        maximum = db.scalar(
            select(SystemSetting.value).where(SystemSetting.key == "export_max_rows")
        )
        if type(maximum) is not int or not 1 <= maximum <= 10000:
            raise CommandError(409, "CONFIGURATION_INCOMPLETE")
        if evaluation_id:
            record = evaluations.visible(db, user, evaluation_id)
            if record.status != "final":
                raise CommandError(409, "EVALUATION_NOT_FINAL")
            items = list(
                db.scalars(
                    select(EvaluationItem)
                    .where(EvaluationItem.evaluation_id == record.id)
                    .order_by(EvaluationItem.task_id)
                    .limit(maximum + 1)
                )
            )
            if len(items) > maximum:
                raise CommandError(413, "EXPORT_TOO_LARGE")
            rows = [item.snapshot_data for item in items]
            filters = AnalyticsFilters(
                annual_plan_id=record.annual_plan_id,
                department_id=record.department_id,
                period_start=record.period_start,
                period_end=record.period_end,
            )
            context.update(
                analytics.metadata(user, filters, record.snapshot_at, record.organization_timezone),
                evaluation_id=str(record.id),
                summary=record.summary,
                metrics=record.metrics,
                calculation_version=record.calculation_version,
            )
        else:
            rows, moment, zone = analytics.collect(db, user, body, maximum=maximum)
            context.update(analytics.metadata(user, body, moment, zone))
        context.update(generated_at=operation.instant(db), row_count=len(rows))
        encoded = jsonable_encoder(context)
        content = (
            json.dumps({**encoded, "items": rows}, ensure_ascii=True, allow_nan=False).encode(
                "utf-8"
            )
            if body.format == "json"
            else encode_csv(rows, encoded)
        )
        if len(content) > MAX_BYTES:
            raise CommandError(413, "EXPORT_TOO_LARGE")
    except Exception as error:
        log_export(
            request,
            user,
            "export_failed",
            {key: value for key, value in context.items() if key not in {"summary", "metrics"}},
            outcome="failure",
        )
        if isinstance(error, CommandError) and error.code == "COHORT_TOO_LARGE":
            raise CommandError(413, "EXPORT_TOO_LARGE") from None
        raise
    audit_context = {
        key: value for key, value in context.items() if key not in {"summary", "metrics"}
    }
    log_export(request, user, "export_prepared", audit_context)
    return ExportResponse(
        content,
        media_type="application/json" if body.format == "json" else "text/csv",
        filename="ocote-" + context["kind"] + "." + body.format,
        failure=lambda: log_export(
            request,
            user,
            "export_failed",
            {**audit_context, "reason": "transport_interrupted"},
            outcome="failure",
        ),
    )
