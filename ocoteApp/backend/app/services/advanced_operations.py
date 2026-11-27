from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.core.errors import CommandError
from app.core.operations_agent import probe
from app.core.vault import EncryptedValue
from app.models.bulk import BackupRecord, RetentionPolicy
from app.models.collaboration import JobRun, ServicePrincipal
from app.models.identity import User
from app.models.platform import (
    EncryptedSecret,
    IntegrationConfig,
    IntegrationHealthCheck,
    SecretKeyVersion,
)
from app.services import bulk, enterprise, platform
from app.services import operations as operation
from app.services.administration import check_version


def authorize(db, user):
    operation.permit(user, "admin")
    enterprise.require_module(db, "advanced_operations")


def agent_record(db, *, lock=False):
    query = select(IntegrationConfig).where(IntegrationConfig.kind == "operations_agent")
    return db.scalar(query.with_for_update() if lock else query)


def principals(db, user, *, limit, cursor=None):
    authorize(db, user)
    enterprise.require_page_size(db, limit)
    query = select(ServicePrincipal).where(ServicePrincipal.is_active)
    if cursor:
        query = query.where(ServicePrincipal.id > cursor)
    rows = list(db.scalars(query.order_by(ServicePrincipal.id).limit(limit + 1)))
    return {"items": [{"id": row.id, "name": row.name, "version": row.version}
                       for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def agent_view(record):
    if record is None:
        return {"configured": False, "is_active": False, "capabilities": [], "version": 0}
    return {
        "configured": True, "id": record.id, "version": record.version,
        "config_revision": record.config_revision, "is_active": record.is_active,
        "tested_version": record.tested_version, "tested_at": record.tested_at,
        "service_principal_id": record.config["service_principal_id"],
        "capabilities": record.config["capabilities"],
        "destination_ref": record.config["destination_ref"],
        "authentication_configured": record.secret_id is not None,
    }


def register_agent(db, user, body, request):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    principal = db.get(ServicePrincipal, body.service_principal_id)
    if principal is None or not principal.is_active:
        raise CommandError(422, "OPERATIONS_PRINCIPAL_REQUIRED")
    record = agent_record(db, lock=True)
    if (record.version if record else 0) != body.expected_version:
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = IntegrationConfig(id=uuid4(), kind="operations_agent", provider="local_agent",
                                   name="Local operations agent", scope_kind="organization",
                                   department_id=None, config_revision=1, is_active=False,
                                   version=1)
    else:
        operation.bump(db, record)
        record.config_revision += 1
    previous = db.get(EncryptedSecret, record.secret_id) if record.secret_id else None
    platform.write_secret(db, record.id, "operations_agent", SimpleNamespace(
        expected_version=previous.secret_version if previous else 0,
        value=body.authentication_secret, reason=body.reason,
    ), request, user)
    secret = db.scalar(select(EncryptedSecret).where(
        EncryptedSecret.owner_id == record.id, EncryptedSecret.purpose == "operations_agent",
    ).order_by(EncryptedSecret.secret_version.desc()).limit(1))
    record.secret_id = secret.id
    record.config = {
        "provider": "local_agent", "service_principal_id": str(body.service_principal_id),
        "capabilities": body.capabilities, "destination_ref": str(body.destination_ref),
        "protocol_version": 1,
    }
    record.is_active, record.tested_at, record.tested_version = False, None, None
    record.configuration_revision_id = platform.revision(
        db, request, user, record, body.reason, ["agent_configuration", "authentication_replaced"],
    )
    db.add(record)
    db.flush([record])
    bulk.event(db, request, user, record, "operations_agent_changed", configured=True,
               config_revision=record.config_revision)
    return agent_view(record)


def call_probe(db, record, request):
    secret = db.get(EncryptedSecret, record.secret_id)
    principal = db.get(ServicePrincipal, UUID(record.config["service_principal_id"]))
    if secret is None or principal is None or not principal.is_active:
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    key = db.get(SecretKeyVersion, secret.key_id)
    if key is None:
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    crypt = platform.vault(db, request)
    authentication = crypt.decrypt(platform.wrapped(key), EncryptedValue(
        key.id, secret.owner_id, secret.secret_version, secret.nonce, secret.ciphertext,
    ))
    caller = getattr(request.app.state, "operations_agent", None) or probe
    capabilities = caller(platform.instance(db).id, authentication)
    if not isinstance(capabilities, list) or not set(record.config["capabilities"]) <= (
        set(capabilities)
    ):
        raise CommandError(503, "OPERATIONS_AGENT_CAPABILITY_UNAVAILABLE")
    return capabilities


def test_agent(db, user, body, request):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    record = agent_record(db, lock=True)
    if record is None:
        raise CommandError(503, "OPERATIONS_AGENT_UNCONFIGURED")
    check_version(record, body.expected_version)
    error = None
    try:
        call_probe(db, record, request)
    except CommandError as failure:
        error = failure
    operation.bump(db, record)
    record.tested_at = operation.instant(db) if error is None else None
    record.tested_version = record.config_revision if error is None else None
    if error is not None:
        record.is_active = False
    db.add(IntegrationHealthCheck(integration_id=record.id, config_version=record.config_revision,
                                  status="passed" if error is None else "failed",
                                  result_code="PROBE_OK" if error is None else error.code,
                                  actor_id=user.id, request_id=UUID(request.state.request_id)))
    bulk.event(db, request, user, record, "operations_agent_changed", tested=error is None)
    db.flush()
    if error is not None:
        raise CommandError(error.status, error.code, persist=True)
    return agent_view(record)


def activate_agent(db, user, body, request):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    record = agent_record(db, lock=True)
    if record is None:
        raise CommandError(503, "OPERATIONS_AGENT_UNCONFIGURED")
    check_version(record, body.expected_version)
    moment = operation.instant(db)
    if record.tested_version != record.config_revision or record.tested_at is None or not (
        moment - timedelta(minutes=10) <= record.tested_at <= moment
    ):
        raise CommandError(409, "OPERATIONS_AGENT_TEST_REQUIRED")
    call_probe(db, record, request)
    operation.bump(db, record)
    record.is_active = True
    bulk.event(db, request, user, record, "operations_agent_changed", is_active=True,
               config_revision=record.config_revision)
    db.flush()
    return agent_view(record)


def deactivate_agent(db, user, body, request):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    record = agent_record(db, lock=True)
    if record is None:
        raise CommandError(503, "OPERATIONS_AGENT_UNCONFIGURED")
    check_version(record, body.expected_version)
    operation.bump(db, record)
    record.is_active = False
    bulk.event(db, request, user, record, "operations_agent_changed", is_active=False)
    db.flush()
    return agent_view(record)


def job_view(record):
    return {name: getattr(record, name) for name in (
        "id", "kind", "created_at", "updated_at", "version", "state", "attempt",
    )}


def request_backup(db, user, body, request, *, source_id=None):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    record = agent_record(db, lock=True)
    capability = "restore_verify" if source_id else "backup"
    if record is None or not record.is_active or record.tested_version != record.config_revision:
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    if capability not in record.config["capabilities"]:
        raise CommandError(503, "OPERATIONS_AGENT_CAPABILITY_UNAVAILABLE")
    if source_id:
        source = db.get(BackupRecord, source_id)
        if source is None:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        check_version(source, body.expected_version)
    else:
        check_version(record, body.expected_version)
    payload = {"destination_ref": record.config["destination_ref"],
               "source_backup_id": str(source_id) if source_id else None}
    input_hash = bulk.digest({"kind": capability, "payload": payload,
                              "revision": str(record.configuration_revision_id)})
    previous = bulk.existing_job(db, user, capability, body.idempotency_key)
    if previous:
        if previous.input_hash != input_hash:
            raise CommandError(409, "IDEMPOTENCY_CONFLICT")
        return job_view(previous)
    call_probe(db, record, request)
    job = bulk.create_job(db, user, request, capability, body.idempotency_key, input_hash,
                          principal=UUID(record.config["service_principal_id"]),
                          revision=record.configuration_revision_id, payload=payload)
    bulk.event(db, request, user, job, "operation_requested", capability=capability,
               reason=body.reason)
    return job_view(job)


def backup_view(record):
    return {name: getattr(record, name) for name in (
        "id", "version", "created_at", "job_id", "instance_id", "source_backup_id",
        "source_revision", "manifest_hash", "dump_hash", "size_bytes", "restore_verified",
        "duration_ms",
    )}


def page(db, user, model, *, limit, cursor=None):
    authorize(db, user)
    enterprise.require_page_size(db, limit)
    query = select(model)
    if model is JobRun:
        query = query.where(JobRun.kind.in_(("backup", "restore_verify")))
    if cursor:
        query = query.where(model.id > cursor)
    rows = list(db.scalars(query.order_by(model.id).limit(limit + 1)))
    view = {BackupRecord: backup_view, JobRun: job_view}.get(model, operation.state)
    return {"items": [view(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def write_retention(db, user, body, request, identity=None):
    authorize(db, user)
    enterprise.reauthenticate(db, user, body, request)
    responsible = db.get(User, body.responsible_user_id)
    if responsible is None or not responsible.is_active:
        raise CommandError(422, "RETENTION_RESPONSIBLE_REQUIRED")
    record = db.scalar(select(RetentionPolicy).where(RetentionPolicy.id == identity)
                       .with_for_update()) if identity else None
    if identity and record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if (record.version if record else 0) != body.expected_version:
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = RetentionPolicy(id=uuid4(), category=body.category, created_by=user.id)
    else:
        if record.category != body.category:
            raise CommandError(409, "RETENTION_CATEGORY_IMMUTABLE")
        operation.bump(db, record)
    for field in ("minimum_days", "legal_hold", "responsible_user_id", "approval_ref"):
        setattr(record, field, getattr(body, field))
    db.add(record)
    db.flush([record])
    bulk.event(db, request, user, record, "retention_policy_changed", category=record.category,
               reason=body.reason, purge_authorized=False)
    return operation.state(record)


def health(db, user, request):
    authorize(db, user)
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != "20261126_0011":
        raise CommandError(503, "F12_REVISION_REQUIRED")
    platform_health = platform.health(db, request)
    last = db.scalar(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(1))
    return {
        "database": {"status": "ready", "revision": revision},
        "vault_available": platform_health["vault_available"],
        "evidence_configuration_verified": platform_health["evidence_configuration_verified"],
        "agent": agent_view(agent_record(db)),
        "last_verified_backup": backup_view(last) if last else None,
        "purge_authorized": False, "runtime_executes_privileged_commands": False,
        "customer_operational_acceptance": False,
    }