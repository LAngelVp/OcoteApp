import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.core.errors import CommandError
from app.core.evidence import EvidenceStore, failure, private_root
from app.core.object_storage import ObjectClient, https_request, unavailable
from app.core.security import now
from app.models.operations import EvidenceFile
from app.models.platform import EncryptedSecret, IntegrationConfig, IntegrationHealthCheck
from app.schemas.enterprise import AzureConfig, S3Config
from app.schemas.platform import SecretWrite
from app.services import platform
from app.services.administration import check_version
from app.services.enterprise import department_scope, reauthenticate, require_module, scanner
from app.services.identity import touch


def view(record):
    return {
        **platform.integration_view(record),
        "provider": record.provider,
        "name": record.name,
        "scope_kind": record.scope_kind,
        "department_id": record.department_id,
        "secret_configured": record.secret_id is not None,
    }


def record_for(db, identity, *, lock=True):
    record = db.get(IntegrationConfig, identity, with_for_update=lock)
    if record is None or record.kind != "object_storage":
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def save(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    require_module(db, "integrations")
    department_scope(db, body.scope_kind, body.department_id)
    record = record_for(db, identity) if identity else None
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    config = body.config.model_dump(mode="json")
    if record is None:
        record = IntegrationConfig(
            id=uuid4(),
            kind="object_storage",
            provider=config["provider"],
            config_revision=1,
            config=config,
            is_active=False,
        )
    else:
        if record.provider != config["provider"]:
            raise CommandError(409, "PROVIDER_TYPE_IMMUTABLE")
        if (record.config, record.scope_kind, record.department_id) != (
            config,
            body.scope_kind,
            body.department_id,
        ) and db.scalar(
            select(EvidenceFile.id).where(EvidenceFile.storage_config_id == record.id).limit(1)
        ):
            raise CommandError(409, "EVIDENCE_STORAGE_MIGRATION_REQUIRED")
    previous_secret = record.secret_id
    if body.credentials is not None:
        latest = db.scalar(
            select(EncryptedSecret)
            .where(
                EncryptedSecret.owner_id == record.id, EncryptedSecret.purpose == "object_storage"
            )
            .order_by(EncryptedSecret.secret_version.desc())
            .limit(1)
        )
        values = {
            name: value.get_secret_value()
            for name, value in body.credentials.__dict__.items()
            if value is not None
        }
        platform.write_secret(
            db,
            record.id,
            "object_storage",
            SecretWrite(
                expected_version=latest.secret_version if latest else 0,
                reason=body.reason,
                value=SecretStr(json.dumps(values)),
            ),
            request,
            actor,
        )
        record.secret_id = db.scalar(
            select(EncryptedSecret.id)
            .where(
                EncryptedSecret.owner_id == record.id, EncryptedSecret.purpose == "object_storage"
            )
            .order_by(EncryptedSecret.secret_version.desc())
            .limit(1)
        )
    if record.secret_id is None:
        raise CommandError(422, "PROVIDER_CREDENTIALS_REQUIRED")
    if identity:
        if (
            record.config,
            record.name,
            record.scope_kind,
            record.department_id,
            previous_secret,
        ) != (config, body.name, body.scope_kind, body.department_id, record.secret_id):
            record.config_revision += 1
        touch(record)
    record.config, record.name = config, body.name
    record.scope_kind, record.department_id = body.scope_kind, body.department_id
    record.is_active = False
    record.tested_version = record.tested_at = None
    record.configuration_revision_id = platform.revision(
        db,
        request,
        actor,
        record,
        body.reason,
        ["configuration", "credentials_replaced" if body.credentials is not None else "metadata"],
    )
    db.add(record)
    db.flush()
    return view(record)


def client_for(db, record, request=None):
    try:
        schema = S3Config if record.provider == "s3" else AzureConfig
        config = schema.model_validate(record.config).model_dump(mode="json")
        secret = db.get(EncryptedSecret, record.secret_id)
        if secret is None or secret.owner_id != record.id or secret.purpose != "object_storage":
            raise unavailable()
        key = db.get(platform.SecretKeyVersion, secret.key_id)
        content = platform.vault(db, request).decrypt(
            platform.wrapped(key), platform.encrypted(secret)
        )
        credentials = json.loads(content)
        transport = (
            getattr(request.app.state, "object_transport", https_request)
            if request is not None
            else https_request
        )
        return ObjectClient(config, credentials, transport)
    except (ValidationError, ValueError, KeyError, TypeError):
        raise unavailable() from None


def test(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    require_module(db, "integrations")
    record = record_for(db, identity)
    check_version(record, body.expected_version)
    passed = False
    try:
        client_for(db, record, request).probe()
        passed = True
    except (CommandError, OSError, ValueError):
        pass
    record.is_active = False
    record.tested_version = record.config_revision if passed else None
    record.tested_at = now() if passed else None
    code = "ISOLATED_STORAGE_VERIFIED" if passed else "OBJECT_PROVIDER_UNAVAILABLE_OR_UNSAFE"
    db.add(
        IntegrationHealthCheck(
            integration_id=record.id,
            config_version=record.config_revision,
            status="passed" if passed else "failed",
            result_code=code,
            actor_id=actor.id,
            request_id=UUID(request.state.request_id),
        )
    )
    touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["verification"]
    )
    db.flush()
    return view(record) | {"passed": passed, "result_code": code}


def activate(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    require_module(db, "integrations")
    record = record_for(db, identity)
    check_version(record, body.expected_version)
    if body.is_active:
        if (
            record.tested_version != record.config_revision
            or record.tested_at is None
            or now() - record.tested_at > timedelta(minutes=10)
        ):
            raise CommandError(409, "FRESH_VERIFICATION_REQUIRED")
        scanner(db, request)
        others = db.scalar(
            select(IntegrationConfig.id)
            .where(
                IntegrationConfig.id != record.id,
                IntegrationConfig.is_active,
                IntegrationConfig.kind.in_(("local_storage", "object_storage")),
                IntegrationConfig.department_id.is_not_distinct_from(record.department_id),
            )
            .limit(1)
        )
        if others is not None:
            raise CommandError(409, "ANOTHER_STORAGE_PROVIDER_ACTIVE")
    record.is_active = body.is_active
    touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["is_active"]
    )
    db.flush()
    return view(record)


class RemoteObject:
    def __init__(self, client, key):
        self.client, self.key = client, key

    def unlink(self, *, missing_ok=True):
        self.client.remove(self.key)


class RemoteEvidenceStore:
    def __init__(self, client, scan, record):
        self.client, self.scanner = client, scan
        self.configuration_id, self.configuration_version = record.id, record.config_revision
        self.allowed_mime = client.config["allowed_mime"]

    def path(self, key):
        return RemoteObject(self.client, key)

    def publish(self, content):
        version = self.scanner(content)
        if not isinstance(version, str) or not version.startswith("ClamAV "):
            raise failure()
        self.client.private()
        key = uuid4().hex
        try:
            self.client.write(key, content)
        except Exception:
            self.client.remove(key)
            raise
        return key, hashlib.sha256(content).hexdigest(), version

    def available(self, key, size, digest):
        self.client.private()
        content = self.client.read(key, limit=min(size, 10485760))
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise failure()
        return content


def configured_store(db, request=None, *, department_id=None, captured=None, historical=False):
    if captured is not None:
        record = db.get(IntegrationConfig, captured)
    elif historical:
        record = db.scalar(
            select(IntegrationConfig).where(IntegrationConfig.kind == "local_storage")
        )
    else:
        candidates = list(
            db.scalars(
                select(IntegrationConfig).where(
                    IntegrationConfig.is_active,
                    IntegrationConfig.kind.in_(("local_storage", "object_storage")),
                    (IntegrationConfig.department_id == department_id)
                    | IntegrationConfig.department_id.is_(None),
                )
            )
        )
        departmental = [row for row in candidates if row.department_id is not None]
        candidates = departmental or [row for row in candidates if row.department_id is None]
        if len(candidates) != 1:
            raise failure()
        record = candidates[0]
    if record is None or record.tested_version != record.config_revision:
        raise failure()
    scan = scanner(db, request) if request is not None else None
    if scan is None:
        from app.core.evidence import ClamAV

        antivirus = db.scalar(select(IntegrationConfig).where(IntegrationConfig.kind == "clamav"))
        if (
            antivirus is None
            or not antivirus.is_active
            or (antivirus.tested_version != antivirus.config_revision)
        ):
            raise failure()
        scan = ClamAV(antivirus.config["port"], antivirus.config["timeout"])
    if record.kind == "object_storage":
        if not historical:
            require_module(db, "integrations")
        return RemoteEvidenceStore(client_for(db, record, request), scan, record)
    from pathlib import Path

    root = Path(record.config["root"])
    private_root(root)
    store = EvidenceStore(root, scan)
    store.configuration_id, store.configuration_version = record.id, record.config_revision
    return store
