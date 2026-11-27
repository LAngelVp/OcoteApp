import ipaddress
import json
import secrets
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import TypeAdapter
from sqlalchemy import func, select

from app.core.errors import CommandError
from app.core.integration_security import (
    API_SCOPES,
    client_ip_allowed,
    key_digest,
    key_identifier,
    key_matches,
    new_service_key,
    validate_key_expiry,
    validated_scopes,
)
from app.core.security import now
from app.models.collaboration import ServicePrincipal
from app.models.identity import AuditEvent, Department, User
from app.models.integrations import APIKey
from app.models.operations import Objective, Task
from app.models.platform import IntegrationConfig, IntegrationHealthCheck
from app.schemas.integrations import ConnectorConfig
from app.services import operations as operation
from app.services import platform
from app.services.administration import check_version
from app.services.collaboration import mutable_record, save_record
from app.services.enterprise import (
    department_scope,
    policy,
    reauthenticate,
    require_module,
    require_page_size,
)
from app.services.identity import audit, touch
from app.services.notifications import decrypted_secret, store_secret

CONFIG = TypeAdapter(ConnectorConfig)
KINDS = {"oidc": "sso", "saml": "sso", "ldap": "sso", "github": "devops",
         "gitlab": "devops", "outgoing_webhook": "outgoing_webhook"}


def administrator(actor):
    if actor is None or not actor.is_active or actor.role != "admin":
        raise CommandError(403, "ADMINISTRATOR_REQUIRED")


def modules(db, kind):
    require_module(db, "integrations")
    require_module(db, "outgoing_webhooks" if kind == "outgoing_webhook" else kind)


def connector_endpoints(config):
    if config.provider == "oidc":
        return (config.authorization_endpoint, config.token_endpoint, config.jwks_endpoint)
    if config.provider == "saml":
        return (config.sso_endpoint,)
    if config.provider == "ldap":
        return (config,)
    if config.provider in {"github", "gitlab"}:
        return (config.api_endpoint,)
    return (config.endpoint,)


def connector_view(record):
    return {key: getattr(record, key) for key in (
        "id", "version", "name", "kind", "provider", "scope_kind", "department_id", "config",
        "config_revision", "is_active", "tested_version", "tested_at",
    )} | {"secret_configured": record.secret_id is not None}


def connector_for(db, identity, *, lock=False):
    record = db.get(IntegrationConfig, identity, with_for_update=lock, populate_existing=True)
    if record is None or record.kind not in set(KINDS.values()):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def credentials(config, value):
    try:
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 65536:
            raise ValueError
        if config.provider in {"github", "gitlab"}:
            material = json.loads(value)
            if not isinstance(material, dict) or set(material) != {
                "access_token", "webhook_secret"
            }:
                raise ValueError
            if not all(isinstance(item, str) for item in material.values()):
                raise ValueError
            if not 1 <= len(material["access_token"]) <= 16384:
                raise ValueError
            if not 16 <= len(material["webhook_secret"].encode()) <= 1024:
                raise ValueError
        elif config.provider == "saml":
            private = serialization.load_pem_private_key(value.encode(), password=None)
            certificate = x509.load_pem_x509_certificate(config.sp_certificate_pem.encode())
            if (
                not isinstance(private, rsa.RSAPrivateKey)
                or private.key_size < 2048
                or private.public_key().public_numbers()
                != certificate.public_key().public_numbers()
            ):
                raise ValueError
        elif config.provider == "outgoing_webhook":
            if not 32 <= len(value.encode()) <= 1024:
                raise ValueError
        elif len(value) > 16384:
            raise ValueError
        return value
    except Exception:
        raise CommandError(422, "PROVIDER_CREDENTIALS_INVALID") from None


def connector_material(db, record, request=None):
    config = CONFIG.validate_python(record.config)
    material = (
        decrypted_secret(db, record.id, record.secret_id, "integrations", request)
        if record.secret_id else None
    )
    if material is None:
        if config.provider != "oidc" or config.token_auth_method != "none":
            raise CommandError(503, "VAULT_UNAVAILABLE")
    else:
        credentials(config, material)
    return config, material


def connectors(db, actor, limit, cursor=None):
    administrator(actor)
    require_module(db, "integrations")
    require_page_size(db, limit)
    query = select(IntegrationConfig).where(IntegrationConfig.kind.in_(set(KINDS.values())))
    if cursor:
        query = query.where(IntegrationConfig.id > cursor)
    rows = list(db.scalars(query.order_by(IntegrationConfig.id).limit(limit + 1)))
    return {"items": [connector_view(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def save_connector(db, identity, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    kind = KINDS[body.config.provider]
    modules(db, kind)
    department_scope(db, body.scope_kind, body.department_id)
    record = connector_for(db, identity, lock=True) if identity else None
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    values = {"name": body.name, "scope_kind": body.scope_kind,
              "department_id": body.department_id, "config": body.config.model_dump(mode="json")}
    if record is None:
        record = IntegrationConfig(id=uuid4(), version=1, config_revision=1,
                                   provider=body.config.provider, kind=kind)
    elif record.provider != body.config.provider:
        raise CommandError(409, "PROVIDER_TYPE_IMMUTABLE")
    issued_secret = None
    secret_id = record.secret_id
    if body.credential is not None:
        material = credentials(body.config, body.credential.get_secret_value())
    elif identity is None and body.config.provider == "outgoing_webhook":
        issued_secret = secrets.token_urlsafe(32)
        material = issued_secret
    else:
        material = None
    if material is not None:
        secret_id = store_secret(
            db, record.id, "integrations", material, body.reason, request, actor
        )
    if secret_id is None and (
        body.config.provider != "oidc" or body.config.token_auth_method != "none"
    ):
        raise CommandError(422, "PROVIDER_CREDENTIALS_REQUIRED")
    changed = {key for key, value in values.items() if getattr(record, key) != value}
    if secret_id != record.secret_id:
        changed.add("secret_replaced")
    if identity and not changed:
        return connector_view(record)
    if identity:
        record.config_revision += 1
        touch(record)
    for key, value in values.items():
        setattr(record, key, value)
    record.secret_id, record.is_active = secret_id, False
    record.tested_version = record.tested_at = None
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, changed
    )
    db.add(record)
    db.flush()
    result = connector_view(record)
    if issued_secret is not None:
        result["issued_secret"] = issued_secret
    return result


def connector_checks(db, identity, actor, limit, cursor=None):
    administrator(actor)
    record = connector_for(db, identity)
    modules(db, record.kind)
    require_page_size(db, limit)
    query = select(IntegrationHealthCheck).where(IntegrationHealthCheck.integration_id == identity)
    if cursor:
        query = query.where(IntegrationHealthCheck.id > cursor)
    rows = list(db.scalars(query.order_by(IntegrationHealthCheck.id).limit(limit + 1)))
    return {"items": [operation.state(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def test_connector(db, tokens, identity, body, request, actor):
    administrator(actor)
    record = connector_for(db, identity, lock=True)
    if record.kind == "sso":
        from app.services.federation import start_probe

        return start_probe(db, tokens, request, identity, body, actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    modules(db, record.kind)
    check_version(record, body.expected_version)
    if any(getattr(body, field) is not None for field in (
        "revocation_confirmed", "test_username", "test_password", "emergency_password"
    )):
        raise CommandError(422, "SSO_PROBE_FIELDS_NOT_ALLOWED")
    config, credential = connector_material(db, record, request)
    if not all(endpoint.audience_approved for endpoint in connector_endpoints(config)):
        raise CommandError(422, "EXPLICIT_AUDIENCE_AND_DESTINATION_REQUIRED")
    department_scope(db, record.scope_kind, record.department_id)
    record.is_active = False
    record.tested_version = record.tested_at = None
    touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["probe_started"]
    )
    prepared = (record.version, record.config_revision, actor.id, actor.token_version,
                record.secret_id)
    kind = record.kind
    db.flush()
    db.commit()
    passed = False
    try:
        transport = getattr(request.app.state, "integration_transport", None)
        if kind == "devops":
            from app.core.devops import verify_repositories

            verify_repositories(config, json.loads(credential)["access_token"], transport=transport)
        else:
            from app.core.outgoing_webhooks import send

            event = uuid4()
            content = json.dumps({"event_id": str(event), "schema_version": 1,
                                  "event_type": "ocote.connection_test", "synthetic": True},
                                 sort_keys=True, separators=(",", ":")).encode()
            status, _headers, _response = send(
                config, credential, prepared[4], event, uuid4(), content,
                timestamp=int(now().timestamp()), transport=transport,
            )
            if not 200 <= status < 300:
                raise CommandError(503, "WEBHOOK_TEST_REJECTED")
        passed = True
    except (CommandError, OSError, ValueError, TypeError, KeyError):
        pass
    finally:
        credential = None
    db.expire_all()
    db.info.pop("f8_flags", None)
    db.info.pop("f8_policy", None)
    from app.services.identity import config_lock

    config_lock(db)
    actor = db.get(User, prepared[2], with_for_update=True, populate_existing=True)
    administrator(actor)
    if actor.token_version != prepared[3]:
        raise CommandError(401, "INVALID_CREDENTIALS")
    record = connector_for(db, identity, lock=True)
    modules(db, record.kind)
    current = (record.version, record.config_revision) == prepared[:2]
    passed = passed and current
    code = ("F11_DEVOPS_VERIFIED" if record.kind == "devops" else "F11_WEBHOOK_VERIFIED") if (
        passed
    ) else "F11_PROVIDER_UNAVAILABLE_OR_UNSAFE"
    check = IntegrationHealthCheck(
        id=uuid4(), created_at=now(), integration_id=identity, config_version=prepared[1],
        status="passed" if passed else "failed", result_code=code, actor_id=actor.id,
        request_id=UUID(request.state.request_id),
    )
    db.add(check)
    db.flush([check])
    if not current:
        raise CommandError(409, "CONFIGURATION_CHANGED_DURING_TEST", persist=True)
    record.tested_version = record.config_revision if passed else None
    record.tested_at = now() if passed else None
    touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["probe_finished"]
    )
    db.flush()
    return connector_view(record) | {"passed": passed, "result_code": code}, None


def activate_connector(db, identity, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    record = connector_for(db, identity, lock=True)
    modules(db, record.kind)
    check_version(record, body.expected_version)
    if record.is_active:
        return connector_view(record)
    moment = now()
    if (
        record.tested_version != record.config_revision or record.tested_at is None
        or not moment - timedelta(minutes=10) <= record.tested_at <= moment
    ):
        raise CommandError(409, "FRESH_VERIFICATION_REQUIRED")
    config = connector_material(db, record, request)[0]
    if not all(endpoint.audience_approved for endpoint in connector_endpoints(config)):
        raise CommandError(422, "EXPLICIT_AUDIENCE_AND_DESTINATION_REQUIRED")
    department_scope(db, record.scope_kind, record.department_id)
    if record.kind == "sso":
        from app.services.federation import sso_proof_code

        emergency = db.get(User, config.emergency_admin_id, populate_existing=True)
        if emergency is None or not emergency.is_active or emergency.role != "admin" or (
            emergency.locked_until is not None and emergency.locked_until > moment
        ):
            raise CommandError(409, "SSO_LOCAL_EMERGENCY_UNAVAILABLE")
        code = sso_proof_code(record, config, emergency)
    else:
        code = "F11_DEVOPS_VERIFIED" if record.kind == "devops" else "F11_WEBHOOK_VERIFIED"
    proof = db.scalar(select(IntegrationHealthCheck.id).where(
        IntegrationHealthCheck.integration_id == record.id,
        IntegrationHealthCheck.config_version == record.config_revision,
        IntegrationHealthCheck.status == "passed", IntegrationHealthCheck.result_code == code,
        IntegrationHealthCheck.created_at >= moment - timedelta(minutes=10),
        IntegrationHealthCheck.created_at <= moment,
    ).limit(1))
    if proof is None:
        raise CommandError(409, "FRESH_VERIFICATION_REQUIRED")
    record.is_active = True
    touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["is_active"]
    )
    db.flush()
    return connector_view(record)


def deactivate_connector(db, identity, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    record = connector_for(db, identity, lock=True)
    modules(db, record.kind)
    check_version(record, body.expected_version)
    if record.is_active:
        record.is_active = False
        touch(record)
        record.configuration_revision_id = platform.revision(
            db, request, actor, record, body.reason, ["is_active"]
        )
        db.flush()
    return connector_view(record)


def key_view(record):
    return {name: getattr(record, name) for name in (
        "id", "version", "name", "service_principal_id", "owner_user_id", "scopes",
        "department_ids", "allowed_networks", "rate_per_minute", "expires_at", "created_at",
        "revoked_at", "rotated_from_id",
    )}


def owner_scopes(owner):
    return API_SCOPES if owner.role in {"admin", "lider"} else frozenset({"tasks:read"})


def key_context(record, principal, owner, requested_scope, address, moment):
    if (
        record is None or principal is None or owner is None
        or record.revoked_at is not None or record.expires_at <= moment
        or not principal.is_active or not owner.is_active
        or principal.id != record.service_principal_id or owner.id != record.owner_user_id
        or record.principal_token_version != principal.token_version
        or record.owner_token_version != owner.token_version
        or owner.role not in {"admin", "gerente", "lider", "colaborador"}
        or not client_ip_allowed(address, record.allowed_networks)
    ):
        raise CommandError(401, "SERVICE_CREDENTIAL_INVALID")
    scopes = set(record.scopes) & set(principal.approved_scopes) & owner_scopes(owner)
    departments = set(record.department_ids) & set(principal.department_ids)
    if owner.role in {"lider", "colaborador"}:
        departments &= {owner.department_id}
    if requested_scope not in scopes or not departments:
        raise CommandError(403, "SERVICE_SCOPE_DENIED")
    return SimpleNamespace(
        id=owner.id, role=owner.role, department_id=owner.department_id, is_active=True,
        actor_service_id=principal.id, service_key_id=record.id,
        service_scopes=frozenset(scopes), service_department_ids=frozenset(departments),
    )


def authenticate_key(db, request, requested_scope):
    modules(db, "api_keys")
    policy(db)
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise CommandError(401, "SERVICE_CREDENTIAL_INVALID")
    encoded = authorization[7:]
    identity = key_identifier(encoded)
    record = db.get(APIKey, identity, with_for_update=True, populate_existing=True)
    if record is None or record.revoked_at is not None or record.expires_at <= now():
        raise CommandError(401, "SERVICE_CREDENTIAL_INVALID")
    pepper = decrypted_secret(db, record.id, record.pepper_secret_id, "service_keys", request)
    if not key_matches(encoded, pepper.encode(), record.token_hash):
        raise CommandError(401, "SERVICE_CREDENTIAL_INVALID")
    principal = db.get(ServicePrincipal, record.service_principal_id)
    owner = db.get(User, record.owner_user_id)
    actor = key_context(
        record, principal, owner, requested_scope,
        request.client.host if request.client else "", now(),
    )
    departments = frozenset(db.scalars(select(Department.id).where(
        Department.id.in_(actor.service_department_ids), Department.is_active,
    )))
    if not departments:
        raise CommandError(403, "SERVICE_SCOPE_DENIED")
    actor.service_department_ids = departments
    recent = db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity_type == "api_keys", AuditEvent.entity_id == record.id,
        AuditEvent.event_type == "service_authenticated",
        AuditEvent.created_at >= now() - timedelta(minutes=1),
    ))
    if recent >= record.rate_per_minute:
        raise CommandError(429, "SERVICE_RATE_LIMIT")
    audit(db, request, "service_authenticated", entity="api_keys", entity_id=record.id,
          actor_service=principal.id, after={"scope": requested_scope})
    request.state.actor = principal.id
    return actor


def principal_list(db, actor, limit, cursor=None):
    administrator(actor)
    modules(db, "api_keys")
    require_page_size(db, limit)
    query = select(ServicePrincipal)
    if cursor:
        query = query.where(ServicePrincipal.id > cursor)
    rows = list(db.scalars(query.order_by(ServicePrincipal.id).limit(limit + 1)))
    return {"items": [operation.state(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def save_principal(db, principal_id, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    modules(db, "api_keys")
    departments = set(body.department_ids)
    active = set(db.scalars(select(Department.id).where(
        Department.id.in_(departments), Department.is_active,
    )))
    if active != departments:
        raise CommandError(422, "INVALID_DEPARTMENT")
    principal_id = principal_id or uuid4()
    previous = db.get(ServicePrincipal, principal_id, with_for_update=True,
                      populate_existing=True)
    if body.expected_version != (previous.version if previous else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    values = {name: getattr(body, name) for name in (
        "name", "department_ids", "approved_scopes", "is_active",
    )}
    values.update(token_version=previous.token_version + 1 if previous else 1,
                  created_by=previous.created_by if previous else actor.id)
    record, before = mutable_record(db, ServicePrincipal, principal_id, body, values=values)
    save_record(db, actor, request, record, before, "principal_changed", body.reason)
    return operation.state(record)


def issue_key(db, body, request, actor, *, rotated_from=None):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    modules(db, "api_keys")
    return _new_key(db, body, request, actor, rotated_from=rotated_from)


def _new_key(db, body, request, actor, *, rotated_from=None):
    if body.expected_version != 0:
        raise CommandError(409, "VERSION_CONFLICT")
    principal = db.get(ServicePrincipal, body.service_principal_id)
    owner = db.get(User, body.owner_user_id)
    if not principal or not principal.is_active or not owner or not owner.is_active:
        raise CommandError(422, "SERVICE_DELEGATION_INVALID")
    scopes = validated_scopes(body.scopes, set(principal.approved_scopes) & owner_scopes(owner))
    departments = set(body.department_ids)
    if not departments <= set(principal.department_ids) or (
        owner.role in {"lider", "colaborador"} and departments != {owner.department_id}
    ):
        raise CommandError(422, "SERVICE_DELEGATION_INVALID")
    active = set(db.scalars(select(Department.id).where(
        Department.id.in_(departments), Department.is_active,
    )))
    if active != departments:
        raise CommandError(422, "INVALID_DEPARTMENT")
    issued = now()
    validate_key_expiry(issued, body.expires_at)
    identity = uuid4()
    encoded, pepper = new_service_key(identity), secrets.token_urlsafe(32)
    record = APIKey(
        id=identity, version=1, created_at=issued, updated_at=issued, name=body.name,
        service_principal_id=principal.id, owner_user_id=owner.id,
        principal_token_version=principal.token_version, owner_token_version=owner.token_version,
        rate_per_minute=body.rate_per_minute, scopes=scopes,
        department_ids=sorted(departments, key=str), allowed_networks=body.allowed_networks,
        token_hash=key_digest(encoded, pepper.encode()), expires_at=body.expires_at,
        revoked_at=None, rotated_from_id=rotated_from,
    )
    record.pepper_secret_id = store_secret(
        db, identity, "service_keys", pepper, body.reason, request, actor
    )
    db.add(record)
    audit(db, request, "administration_changed", actor=actor.id, entity="api_keys",
          entity_id=identity, after={"version": 1, "reason": body.reason, "issued": True})
    db.flush()
    return key_view(record) | {"api_key": encoded}


def rotate_key(db, key_id, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    modules(db, "api_keys")
    record = db.get(APIKey, key_id, with_for_update=True, populate_existing=True)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.revoked_at is not None or record.expires_at <= now():
        raise CommandError(409, "SERVICE_KEY_TERMINAL")
    if (
        body.service_principal_id != record.service_principal_id
        or body.owner_user_id != record.owner_user_id
        or not set(body.scopes) <= set(record.scopes)
        or not set(body.department_ids) <= set(record.department_ids)
        or body.rate_per_minute > record.rate_per_minute
    ):
        raise CommandError(422, "SERVICE_ROTATION_MUST_NOT_EXPAND")
    if record.allowed_networks is not None:
        if body.allowed_networks is None:
            raise CommandError(422, "SERVICE_ROTATION_MUST_NOT_EXPAND")
        approved = [ipaddress.ip_network(value, strict=True) for value in record.allowed_networks]
        requested = [ipaddress.ip_network(value, strict=True) for value in body.allowed_networks]
        if any(not any(network.version == original.version and network.subnet_of(original)
                       for original in approved) for network in requested):
            raise CommandError(422, "SERVICE_ROTATION_MUST_NOT_EXPAND")
    record.revoked_at = now()
    touch(record)
    audit(db, request, "administration_changed", actor=actor.id, entity="api_keys",
          entity_id=record.id, after={"version": record.version, "reason": body.reason,
                                     "rotated": True})
    db.flush()
    return _new_key(db, body.model_copy(update={"expected_version": 0}), request, actor,
                    rotated_from=record.id)


def revoke_key(db, identity, body, request, actor):
    administrator(actor)
    reauthenticate(db, actor, body, request)
    administrator(actor)
    modules(db, "api_keys")
    record = db.get(APIKey, identity, with_for_update=True, populate_existing=True)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.revoked_at is None:
        record.revoked_at = now()
        touch(record)
        audit(db, request, "administration_changed", actor=actor.id, entity="api_keys",
              entity_id=record.id, after={"version": record.version, "reason": body.reason,
                                         "revoked": True})
        db.flush()
    return key_view(record)


def keys(db, actor, limit, cursor=None):
    administrator(actor)
    modules(db, "api_keys")
    require_page_size(db, limit)
    query = select(APIKey)
    if cursor:
        query = query.where(APIKey.id > cursor)
    records = list(db.scalars(query.order_by(APIKey.id).limit(limit + 1)))
    return {"items": [key_view(record) for record in records[:limit]],
            "next_cursor": records[limit - 1].id if len(records) > limit else None}


def technical_query(actor):
    return operation.scope(select(Task), Task, actor).where(Task.objective_id.in_(
        select(Objective.id).where(Objective.department_id.in_(actor.service_department_ids))
    ))


def technical_tasks(db, actor, limit, cursor=None):
    require_page_size(db, limit)
    query = technical_query(actor)
    if cursor:
        query = query.where(Task.id > cursor)
    records = list(db.scalars(query.order_by(Task.id).limit(limit + 1)))
    return {"items": [operation.task_view(db, record, actor) for record in records[:limit]],
            "next_cursor": records[limit - 1].id if len(records) > limit else None}


def technical_task(db, actor, identity):
    record = db.scalar(technical_query(actor).where(Task.id == identity))
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def create_technical_task(db, actor, body, request):
    objective = db.scalar(select(Objective).where(
        Objective.id == body.objective_id,
        Objective.department_id.in_(actor.service_department_ids),
    ))
    if objective is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return operation.create_task(db, actor, body, request)


def update_technical_task(db, actor, identity, body, request):
    technical_task(db, actor, identity)
    return operation.change_task(db, actor, identity, body, request, "task_updated")