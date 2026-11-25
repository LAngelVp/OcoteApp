"""F7 local-only release; not a customer installer or package builder."""

import hashlib
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import MigrationSettings, Settings
from app.core.security import CONFIG_LOCK
from app.core.vault import OSSealedFile, Vault
from app.main import create_app
from app.models.platform import DeploymentInstance, EncryptedSecret, SecretKeyVersion
from app.services.platform import encrypted, seal_path, wrapped
from tools import f1_local as local
from tools import f2_local as previous

HEAD, SOURCE = "20261125_0006", "20261125_0005"
OPERATOR = "LUIS ANGEL VALLEJO - DESARROLLADOR"
ADDED = {
    "deployment_instances",
    "configuration_revisions",
    "secret_key_versions",
    "encrypted_secrets",
    "integration_configs",
    "integration_health_checks",
}


def preserved(before, after, *, ledger=False):
    for table, rows in before["rows"].items():
        if table == "alembic_version":
            continue
        if ledger and table == "release_history":
            if not set(rows) <= set(after["rows"][table]):
                raise RuntimeError("Historical release changed")
        elif rows != after["rows"].get(table):
            raise RuntimeError("Existing data changed: " + table)
    for key in ("columns", "constraints", "indexes", "functions", "triggers"):
        if not set(map(local.canonical, before[key])) <= set(map(local.canonical, after[key])):
            raise RuntimeError("Existing schema object changed: " + key)


def upgraded(before, after):
    if set(after["tables"]) - set(before["tables"]) != ADDED:
        raise RuntimeError("Unexpected F7 table set")
    if after["rows"]["alembic_version"] != ['{"version_num": "20261125_0006"}']:
        raise RuntimeError("Unexpected F7 revision")
    if any(after["rows"][table] for table in ADDED):
        raise RuntimeError("Unsolicited F7 configuration")
    preserved(before, after)


def verify_runtime(database):
    with local.role_connection(Settings().database_url.get_secret_value(), database) as db:
        for table in ADDED:
            allowed = {"SELECT", "INSERT"}
            if table == "deployment_instances":
                allowed = {"SELECT", "UPDATE"}
            elif table == "integration_configs":
                allowed.add("UPDATE")
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                actual = db.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)
                ).fetchone()[0]
                if actual != (privilege in allowed):
                    raise RuntimeError("Unexpected F7 runtime grant")


def initialize_vault(database=local.DATABASE_NAME):
    engine = previous.migration_engine(database)
    identity = uuid4()
    path = seal_path(identity)
    try:
        with Session(engine) as db, db.begin():
            if db.scalar(select(DeploymentInstance)) is not None:
                raise RuntimeError("Vault already initialized; no overwrite authorized")
            local.private_directory(path.parent)
            root = os.urandom(32)
            OSSealedFile(path, identity).create(root)
            if OSSealedFile(path, identity).read() != root:
                raise RuntimeError("Root seal verification failed")
            db.add(DeploymentInstance(id=identity, root_key_ref="windows-dpapi-v1"))
        return identity, path
    finally:
        engine.dispose()


def verify_vault(database, path):
    engine = previous.migration_engine(database)
    try:
        with Session(engine) as db:
            record = db.scalar(select(DeploymentInstance))
            if record is None:
                raise RuntimeError("Missing instance identity")
            crypt = Vault(OSSealedFile(path, record.id).read(), record.id, record.root_key_ref)
            for value in db.scalars(select(EncryptedSecret)):
                crypt.decrypt(wrapped(db.get(SecretKeyVersion, value.key_id)), encrypted(value))
    finally:
        engine.dispose()


def check_release():
    from fastapi.testclient import TestClient

    with previous.isolated_database() as name:
        previous.upgrade(name, SOURCE)
        url = MigrationSettings().migration_database_url.get_secret_value()
        with local.role_connection(url, name) as db:
            before = previous.snapshot(db)
            previous.upgrade(name, HEAD)
            after = previous.snapshot(db)
            upgraded(before, after)
            previous.upgrade(name, HEAD)
            if previous.snapshot(db) != after:
                raise RuntimeError("Isolated upgrade is not a no-op")
        verify_runtime(name)
        _, path = initialize_vault(name)
        try:
            verify_vault(name, path)
            engine = previous.migration_engine(name)
            try:
                with Session(engine) as db, db.begin():
                    instance = db.scalar(select(DeploymentInstance))
                    crypt = Vault(
                        OSSealedFile(path, instance.id).read(), instance.id, instance.root_key_ref
                    )
                    key = crypt.new_key("backup", 1)
                    db.add(
                        SecretKeyVersion(
                            id=key.id,
                            instance_id=key.instance_id,
                            purpose=key.purpose,
                            epoch=key.epoch,
                            root_key_ref=key.root_key_ref,
                            algorithm="AES-256-GCM",
                            nonce=key.nonce,
                            wrapped_dek=key.wrapped_dek,
                        )
                    )
                    db.flush()
                    value = crypt.encrypt(key, uuid4(), 1, b"synthetic restored vault proof")
                    db.add(
                        EncryptedSecret(
                            owner_id=value.owner_id,
                            purpose="backup",
                            secret_version=1,
                            key_id=key.id,
                            nonce=value.nonce,
                            ciphertext=value.ciphertext,
                        )
                    )
                with local.role_connection(url, name) as db:
                    baseline = previous.snapshot(db)
                with TemporaryDirectory(prefix="ocote-f7-vault-") as temporary:
                    directory = Path(temporary)
                    local.protect(directory)
                    local.write_private(directory / "events.jsonl", b"")
                    local.write_private(directory / "isolated.dump", b"")
                    previous.pg_run(
                        [
                            str(local.PG_BIN / "pg_dump"),
                            "-w",
                            "-h",
                            "127.0.0.1",
                            "-p",
                            "5432",
                            "-U",
                            local.MIGRATOR,
                            "-d",
                            name,
                            "--format=custom",
                            "--file=" + str(directory / "isolated.dump"),
                        ],
                        make_url(url).password,
                    )
                    local.write_private(directory / "master.dpapi", path.read_bytes())
                    restored(directory, "isolated", baseline, root_seal=directory / "master.dpapi")
            finally:
                engine.dispose()
            with TestClient(create_app()) as client:
                if client.get("/api/v1/health/live").json() != {"status": "alive"}:
                    raise RuntimeError("Liveness smoke failed")
        finally:
            path.unlink()
            path.parent.rmdir()
    print("F7 isolated migration/no-op/grants/DPAPI bootstrap: PASS")


def restored(directory, label, before, *, upgrade=False, root_seal=None):
    url = MigrationSettings().migration_database_url.get_secret_value()
    with previous.isolated_database("restore") as destination:
        previous.pg_run(
            [
                str(local.PG_BIN / "pg_restore"),
                "-w",
                "-h",
                "127.0.0.1",
                "-p",
                "5432",
                "-U",
                local.MIGRATOR,
                "-d",
                destination,
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                str(directory / (label + ".dump")),
            ],
            make_url(url).password,
        )
        with local.role_connection(url, destination) as db:
            if previous.snapshot(db) != before:
                raise RuntimeError("Restored schema/data differs")
            if upgrade:
                previous.upgrade(destination, HEAD)
                after = previous.snapshot(db)
                upgraded(before, after)
                previous.upgrade(destination, HEAD)
                if previous.snapshot(db) != after:
                    raise RuntimeError("Restored upgrade is not a no-op")
        if root_seal is not None:
            verify_vault(destination, root_seal)
    local.journal(
        directory,
        "f7_restore_verified",
        label=label,
        upgraded=upgrade,
        vault_verified=root_seal is not None,
    )


def backup(admin, directory, label, *, upgrade=False, root_seal=None):
    baseline = previous.snapshot(admin)
    path = directory / (label + ".dump")
    local.write_private(path, b"")
    previous.pg_run(
        [
            str(local.PG_BIN / "pg_dump"),
            "-w",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            local.DATABASE_NAME,
            "--format=custom",
            "--file=" + str(path),
        ],
        os.environ["PGPASSWORD"],
    )
    restored(directory, label, baseline, upgrade=upgrade, root_seal=root_seal)
    if previous.snapshot(admin) != baseline:
        raise RuntimeError("Source changed during backup")
    metadata = {
        "sha256": local.digest(path),
        "bytes": path.stat().st_size,
        "verified_at": local.now(),
        "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest(),
    }
    local.write_private(directory / (label + "-manifest.json"), local.canonical(metadata))
    return metadata


def apply(artifacts):
    root = Path(artifacts).resolve()
    if root == local.ROOT or root.is_relative_to(local.ROOT) or root.is_symlink():
        raise RuntimeError("Artifacts must be private and outside checkout")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Existing maintenance must be investigated")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only source 0005 is authorized")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Release lock held")
        try:
            if admin.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Drain API/all writers before release")
            local.private_directory(root)
            size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            if shutil.disk_usage(root).free < size * 6 + 134217728:
                raise RuntimeError("Insufficient space for backup/restores")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f7-" + str(attempt))
            local.private_directory(directory)
            local.write_private(directory / "events.jsonl", b"")
            local.private_directory(local.LOCAL)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt, "phase": "F7"}))
            local.journal(directory, "f7_started", attempt=attempt, request_id=request_id)
            try:
                admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
                catalog, legacy = local.catalog(admin), local.legacy_catalog(admin)
                before = previous.snapshot(admin)
                files = {
                    path.relative_to(local.ROOT).as_posix(): local.digest(path)
                    for folder in ("backend/app", "backend/alembic", "src")
                    for path in (local.ROOT / folder).rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                }
                artifact_hash = hashlib.sha256(local.canonical(files)).hexdigest()
                local.write_private(
                    directory / "artifact-manifest.json",
                    local.canonical(
                        {
                            "files": files,
                            "target_revision": HEAD,
                            "source_revision": SOURCE,
                            "scope": "local_synthetic_only",
                            "customer_package": False,
                        }
                    ),
                )
                verified = backup(admin, directory, "before", upgrade=True)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                migrated = previous.snapshot(admin)
                upgraded(before, migrated)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                if previous.snapshot(admin) != migrated:
                    raise RuntimeError("Source second upgrade changed state")
                verify_runtime(local.DATABASE_NAME)
                identity, root_path = initialize_vault()
                local.write_private(directory / "master.dpapi", root_path.read_bytes())
                verify_vault(local.DATABASE_NAME, root_path)
                url = MigrationSettings().migration_database_url.get_secret_value()
                with local.role_connection(url) as db:
                    db.execute(
                        "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES(%s,%s,%s,'0.7.0',%s,%s,%s,%s,%s,'local','validation',"
                        "'running',%s,%s,%s)",
                        (
                            attempt,
                            started,
                            local.now(),
                            artifact_hash,
                            local.digest(directory / "artifact-manifest.json"),
                            SOURCE,
                            HEAD,
                            OPERATOR,
                            local.digest(directory / "before-manifest.json"),
                            verified["verified_at"],
                            request_id,
                        ),
                    )
                backup(admin, directory, "recorded", root_seal=directory / "master.dpapi")
                with local.role_connection(url) as db:
                    changed = db.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F7_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Own terminal release transition failed")
                backup(admin, directory, "terminal", root_seal=directory / "master.dpapi")
                preserved(before, previous.snapshot(admin), ledger=True)
                if local.catalog(admin) != catalog or local.legacy_catalog(admin) != legacy:
                    raise RuntimeError("Database identity/legacy changed")
                local.journal(
                    directory,
                    "f7_succeeded",
                    attempt=attempt,
                    revision=HEAD,
                    instance_id=identity,
                    tables=len(previous.snapshot(admin)["tables"]),
                    legacy_rows_preserved=True,
                    seconds=(local.now() - started).total_seconds(),
                )
                local.MARKER.unlink()
                print("F7 verified: " + str(directory))
            except Exception as error:
                local.journal(
                    directory,
                    "f7_failed",
                    error_type=type(error).__name__,
                    maintenance_retained=True,
                )
                raise
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))
