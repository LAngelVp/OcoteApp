import base64
import binascii
import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.errors import CommandError
from app.core.tabular import ImportLimits, parse_table
from app.core.vault import EncryptedValue
from app.models.bulk import ImportJob, ImportRow
from app.models.collaboration import CustomFieldDefinition, CustomFieldOption, JobRun, Tag
from app.models.enterprise import FeatureFlag, SecurityPolicy
from app.models.identity import (
    Department,
    HorizonType,
    Priority,
    SystemSetting,
    User,
    WorkflowStage,
)
from app.models.operations import AnnualPlan, Objective
from app.models.platform import SecretKeyVersion
from app.schemas.operations import ObjectiveCreate, PlanCreate, TaskCreate
from app.services import collaboration, enterprise, platform
from app.services import operations as operation
from app.services.administration import check_version
from app.services.identity import audit

SCHEMAS = {"plan": PlanCreate, "objective": ObjectiveCreate, "task": TaskCreate}
CREATORS = {"plan": operation.create_plan, "objective": operation.create_objective,
            "task": operation.create_task}
MAPPING_FIELDS = {
    "plan": {"title", "start_date", "due_date", "horizon_type", "custom_fields", "tag_ids"},
    "objective": {"title", "description", "annual_plan_id", "department_id", "start_date",
                  "due_date", "horizon_type", "custom_fields", "tag_ids"},
    "task": {"title", "description", "objective_id", "assignee_id", "priority_id",
             "start_date", "due_date", "custom_fields", "tag_ids"},
}


def canonical(value):
    return json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def authorize_import(db, user, entity_type):
    enterprise.require_module(db, "imports")
    if entity_type not in SCHEMAS:
        raise CommandError(422, "IMPORT_ENTITY_INVALID")
    operation.permit(user, "admin", "lider" if entity_type == "task" else "gerente")
    return enterprise.policy(db)


def event(db, request, user, record, name, **details):
    audit(db, request, name, actor=user.id, entity=record.__tablename__, entity_id=record.id,
          after={"version": getattr(record, "version", 1), **jsonable_encoder(details)})


def payload_key(db, request, purpose):
    crypt = platform.vault(db, request)
    key = db.scalar(select(SecretKeyVersion).where(SecretKeyVersion.purpose == purpose)
                    .order_by(SecretKeyVersion.epoch.desc()).limit(1))
    if key is None:
        key = platform.new_key(db, crypt, purpose, 1)
    return crypt, key


def encrypt(db, request, purpose, owner_id, version, content):
    crypt, key = payload_key(db, request, purpose)
    return crypt.encrypt_payload(platform.wrapped(key), owner_id, version, content)


def decrypt(db, request, record, *, version=1):
    key = db.get(SecretKeyVersion, record.key_id)
    if key is None:
        raise CommandError(503, "VAULT_UNAVAILABLE")
    return platform.vault(db, request).decrypt_payload(platform.wrapped(key), EncryptedValue(
        key.id, record.id, version, record.nonce, record.ciphertext,
    ))


def create_job(db, user, request, kind, key, input_hash, *, principal=None, revision=None,
               payload=None):
    job = JobRun(id=uuid4(), kind=kind, owner_user_id=user.id,
                 service_principal_id=principal, configuration_revision_id=revision,
                 request_id=UUID(request.state.request_id), idempotency_key=key,
                 input_hash=input_hash, operation_payload=payload, state="running", attempt=1)
    db.add(job)
    db.flush([job])
    event(db, request, user, job, "f12_job_created", kind=kind)
    return job


def finish_job(db, user, request, job):
    if job.state != "running":
        raise CommandError(409, "JOB_TERMINAL")
    operation.bump(db, job)
    job.state = "succeeded"
    event(db, request, user, job, "f12_job_updated", state=job.state)


def existing_job(db, user, kind, key):
    return db.scalar(select(JobRun).where(JobRun.kind == kind, JobRun.owner_user_id == user.id,
                                         JobRun.idempotency_key == key))


def import_view(record):
    return {field: getattr(record, field) for field in (
        "id", "created_at", "updated_at", "version", "entity_type", "file_format",
        "file_hash", "file_size", "headers", "mapping", "state", "row_count", "error_count",
        "preview_attempts", "config_hash", "preview_hash", "expires_at", "result_ids",
    )}


def import_record(db, user, identity, *, lock=False):
    query = select(ImportJob).where(ImportJob.id == identity)
    if user.role != "admin":
        query = query.where(ImportJob.actor_id == user.id)
    record = db.scalar(query.with_for_update() if lock else query)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    authorize_import(db, user, record.entity_type)
    if user.role == "lider" and record.department_id != user.department_id:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def list_imports(db, user, *, limit, cursor=None):
    operation.permit(user, "admin", "gerente", "lider")
    enterprise.require_module(db, "imports")
    enterprise.require_page_size(db, limit)
    query = select(ImportJob)
    if user.role != "admin":
        query = query.where(ImportJob.actor_id == user.id)
    if user.role == "gerente":
        query = query.where(ImportJob.entity_type.in_(("plan", "objective")))
    elif user.role == "lider":
        query = query.where(ImportJob.entity_type == "task",
                            ImportJob.department_id == user.department_id)
    if cursor:
        query = query.where(ImportJob.id > cursor)
    rows = list(db.scalars(query.order_by(ImportJob.id).limit(limit + 1)))
    return {"items": [import_view(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def create_import(db, user, body, request):
    policy = authorize_import(db, user, body.entity_type)
    request.app.state.import_limiter.check(str(user.id), request.client.host if request.client
                                         else "local")
    try:
        content = base64.b64decode(body.content.get_secret_value(), validate=True)
    except (ValueError, binascii.Error):
        raise CommandError(422, "IMPORT_ENCODING_INVALID") from None
    if not content or len(content) > policy.import_max_bytes:
        raise CommandError(413, "IMPORT_TOO_LARGE")
    file_hash = digest(content)
    previous = existing_job(db, user, "import", body.idempotency_key)
    if previous:
        record = db.scalar(select(ImportJob).where(ImportJob.job_id == previous.id))
        if record is None or (record.file_hash, record.file_format, record.entity_type) != (
            file_hash, body.file_format, body.entity_type,
        ):
            raise CommandError(409, "IDEMPOTENCY_CONFLICT")
        return import_view(import_record(db, user, record.id))
    active = db.scalar(select(func.count()).select_from(ImportJob).where(
        ImportJob.actor_id == user.id, ImportJob.state.in_(("uploaded", "previewed", "rejected")),
        ImportJob.expires_at > operation.instant(db),
    ))
    if active >= 5:
        raise CommandError(429, "IMPORT_ACTIVE_JOB_LIMIT")
    scan = getattr(request.app.state, "import_scanner", None) or enterprise.scanner(db, request)
    scan_version = scan(content)
    if not isinstance(scan_version, str) or not scan_version:
        raise CommandError(503, "IMPORT_SCANNER_UNAVAILABLE")
    headers, rows = parse_table(content, body.file_format,
                                ImportLimits(policy.import_max_rows, policy.import_max_bytes))
    identity = uuid4()
    value = encrypt(db, request, "import_staging", identity, 1, content)
    job = create_job(db, user, request, "import", body.idempotency_key, file_hash)
    record = ImportJob(
        id=identity, job_id=job.id, actor_id=user.id, department_id=user.department_id,
        entity_type=body.entity_type, file_format=body.file_format, file_hash=file_hash,
        file_size=len(content), scan_version=scan_version[:200], headers=headers,
        mapping={}, state="uploaded", row_count=len(rows), error_count=0, preview_attempts=0,
        expires_at=operation.instant(db) + timedelta(hours=1), key_id=value.key_id,
        nonce=value.nonce, ciphertext=value.ciphertext,
    )
    db.add(record)
    db.flush([record])
    event(db, request, user, record, "import_created", file_hash=file_hash,
          row_count=len(rows), reason=body.reason)
    return import_view(record)


def normalize_row(entity_type, mapping, headers, raw):
    if entity_type not in SCHEMAS or not set(mapping) <= set(headers) or (
        not set(mapping.values()) <= MAPPING_FIELDS[entity_type]
        or len(set(mapping.values())) != len(mapping)
    ):
        raise CommandError(422, "IMPORT_MAPPING_INVALID")
    values = {target: raw[headers.index(source)] for source, target in mapping.items()}
    for field in ("custom_fields", "tag_ids"):
        if field in values:
            try:
                values[field] = json.loads(values[field])
            except (ValueError, TypeError, RecursionError):
                raise CommandError(422, "IMPORT_METADATA_INVALID") from None
    if values.get("priority_id") == "":
        values.pop("priority_id")
    return SCHEMAS[entity_type].model_validate(values)


def validate_domain(db, user, entity_type, body):
    operation.configuration(db)
    department = None
    references = []
    if entity_type == "plan":
        operation.horizon(db, body.horizon_type)
    elif entity_type == "objective":
        plan = operation.visible(db, AnnualPlan, body.annual_plan_id, user)
        operation.open_plan(plan)
        department = body.department_id
        record = db.get(Department, department)
        if record is None or not record.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")
        operation.horizon(db, body.horizon_type)
        operation.contained(body.start_date, body.due_date, body.due_date, plan)
        references.extend([(AnnualPlan, plan), (Department, record)])
    else:
        objective = operation.visible(db, Objective, body.objective_id, user)
        plan = operation.visible(db, AnnualPlan, objective.annual_plan_id, user)
        operation.open_plan(plan, active=True)
        department = objective.department_id
        record = db.get(Department, department)
        if record is None or not record.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")
        operation.valid_assignee(db, body.assignee_id, department)
        operation.priority(db, body.priority_id)
        operation.contained(body.start_date, body.due_date, body.due_date, objective)
        if body.start_date > body.due_date:
            raise CommandError(422, "INVALID_INTERVAL")
        references.extend([(AnnualPlan, plan), (Objective, objective), (Department, record),
                           (User, db.get(User, body.assignee_id))])
    collaboration.validate_template_metadata(db, entity_type, department, body)
    return references


def configuration_hash(db, user, references):
    context = {"actor": [str(user.id), user.role, str(user.department_id), user.token_version]}
    for model in (SystemSetting, SecurityPolicy, FeatureFlag, HorizonType, Priority, WorkflowStage):
        context[model.__tablename__] = [operation.state(row) for row in
                                       db.scalars(select(model).order_by(model.id))]
    definitions = list(db.scalars(collaboration.catalog_query(CustomFieldDefinition, user)
                                  .order_by(CustomFieldDefinition.id)))
    context["field_definitions"] = [operation.state(row) for row in definitions]
    context["field_options"] = [operation.state(row) for row in db.scalars(
        select(CustomFieldOption).where(CustomFieldOption.definition_id.in_(
            [definition.id for definition in definitions],
        )).order_by(CustomFieldOption.id),
    )]
    context["tags"] = [operation.state(row) for row in db.scalars(
        collaboration.catalog_query(Tag, user).order_by(Tag.id),
    )]
    context["references"] = sorted({
        (model.__tablename__, str(record.id), record.version)
        for model, record in references
    })
    return digest(context)


def preview_rows(db, user, record, mapping, content):
    policy = authorize_import(db, user, record.entity_type)
    headers, rows = parse_table(content, record.file_format,
                                ImportLimits(policy.import_max_rows, policy.import_max_bytes))
    if not set(mapping) <= set(headers) or not set(mapping.values()) <= (
        MAPPING_FIELDS[record.entity_type]
    ) or not mapping:
        raise CommandError(422, "IMPORT_MAPPING_INVALID")
    results, references = [], []
    for number, raw in enumerate(rows, 1):
        errors, normalized = [], {}
        try:
            body = normalize_row(record.entity_type, mapping, headers, raw)
            normalized = body.model_dump(mode="json", exclude_unset=True)
            references.extend(validate_domain(db, user, record.entity_type, body))
        except ValidationError as error:
            for entry in error.errors(include_input=False, include_context=False):
                field = str(entry["loc"][0]) if entry["loc"] else "row"
                column = next((name for name, target in mapping.items() if target == field), field)
                errors.append({"row": number, "column": column, "code": "INVALID_FIELD"})
        except CommandError as error:
            if error.status >= 500:
                raise
            errors.append({"row": number, "column": "row", "code": error.code})
        results.append({"row": number, "data": normalized, "errors": errors[:100]})
    context_hash = configuration_hash(db, user, references)
    preview_hash = digest({"file": record.file_hash, "mapping": mapping, "rows": results,
                           "configuration": context_hash})
    return results, references, context_hash, preview_hash


def preview_import(db, user, identity, body, request):
    record = import_record(db, user, identity, lock=True)
    check_version(record, body.expected_version)
    if record.expires_at <= operation.instant(db) or record.state in {"committed", "expired"}:
        raise CommandError(409, "IMPORT_NOT_PREVIEWABLE")
    if record.preview_attempts >= 10:
        raise CommandError(409, "IMPORT_PREVIEW_LIMIT")
    content = decrypt(db, request, record)
    if digest(content) != record.file_hash:
        raise CommandError(503, "IMPORT_INTEGRITY_FAILURE")
    rows, _references, context_hash, preview_hash = preview_rows(
        db, user, record, body.mapping, content,
    )
    operation.bump(db, record)
    record.mapping = body.mapping
    record.error_count = sum(len(row["errors"]) for row in rows)
    record.preview_attempts += 1
    record.state = "rejected" if record.error_count else "previewed"
    record.config_hash, record.preview_hash = context_hash, preview_hash
    db.flush([record])
    crypt = platform.vault(db, request)
    key = platform.wrapped(db.get(SecretKeyVersion, record.key_id))
    for row in rows:
        identity = uuid4()
        value = crypt.encrypt_payload(key, identity, record.version, canonical(row["data"]))
        entry = ImportRow(
            id=identity, import_id=record.id, preview_version=record.version,
            row_number=row["row"], row_hash=digest(row["data"]), errors=row["errors"],
            key_id=value.key_id, nonce=value.nonce, ciphertext=value.ciphertext,
        )
        db.add(entry)
        event(db, request, user, entry, "import_previewed", import_id=str(record.id),
              preview_version=record.version, row_number=row["row"])
    event(db, request, user, record, "import_previewed", preview_hash=preview_hash,
          error_count=record.error_count, reason=body.reason)
    db.flush()
    return {**import_view(record), "rows": [
        {"row": row["row"], "errors": row["errors"], "valid": not row["errors"],
         "preview": public_preview(row["data"])} for row in rows
    ]}


def public_preview(data):
    return {name: data[name] for name in ("title", "start_date", "due_date", "horizon_type")
            if name in data}


def lock_references(db, user, references):
    identities = {model: set() for model in (Department, User, AnnualPlan, Objective)}
    identities[User].add(user.id)
    for model, record in references:
        identities[model].add(record.id)
    for model, values in identities.items():
        if values:
            operation.lock_rows(db, model, values)


def commit_import(db, user, identity, body, request):
    record = import_record(db, user, identity, lock=True)
    if record.state == "committed":
        if record.commit_key == body.idempotency_key and record.preview_hash == body.preview_hash:
            return import_view(record)
        raise CommandError(409, "IDEMPOTENCY_CONFLICT")
    check_version(record, body.expected_version)
    if record.state != "previewed" or record.expires_at <= operation.instant(db) or (
        record.preview_hash != body.preview_hash
    ):
        raise CommandError(409, "IMPORT_PREVIEW_STALE")
    content = decrypt(db, request, record)
    if digest(content) != record.file_hash:
        raise CommandError(503, "IMPORT_INTEGRITY_FAILURE")
    rows, references, context_hash, preview_hash = preview_rows(
        db, user, record, record.mapping, content,
    )
    lock_references(db, user, references)
    rows, _references, context_hash, preview_hash = preview_rows(
        db, user, record, record.mapping, content,
    )
    if record.config_hash != context_hash or record.preview_hash != preview_hash or any(
        row["errors"] for row in rows
    ):
        raise CommandError(409, "IMPORT_PREVIEW_STALE")
    result = []
    for row in rows:
        data = SCHEMAS[record.entity_type].model_validate(row["data"])
        created = CREATORS[record.entity_type](db, user, data, request)
        result.append(str(created["id"]))
    operation.bump(db, record)
    record.state, record.commit_key, record.result_ids = "committed", body.idempotency_key, result
    event(db, request, user, record, "import_committed", row_count=len(result),
          preview_hash=record.preview_hash, reason=body.reason)
    job = db.scalar(select(JobRun).where(JobRun.id == record.job_id).with_for_update())
    finish_job(db, user, request, job)
    db.flush()
    return import_view(record)


def preview_detail(db, user, identity, request):
    record = import_record(db, user, identity)
    if record.expires_at <= operation.instant(db):
        raise CommandError(409, "IMPORT_STAGING_EXPIRED")
    rows = list(db.scalars(select(ImportRow).where(
        ImportRow.import_id == record.id,
        ImportRow.preview_version == record.preview_attempts + 1,
    ).order_by(ImportRow.row_number).limit(1001)))
    results = []
    for row in rows:
        data = json.loads(decrypt(db, request, row, version=row.preview_version))
        if digest(data) != row.row_hash:
            raise CommandError(503, "IMPORT_INTEGRITY_FAILURE")
        results.append({"row": row.row_number, "errors": row.errors, "valid": not row.errors,
                        "preview": public_preview(data)})
    return {**import_view(record), "rows": results}