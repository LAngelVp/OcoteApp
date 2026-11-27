from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.errors import CommandError
from app.core.tabular import pdf_report, xlsx_report
from app.models.bulk import ExportJob
from app.models.evaluations import EvaluationItem
from app.models.identity import SystemSetting
from app.services import bulk, enterprise, evaluations, exports
from app.services import operations as operation

COLUMNS = ("Tarea", "Departamento", "Responsable", "Etapa", "Compromiso original",
           "Compromiso vigente", "Cierre", "Avance", "Puntualidad")


def authorize(db, user):
    operation.permit(user, "admin", "gerente", "lider")
    enterprise.require_module(db, "executive_reports")
    enterprise.require_module(db, "evaluations")
    enterprise.require_module(db, "exports")
    return enterprise.policy(db)


def visible_final(db, user, identity):
    authorize(db, user)
    record = evaluations.visible(db, user, identity)
    if record.status != "final":
        raise CommandError(409, "EVALUATION_NOT_FINAL")
    return record


def report_view(record):
    return {field: getattr(record, field) for field in (
        "id", "created_at", "version", "final_evaluation_id", "department_id", "file_format",
        "snapshot_at", "calculation_version", "organization_timezone", "row_count", "byte_count",
        "result_hash", "expires_at",
    )}


def report_record(db, user, identity):
    authorize(db, user)
    query = select(ExportJob).where(ExportJob.id == identity)
    if user.role != "admin":
        query = query.where(ExportJob.requester_id == user.id)
    record = db.scalar(query)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    visible_final(db, user, record.final_evaluation_id)
    return record


def list_reports(db, user, *, limit, cursor=None):
    authorize(db, user)
    enterprise.require_page_size(db, limit)
    query = select(ExportJob)
    if user.role != "admin":
        query = query.where(ExportJob.requester_id == user.id)
    if user.role == "lider":
        query = query.where(ExportJob.department_id == user.department_id)
    if cursor:
        query = query.where(ExportJob.id > cursor)
    rows = list(db.scalars(query.order_by(ExportJob.id).limit(limit + 1)))
    return {"items": [report_view(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def nested(row, key, field):
    value = row.get(key)
    return value.get(field, "") if isinstance(value, dict) else ""


def sealed_rows(items):
    return [[row.get("title", ""), nested(row, "department", "name"),
             nested(row, "assignee", "display_name"), nested(row, "stage", "name"),
             row.get("original_due_date", ""), row.get("due_date", ""),
             row.get("completed_at", ""), row.get("progress_percent", ""),
             row.get("punctuality_status", "")] for row in items]


def report_context(record):
    return {
        "evaluation_id": str(record.id), "period_start": record.period_start.isoformat(),
        "period_end": record.period_end.isoformat(), "snapshot_at": record.snapshot_at.isoformat(),
        "calculation_version": record.calculation_version,
        "organization_timezone": record.organization_timezone, "summary": record.summary or "",
        "metrics": bulk.canonical(record.metrics).decode("ascii"),
    }


def create_report(db, user, body, request):
    policy = authorize(db, user)
    request.app.state.export_limiter.check(str(user.id), request.client.host if request.client
                                         else "local")
    evaluation = visible_final(db, user, body.evaluation_id)
    input_hash = bulk.digest({"evaluation": str(body.evaluation_id), "format": body.file_format})
    previous = bulk.existing_job(db, user, "export", body.idempotency_key)
    if previous:
        record = db.scalar(select(ExportJob).where(ExportJob.job_id == previous.id))
        if record is None or previous.input_hash != input_hash:
            raise CommandError(409, "IDEMPOTENCY_CONFLICT")
        return report_view(report_record(db, user, record.id))
    maximum = db.scalar(select(SystemSetting.value).where(SystemSetting.key == "export_max_rows"))
    if type(maximum) is not int or not 1 <= maximum <= 10000:
        raise CommandError(409, "CONFIGURATION_INCOMPLETE")
    items = list(db.scalars(select(EvaluationItem).where(
        EvaluationItem.evaluation_id == evaluation.id,
    ).order_by(EvaluationItem.task_id).limit(maximum + 1)))
    if len(items) > maximum:
        raise CommandError(413, "EXPORT_TOO_LARGE")
    renderer = {"pdf": pdf_report, "xlsx": xlsx_report}.get(body.file_format)
    if renderer is None:
        raise CommandError(422, "REPORT_FORMAT_INVALID")
    content = renderer(COLUMNS, sealed_rows([item.snapshot_data for item in items]),
                       report_context(evaluation), min(policy.export_max_bytes, 16777216))
    identity = uuid4()
    value = bulk.encrypt(db, request, "report_result", identity, 1, content)
    job = bulk.create_job(db, user, request, "export", body.idempotency_key, input_hash)
    record = ExportJob(
        id=identity, job_id=job.id, requester_id=user.id, final_evaluation_id=evaluation.id,
        department_id=evaluation.department_id, file_format=body.file_format,
        snapshot_at=evaluation.snapshot_at, calculation_version=evaluation.calculation_version,
        organization_timezone=evaluation.organization_timezone, row_count=len(items),
        byte_count=len(content), result_hash=bulk.digest(content),
        expires_at=operation.instant(db) + timedelta(hours=1),
        key_id=value.key_id, nonce=value.nonce, ciphertext=value.ciphertext,
    )
    db.add(record)
    db.flush([record])
    bulk.event(db, request, user, record, "executive_report_created",
               row_count=len(items), result_hash=record.result_hash, reason=body.reason)
    bulk.finish_job(db, user, request, job)
    db.flush()
    return report_view(record)


def download_report(db, user, identity, request):
    policy = authorize(db, user)
    record = report_record(db, user, identity)
    if record.expires_at <= operation.instant(db):
        raise CommandError(409, "REPORT_EXPIRED")
    maximum = db.scalar(select(SystemSetting.value).where(SystemSetting.key == "export_max_rows"))
    if type(maximum) is not int or not 1 <= maximum <= 10000:
        raise CommandError(409, "CONFIGURATION_INCOMPLETE")
    if record.row_count > maximum or record.byte_count > min(policy.export_max_bytes, 16777216):
        raise CommandError(413, "EXPORT_TOO_LARGE")
    content = bulk.decrypt(db, request, record)
    if len(content) != record.byte_count or bulk.digest(content) != record.result_hash:
        raise CommandError(503, "REPORT_INTEGRITY_FAILURE")
    bulk.event(db, request, user, record, "executive_report_downloaded",
               result_hash=record.result_hash, byte_count=record.byte_count)
    db.flush()
    context = {"report_id": str(record.id), "evaluation_id": str(record.final_evaluation_id),
               "result_hash": record.result_hash}
    file_format = record.file_format
    response = exports.ExportResponse(
        content, media_type=("application/pdf" if file_format == "pdf" else
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        filename="ocote-report-" + str(record.id) + "." + file_format,
        failure=lambda: exports.log_export(request, user, "executive_report_failed", context,
                                          outcome="failure"),
    )
    response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    return response