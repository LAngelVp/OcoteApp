import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.errors import CommandError
from app.core.evidence import ClamAV, EvidenceStore, failure, private_root
from app.core.vault import ALGORITHM, EncryptedValue, OSSealedFile, Vault, WrappedKey
from app.models.platform import (
    ConfigurationRevision,
    DeploymentInstance,
    EncryptedSecret,
    IntegrationConfig,
    IntegrationHealthCheck,
    SecretKeyVersion,
)
from app.schemas.platform import ClamAVConfig, LocalStorage
from app.services.administration import check_version
from app.services.identity import audit, touch


def instance(db, *, lock=False):
    query = select(DeploymentInstance)
    record = db.scalar(query.with_for_update() if lock else query)
    if record is None:
        raise CommandError(503, "VAULT_NOT_INITIALIZED")
    return record


def seal_path(identity):
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "OS_SEAL_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "vault" / str(identity) / "master.dpapi"


def vault(db, request=None):
    record = instance(db)
    injected = getattr(request.app.state, "vault", None) if request is not None else None
    if injected is not None:
        return injected
    return Vault(
        OSSealedFile(seal_path(record.id), record.id).read(), record.id, record.root_key_ref
    )


def revision(db, request, actor, record, reason, changed):
    db.add(
        ConfigurationRevision(
            actor_id=actor.id,
            request_id=UUID(request.state.request_id),
            entity_id=record.id,
            entity_type=record.__tablename__,
            reason=reason,
            changed_keys=sorted(changed),
        )
    )
    audit(
        db,
        request,
        "administration_changed",
        actor=actor.id,
        entity=record.__tablename__,
        entity_id=record.id,
        after={"changed_keys": sorted(changed), "reason": reason},
    )


def custody_view(record):
    fields = ("primary_name", "primary_contact", "backup_name", "backup_contact")
    return {
        "id": record.id,
        "version": record.version,
        **{name: getattr(record, name) for name in fields},
        "custody_complete": all(getattr(record, name) for name in fields),
    }


def update_custody(db, body, request, actor):
    record = instance(db, lock=True)
    check_version(record, body.expected_version)
    values = body.model_dump(exclude={"expected_version", "reason"})
    for key, value in values.items():
        setattr(record, key, value)
    touch(record)
    revision(db, request, actor, record, body.reason, values)
    db.flush()
    return custody_view(record)


def integration_view(record):
    return {
        name: getattr(record, name)
        for name in (
            "id",
            "kind",
            "version",
            "config",
            "config_revision",
            "is_active",
            "tested_version",
            "tested_at",
        )
    }


def integration(db, kind):
    record = db.scalar(
        select(IntegrationConfig).where(IntegrationConfig.kind == kind).with_for_update()
    )
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def save_integration(db, kind, body, request, actor):
    expected = LocalStorage if kind == "local_storage" else ClamAVConfig
    if not isinstance(body.config, expected):
        raise CommandError(422, "INVALID_INTEGRATION_CONFIGURATION")
    record = db.scalar(
        select(IntegrationConfig).where(IntegrationConfig.kind == kind).with_for_update()
    )
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    values = body.config.model_dump()
    if record is None:
        record = IntegrationConfig(id=uuid4(), kind=kind, config=values)
        db.add(record)
    else:
        if record.config != values:
            if kind == "local_storage":
                from app.models.operations import EvidenceFile

                if db.scalar(select(func.count()).select_from(EvidenceFile)):
                    raise CommandError(409, "EVIDENCE_STORAGE_MIGRATION_REQUIRED")
            record.config_revision += 1
        record.config = values
        record.is_active = False
        record.tested_version = record.tested_at = None
        touch(record)
    revision(db, request, actor, record, body.reason, values)
    db.flush()
    return integration_view(record)


def probe_local(config):
    root = Path(config["root"])
    for directory in (root, root / "quarantine", root / "objects"):
        private_root(directory)
    path = root / (".ocote-probe-" + uuid4().hex)
    content = os.urandom(64)
    created = False
    try:
        with path.open("xb") as output:
            created = True
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise failure()
    finally:
        if created:
            path.unlink()


def probe_clamav(config):
    scanner = ClamAV(config["port"], config["timeout"])
    scanner(b"OCOTE clean scanner probe")
    sample = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    try:
        scanner(sample)
    except CommandError as error:
        if error.code == "MALWARE_DETECTED":
            return
        raise
    raise failure()


def test_integration(db, kind, body, request, actor):
    record = integration(db, kind)
    check_version(record, body.expected_version)
    passed = False
    try:
        (probe_local if kind == "local_storage" else probe_clamav)(record.config)
        passed = True
    except (CommandError, OSError, ValueError, subprocess.SubprocessError):
        pass
    record.is_active = False
    record.tested_version = record.config_revision if passed else None
    record.tested_at = datetime.now(UTC) if passed else None
    touch(record)
    code = "VERIFIED" if passed else "PROVIDER_UNAVAILABLE_OR_UNSAFE"
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
    revision(db, request, actor, record, body.reason, ["verification"])
    db.flush()
    return {**integration_view(record), "passed": passed, "result_code": code}


def activate_integration(db, kind, body, request, actor):
    record = integration(db, kind)
    check_version(record, body.expected_version)
    if body.is_active and (
        record.tested_version != record.config_revision
        or record.tested_at is None
        or datetime.now(UTC) - record.tested_at > timedelta(minutes=15)
    ):
        raise CommandError(409, "FRESH_VERIFICATION_REQUIRED")
    record.is_active = body.is_active
    touch(record)
    revision(db, request, actor, record, body.reason, ["is_active"])
    db.flush()
    return integration_view(record)


def configured_store(db):
    records = {row.kind: row for row in db.scalars(select(IntegrationConfig))}
    if set(records) != {"local_storage", "clamav"} or any(
        not row.is_active or row.tested_version != row.config_revision for row in records.values()
    ):
        raise failure()
    storage, scanner = records["local_storage"].config, records["clamav"].config
    root = Path(storage["root"])
    private_root(root)
    return EvidenceStore(root, ClamAV(scanner["port"], scanner["timeout"]))


def wrapped(record):
    return WrappedKey(
        record.id,
        record.instance_id,
        record.purpose,
        record.epoch,
        record.root_key_ref,
        record.nonce,
        record.wrapped_dek,
    )


def encrypted(record):
    return EncryptedValue(
        record.key_id, record.owner_id, record.secret_version, record.nonce, record.ciphertext
    )


def new_key(db, crypt, purpose, epoch):
    key = crypt.new_key(purpose, epoch)
    record = SecretKeyVersion(
        id=key.id,
        instance_id=key.instance_id,
        purpose=purpose,
        epoch=epoch,
        root_key_ref=key.root_key_ref,
        algorithm=ALGORITHM,
        nonce=key.nonce,
        wrapped_dek=key.wrapped_dek,
    )
    db.add(record)
    db.flush()
    return record


def secret_view(record):
    return {
        "owner_id": record.owner_id,
        "purpose": record.purpose,
        "version": record.secret_version,
        "configured": True,
        "rotated_at": record.created_at,
    }


def write_secret(db, owner, purpose, body, request, actor):
    crypt = vault(db, request)
    previous = db.scalar(
        select(EncryptedSecret)
        .where(
            EncryptedSecret.owner_id == owner,
            EncryptedSecret.purpose == purpose,
        )
        .order_by(EncryptedSecret.secret_version.desc())
        .limit(1)
    )
    current = previous.secret_version if previous else 0
    if current != body.expected_version:
        raise CommandError(409, "VERSION_CONFLICT")
    key = db.scalar(
        select(SecretKeyVersion)
        .where(SecretKeyVersion.purpose == purpose)
        .order_by(SecretKeyVersion.epoch.desc())
        .limit(1)
    )
    if key is None:
        key = new_key(db, crypt, purpose, 1)
    value = crypt.encrypt(
        wrapped(key), owner, current + 1, body.value.get_secret_value().encode("utf-8")
    )
    record = EncryptedSecret(
        id=uuid4(),
        owner_id=owner,
        purpose=purpose,
        secret_version=value.version,
        key_id=value.key_id,
        nonce=value.nonce,
        ciphertext=value.ciphertext,
    )
    db.add(record)
    revision(db, request, actor, record, body.reason, ["value_replaced"])
    db.flush()
    return secret_view(record)


def rotate(db, body, request, actor):
    crypt = vault(db, request)
    previous = db.scalar(
        select(SecretKeyVersion)
        .where(SecretKeyVersion.purpose == body.purpose)
        .order_by(SecretKeyVersion.epoch.desc())
        .limit(1)
    )
    if previous is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if previous.epoch != body.expected_version:
        raise CommandError(409, "VERSION_CONFLICT")
    values = list(
        db.scalars(
            select(EncryptedSecret)
            .where(EncryptedSecret.purpose == body.purpose)
            .distinct(EncryptedSecret.owner_id)
            .order_by(EncryptedSecret.owner_id, EncryptedSecret.secret_version.desc())
            .limit(101)
        )
    )
    if len(values) > 100:
        raise CommandError(413, "ROTATION_LIMIT_EXCEEDED")
    key = new_key(db, crypt, body.purpose, previous.epoch + 1)
    for old in values:
        old_key = db.get(SecretKeyVersion, old.key_id)
        content = crypt.decrypt(wrapped(old_key), encrypted(old))
        value = crypt.encrypt(wrapped(key), old.owner_id, old.secret_version + 1, content)
        db.add(
            EncryptedSecret(
                owner_id=old.owner_id,
                purpose=old.purpose,
                secret_version=value.version,
                key_id=value.key_id,
                nonce=value.nonce,
                ciphertext=value.ciphertext,
            )
        )
    revision(db, request, actor, key, body.reason, ["dek_rotation"])
    db.flush()
    return {"purpose": body.purpose, "epoch": key.epoch, "rotated_count": len(values)}


def health(db, request):
    record = db.scalar(select(DeploymentInstance))
    available = False
    try:
        crypt = vault(db, request)
        first = db.scalar(select(EncryptedSecret).limit(1))
        if first:
            crypt.decrypt(wrapped(db.get(SecretKeyVersion, first.key_id)), encrypted(first))
        available = True
    except (CommandError, OSError, ValueError):
        pass
    providers = list(db.scalars(select(IntegrationConfig).order_by(IntegrationConfig.kind)))
    views = []
    for provider in providers:
        last = db.scalar(
            select(IntegrationHealthCheck)
            .where(IntegrationHealthCheck.integration_id == provider.id)
            .order_by(IntegrationHealthCheck.created_at.desc(), IntegrationHealthCheck.id)
            .limit(1)
        )
        views.append(
            {
                **integration_view(provider),
                "last_check": {
                    "status": last.status,
                    "result_code": last.result_code,
                    "checked_at": last.created_at,
                    "config_version": last.config_version,
                }
                if last
                else None,
            }
        )
    return {
        "vault_available": available,
        "custody": custody_view(record) if record else None,
        "integrations": views,
        "evidence_configuration_verified": len(providers) == 2
        and all(row.is_active and row.tested_version == row.config_revision for row in providers),
        "customer_operational_acceptance": False,
    }
