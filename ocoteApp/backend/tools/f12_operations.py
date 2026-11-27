"""Explicit local F12 operations agent, never imported as an API executor."""

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import shutil
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from multiprocessing.connection import Listener
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import CommandError
from app.core.operations_agent import decode, envelope, pipe_address
from app.core.vault import OSSealedFile
from app.models.bulk import BackupRecord
from app.models.collaboration import JobRun, ServicePrincipal
from app.models.identity import User
from app.models.platform import IntegrationConfig
from app.services import advanced_operations, bulk, enterprise
from app.services import operations as operation
from tools import f12_local as operator
from tools import f12_release as release

CONTEXT = UUID("7ae6ff08-cead-4513-b626-e2edfae41202")
FORMAT = "ocote-f12-backup-v1"
MAX_ARCHIVE = 107374182400
MAX_SNAPSHOT = 268435456
local, previous, shared = release.local, release.previous, release.shared


def private_path(value):
    path = Path(value)
    if not path.is_absolute() or any(item.is_symlink() or item.is_junction()
                                     for item in (path, *path.parents)) or (
        path.resolve().is_relative_to(local.ROOT.resolve())
    ):
        raise CommandError(422, "PRIVATE_OPERATIONS_DESTINATION_REQUIRED")
    return path.resolve()


def configure(root, instance, principal, destination):
    if not sys.stdin.isatty() or os.environ.get("PGPASSWORD"):
        raise CommandError(503, "VISIBLE_AGENT_CONFIGURATION_REQUIRED")
    root = private_path(root)
    path = root / "agent.dpapi"
    if path.exists():
        raise CommandError(409, "AGENT_CONFIGURATION_EXISTS_NO_OVERWRITE")
    secret = getpass.getpass("Secreto compartido del agente, sin eco: ")
    if not 32 <= len(secret) <= 256 or any(not 33 <= ord(char) <= 126 for char in secret):
        raise CommandError(422, "INVALID_AGENT_AUTHENTICATION")
    payload = {"purpose": "ocote-f12-operations-agent-v1", "instance_id": str(instance),
               "principal_id": str(principal), "destination_ref": str(destination),
               "authentication": secret, "archive_key": base64.b64encode(os.urandom(32)).decode()}
    local.private_directory(root)
    OSSealedFile(path, CONTEXT).create(local.canonical(payload))
    print("F12_AGENT_CONFIGURED_NO_DATABASE_CONNECTION", flush=True)


def configuration(root):
    root = private_path(root)
    try:
        path = root / "agent.dpapi"
        if path.is_symlink() or path.is_junction():
            raise ValueError
        values = json.loads(OSSealedFile(path, CONTEXT).read())
        if values["purpose"] != "ocote-f12-operations-agent-v1":
            raise ValueError
        for field in ("instance_id", "principal_id", "destination_ref"):
            UUID(values[field])
        if len(base64.b64decode(values["archive_key"], validate=True)) != 32:
            raise ValueError
        return root, values
    except (ValueError, KeyError, TypeError, OSError):
        raise CommandError(503, "AGENT_CONFIGURATION_UNAVAILABLE") from None


def aad(instance, location):
    return local.canonical({"format": FORMAT, "instance": str(instance), "location": str(location)})


def encrypt_archive(source, target, key, instance, location):
    if not 1 <= source.stat().st_size <= MAX_ARCHIVE:
        raise CommandError(413, "BACKUP_TOO_LARGE")
    nonce, wrap_nonce, data_key = os.urandom(12), os.urandom(12), os.urandom(32)
    context = aad(instance, location)
    encryptor = Cipher(algorithms.AES(data_key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(context)
    local.write_private(target, b"")
    digest = hashlib.sha256()
    with source.open("rb") as incoming, target.open("wb") as outgoing:
        for chunk in iter(lambda: incoming.read(65536), b""):
            encrypted = encryptor.update(chunk)
            digest.update(encrypted)
            outgoing.write(encrypted)
        final = encryptor.finalize()
        outgoing.write(final)
        digest.update(final)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return {"format": FORMAT, "instance": str(instance), "location": str(location),
            "nonce": nonce.hex(), "tag": encryptor.tag.hex(), "wrap_nonce": wrap_nonce.hex(),
            "wrapped_key": AESGCM(key).encrypt(wrap_nonce, data_key, context).hex(),
            "cipher_sha256": digest.hexdigest(), "bytes": target.stat().st_size}


def decrypt_archive(source, target, key, metadata, instance, location):
    if target.exists() or target.is_symlink():
        raise CommandError(409, "BACKUP_TARGET_ALREADY_EXISTS")
    try:
        if metadata["format"] != FORMAT or metadata["instance"] != str(instance) or (
            metadata["location"] != str(location) or source.stat().st_size != metadata["bytes"]
            or source.stat().st_size > MAX_ARCHIVE
            or local.digest(source) != metadata["cipher_sha256"]
        ):
            raise ValueError
        context = aad(instance, location)
        data_key = AESGCM(key).decrypt(bytes.fromhex(metadata["wrap_nonce"]),
                                        bytes.fromhex(metadata["wrapped_key"]), context)
        decryptor = Cipher(algorithms.AES(data_key), modes.GCM(
            bytes.fromhex(metadata["nonce"]), bytes.fromhex(metadata["tag"]),
        )).decryptor()
        decryptor.authenticate_additional_data(context)
        local.write_private(target, b"")
        with source.open("rb") as incoming, target.open("wb") as outgoing:
            for chunk in iter(lambda: incoming.read(65536), b""):
                outgoing.write(decryptor.update(chunk))
            outgoing.write(decryptor.finalize())
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise CommandError(503, "BACKUP_AUTHENTICATION_FAILED") from None


def known_catalog(connection):
    signatures = {"uq_f8_local_kind": shared.index_signature,
                  "uq_f11_provider_name_scope": shared.provider_index_signature}
    return {"indexes": {name: {"signature": signature(connection),
                               "properties": shared.index_properties(connection, name)}
                         for name, signature in signatures.items()},
            "triggers": {name: shared.trigger_properties(connection, name)
                         for name in shared.TRIGGER_GUARDS}}


def pack(directory, baseline, security, root_seal, catalog):
    payload = local.canonical({"snapshot": baseline, "security": security,
                               "known_catalog": catalog})
    if len(payload) > MAX_SNAPSHOT:
        raise CommandError(413, "BACKUP_SNAPSHOT_TOO_LARGE")
    local.write_private(directory / "snapshot.json", payload)
    local.write_private(directory / "master.dpapi", root_seal.read_bytes())
    destination = directory / "payload.zip"
    local.write_private(destination, b"")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in ("data.dump", "snapshot.json", "master.dpapi"):
            archive.write(directory / name, name)
    return destination


def unpack(source, directory):
    with zipfile.ZipFile(source) as archive:
        expected = {"data.dump", "snapshot.json", "master.dpapi"}
        if set(archive.namelist()) != expected or len(archive.infolist()) != 3 or any(
            entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1
            for entry in archive.infolist()
        ) or archive.getinfo("snapshot.json").file_size > MAX_SNAPSHOT:
            raise CommandError(503, "BACKUP_ARCHIVE_INVALID")
        for name in expected:
            target = directory / name
            local.write_private(target, b"")
            with archive.open(name) as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=65536)
    document = json.loads((directory / "snapshot.json").read_bytes())
    for section in ("columns", "constraints", "indexes", "functions", "triggers"):
        document["snapshot"][section] = [tuple(row) for row in document["snapshot"][section]]
    document["security"] = {name: [tuple(row) for row in rows]
                            for name, rows in document["security"].items()}
    return document


def restore_archive(directory, expected):
    from app.core.config import MigrationSettings

    url = MigrationSettings().migration_database_url.get_secret_value()
    from sqlalchemy.engine import make_url

    with previous.isolated_database("restore") as destination:
        shared.pg_run([str(local.PG_BIN / "pg_restore"), "-w", "-h", "127.0.0.1", "-p", "5432",
                       "-U", local.MIGRATOR, "-d", destination, "--exit-on-error", "--no-owner",
                       str(directory / "data.dump")], make_url(url).password)
        with local.role_connection(url, destination) as restored:
            recovered = previous.snapshot(restored)
            shared.compare_restored(expected["snapshot"], recovered, restored, restored)
            release.require(shared.security_catalog(restored) == expected["security"],
                            "OPERATIONS_RESTORED_SECURITY_DIFFERS")
            release.require(local.canonical(known_catalog(restored)) ==
                            local.canonical(expected["known_catalog"]),
                            "OPERATIONS_RESTORED_GUARD_CATALOG_DIFFERS")
        release.verify_runtime(destination)
        shared.verify_vault(destination, directory / "master.dpapi")


def unit_request(job):
    return SimpleNamespace(state=SimpleNamespace(request_id=str(job.request_id)))


def claim_job(engine, identity, config):
    with Session(engine, expire_on_commit=False) as database, database.begin():
        enterprise.require_module(database, "advanced_operations")
        job = database.scalar(select(JobRun).where(JobRun.id == identity).with_for_update())
        if job is None or job.kind not in {"backup", "restore_verify"} or job.state != "running":
            raise CommandError(409, "OPERATIONS_JOB_NOT_CLAIMABLE")
        actor = database.get(User, job.owner_user_id)
        principal = database.get(ServicePrincipal, job.service_principal_id)
        agent = database.scalar(select(IntegrationConfig).where(
            IntegrationConfig.kind == "operations_agent", IntegrationConfig.is_active,
        ))
        if actor is None or not actor.is_active or actor.role != "admin" or principal is None or (
            not principal.is_active or str(principal.id) != config["principal_id"]
            or agent is None or agent.configuration_revision_id != job.configuration_revision_id
            or agent.tested_version != agent.config_revision
            or agent.config["destination_ref"] != config["destination_ref"]
            or job.operation_payload["destination_ref"] != config["destination_ref"]
            or job.kind not in agent.config["capabilities"] or job.lease_token is not None
            or job.created_at < operation.instant(database) - timedelta(minutes=10)
        ):
            raise CommandError(503, "OPERATIONS_JOB_AUTHORIZATION_CHANGED")
        original = advanced_operations.probe
        advanced_operations.probe = lambda _instance, secret: (
            ["backup", "restore_verify"] if hmac.compare_digest(
                secret, config["authentication"].encode("ascii"),
            ) else []
        )
        try:
            advanced_operations.call_probe(database, agent, SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace()),
            ))
        finally:
            advanced_operations.probe = original
        operation.bump(database, job)
        job.lease_token = uuid4()
        job.lease_until = operation.instant(database) + timedelta(minutes=15)
        bulk.event(database, unit_request(job), actor, job, "f12_job_updated", leased=True)
        return job


def finish_job(engine, identity, result, *, failed=False):
    with Session(engine) as database, database.begin():
        job = database.scalar(select(JobRun).where(JobRun.id == identity).with_for_update())
        if job is None or job.state != "running":
            return
        actor = SimpleNamespace(id=job.owner_user_id)
        if not failed:
            record = BackupRecord(id=uuid4(), job_id=job.id, requested_by=job.owner_user_id,
                                  source_backup_id=(UUID(job.operation_payload["source_backup_id"])
                                                    if job.operation_payload["source_backup_id"]
                                                    else None), **result)
            database.add(record)
            bulk.event(database, unit_request(job), actor, record, "operation_completed",
                       restore_verified=True)
        operation.bump(database, job)
        job.state = "failed" if failed else "succeeded"
        job.lease_token, job.lease_until = None, None
        bulk.event(database, unit_request(job), actor, job, "f12_job_updated", state=job.state)


def run_job(root, identity):
    import time

    release.authorization_budget()
    root, config = configuration(root)
    engine = previous.migration_engine(local.DATABASE_NAME)
    job = None
    marker_created = False
    started = time.monotonic()
    directory = root / str(uuid4())
    try:
        with local.admin_connection() as admin:
            local.verify_identity(admin)
            release.require(admin.execute("SELECT version_num FROM alembic_version").fetchall() ==
                            [(release.HEAD,)], "F12_OPERATIONS_REVISION_REQUIRED")
            release.require(not local.MARKER.exists(), "OPERATIONS_EXISTING_MAINTENANCE")
            release.require(admin.execute("SELECT pg_try_advisory_lock(%s)",
                                          (local.LOCK_KEY,)).fetchone()[0], "OPERATIONS_LOCK_HELD")
            try:
                job = claim_job(engine, identity, config)
                local.private_directory(directory)
                local.write_private(directory / "events.jsonl", b"")
                local.write_private(local.MARKER, local.canonical({"attempt": job.id,
                                                                   "phase": "F12_OPERATION"}))
                marker_created = True
                admin.execute("SELECT pg_advisory_lock(%s)", (release.CONFIG_LOCK,))
                instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
                release.require(str(instance) == config["instance_id"],
                                "OPERATIONS_INSTANCE_DIFFERS")
                root_seal = release.seal_path(instance)
                root_hash = local.digest(root_seal)
                size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
                release.require(shutil.disk_usage(root).free >= size * 6 + 134217728,
                                "OPERATIONS_INSUFFICIENT_SPACE")
                baseline, security = previous.snapshot(admin), shared.security_catalog(admin)
                if job.kind == "backup":
                    release.backup(admin, directory, "data", root_seal=root_seal)
                    payload = pack(directory, baseline, security, root_seal, known_catalog(admin))
                    metadata = encrypt_archive(payload, directory / "archive.enc",
                                               base64.b64decode(config["archive_key"]), instance,
                                               UUID(directory.name))
                    metadata.update(source_revision=release.HEAD,
                                    dump_hash=local.digest(directory / "data.dump"))
                    local.write_private(directory / "archive-manifest.json",
                                        local.canonical(metadata))
                    result = {"instance_id": instance, "source_revision": release.HEAD,
                              "manifest_hash": local.digest(directory / "archive-manifest.json"),
                              "dump_hash": metadata["dump_hash"], "size_bytes": metadata["bytes"],
                              "encrypted_key_ref": "agent-dpapi-v1",
                              "private_location_ref": UUID(directory.name)}
                else:
                    with Session(engine) as database:
                        source = database.get(BackupRecord, UUID(job.operation_payload[
                            "source_backup_id"]))
                        if source is None or source.instance_id != instance:
                            raise CommandError(404, "RESOURCE_NOT_FOUND")
                        location = source.private_location_ref
                        archive = private_path(root / str(location))
                        release.require(local.digest(archive / "archive-manifest.json") ==
                                        source.manifest_hash, "OPERATIONS_BACKUP_MANIFEST_DIFFERS")
                        metadata = json.loads((archive / "archive-manifest.json").read_bytes())
                        result = {field: getattr(source, field) for field in (
                            "instance_id", "source_revision", "manifest_hash", "dump_hash",
                            "size_bytes", "encrypted_key_ref", "private_location_ref",
                        )}
                    decrypt_archive(archive / "archive.enc", directory / "payload.zip",
                                    base64.b64decode(config["archive_key"]), metadata, instance,
                                    location)
                    expected = unpack(directory / "payload.zip", directory)
                    release.require(local.digest(directory / "data.dump") == result["dump_hash"],
                                    "OPERATIONS_BACKUP_DUMP_DIFFERS")
                    restore_archive(directory, expected)
                release.require(previous.snapshot(admin) == baseline and
                                shared.security_catalog(admin) == security and
                                local.digest(root_seal) == root_hash,
                                "OPERATIONS_ORIGIN_CHANGED")
                release.authorization_budget()
                result.update(restore_verified=True,
                              duration_ms=round((time.monotonic() - started) * 1000))
                finish_job(engine, job.id, result)
                local.journal(directory, "f12_operation_verified", job_id=job.id, kind=job.kind)
                local.MARKER.unlink()
                marker_created = False
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (release.CONFIG_LOCK,))
                admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))
    except Exception as error:
        if directory.exists():
            local.journal(directory, "f12_operation_failed", error_type=type(error).__name__,
                          diagnostic=({"code": error.code, **error.details}
                                      if isinstance(error, shared.ReleaseFailure) else None),
                          maintenance_retained=local.MARKER.exists())
        if job is not None:
            finish_job(engine, job.id, {}, failed=True)
        if marker_created:
            print("F12_OPERATIONS_BLOCKED_MAINTENANCE_RETAINED", flush=True)
        raise
    finally:
        engine.dispose()
        if directory.exists():
            for name in ("data.dump", "snapshot.json", "master.dpapi", "payload.zip"):
                (directory / name).unlink(missing_ok=True)


def serve(root):
    if os.name != "nt" or os.environ.get("PGPASSWORD"):
        raise CommandError(503, "LOCAL_AGENT_WITHOUT_ADMIN_ENVIRONMENT_REQUIRED")
    root, config = configuration(root)
    with local.role_connection(Settings().database_url.get_secret_value()) as database:
        if database.execute("SELECT current_user").fetchone() != ("ocote_runtime",) or (
            database.execute("SELECT version_num FROM alembic_version").fetchone() != (
                release.HEAD,
            )
        ):
            raise CommandError(503, "F12_OPERATIONS_REVISION_REQUIRED")
    with Listener(pipe_address(config["instance_id"]), family="AF_PIPE", authkey=None) as listener:
        while True:
            with listener.accept() as connection:
                try:
                    if not connection.poll(5):
                        continue
                    payload = decode(connection.recv_bytes(16384),
                                     config["authentication"].encode())
                    if set(payload) != {"protocol_version", "command", "instance_id", "nonce",
                                        "issued_at"} or payload["command"] != "probe" or (
                        payload["protocol_version"] != 1 or payload["instance_id"] != config[
                            "instance_id"] or abs((datetime.now(UTC) - datetime.fromisoformat(
                                payload["issued_at"])).total_seconds()) > 60
                    ):
                        continue
                    UUID(payload["nonce"])
                    authorization = operator.authorization()
                    available = authorization["expires_at"] - operator.time.time() >= 900
                    connection.send_bytes(envelope({"protocol_version": 1,
                                                    "instance_id": config["instance_id"],
                                                    "nonce": payload["nonce"],
                                                    "capabilities": ["backup", "restore_verify"]
                                                    if available else []},
                                                   config["authentication"].encode()))
                except (CommandError, OSError, ValueError, TypeError):
                    continue
            with local.role_connection(Settings().database_url.get_secret_value()) as database:
                if database.execute("SELECT version_num FROM alembic_version").fetchone() != (
                    release.HEAD,
                ):
                    continue
                jobs = database.execute(
                    "SELECT id FROM job_runs WHERE kind IN ('backup','restore_verify') "
                    "AND state='running' AND lease_token IS NULL AND service_principal_id=%s "
                    "ORDER BY created_at,id LIMIT 1", (UUID(config["principal_id"]),),
                ).fetchall()
            if jobs:
                output = root / ("run-" + str(uuid4()) + ".txt")
                operator.run_authorized(
                    ["-m", "tools.f12_operations", "run-job", "--root", str(root),
                     "--job", str(jobs[0][0])], authorization, output,
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("configure", "serve", "run-job"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--instance", type=UUID)
    parser.add_argument("--principal", type=UUID)
    parser.add_argument("--destination", type=UUID)
    parser.add_argument("--job", type=UUID)
    arguments = parser.parse_args()
    try:
        if arguments.command == "configure":
            if not all((arguments.instance, arguments.principal, arguments.destination)):
                raise CommandError(422, "EXPLICIT_AGENT_IDENTITIES_REQUIRED")
            configure(arguments.root, arguments.instance, arguments.principal,
                      arguments.destination)
        elif arguments.command == "serve":
            serve(arguments.root)
        elif arguments.job:
            run_job(arguments.root, arguments.job)
        else:
            raise CommandError(422, "EXPLICIT_OPERATIONS_JOB_REQUIRED")
        return 0
    except Exception as error:
        print("F12_OPERATIONS_FAILED_" + (error.code if isinstance(error, CommandError)
                                         else type(error).__name__))
        return 1
    finally:
        if arguments.command == "run-job":
            operator.revoke()


if __name__ == "__main__":
    raise SystemExit(main())