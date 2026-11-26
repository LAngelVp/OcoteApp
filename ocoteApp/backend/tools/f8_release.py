"""Guarded local F8 release; preserves the existing instance and every historical value."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings
from app.core.security import CONFIG_LOCK
from app.services.platform import seal_path
from tools import f1_local as local
from tools import f2_local as previous
from tools.f7_release import verify_vault

SOURCE, HEAD = "20261125_0006", "20261125_0007"
ADDED = {
    "security_policies",
    "feature_flags",
    "private_assets",
    "organization_profiles",
    "calendar_configs",
    "calendar_holidays",
}


def preserved(before, after, *, ledger=False):
    for table, rows in before["rows"].items():
        if table == "alembic_version":
            continue
        original = [json.loads(row) for row in rows]
        current = [json.loads(row) for row in after["rows"][table]]
        if not original:
            if current and not (ledger and table == "release_history"):
                raise RuntimeError("Unexpected records in historical table: " + table)
            continue
        keys = set(original[0])
        if any(not keys <= set(row) for row in current):
            raise RuntimeError("Historical column removed: " + table)
        expected = sorted(local.canonical(row) for row in original)
        projected = sorted(local.canonical({key: row[key] for key in keys}) for row in current)
        if (
            not set(expected) <= set(projected)
            if ledger and table == "release_history"
            else expected != projected
        ):
            raise RuntimeError("Historical value changed: " + table)


def upgraded(before, after):
    if set(after["tables"]) - set(before["tables"]) != ADDED:
        raise RuntimeError("Unexpected F8 table set")
    if after["rows"]["alembic_version"] != ['{"version_num": "20261125_0007"}']:
        raise RuntimeError("Unexpected F8 revision")
    if any(after["rows"][table] for table in ADDED):
        raise RuntimeError("Unsolicited F8 settings/defaults")
    preserved(before, after)


def verify_runtime(database):
    with local.role_connection(Settings().database_url.get_secret_value(), database) as db:
        for table in ADDED:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                expected = privilege in {"SELECT", "INSERT"} or (
                    privilege == "UPDATE" and table != "private_assets"
                )
                actual = db.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)
                ).fetchone()[0]
                if actual != expected:
                    raise RuntimeError("Unexpected F8 runtime privilege")


def index_signature(db):
    shape = db.execute(
        "SELECT i.indisunique,i.indisprimary,i.indisvalid,i.indisready,"
        "i.indnullsnotdistinct,i.indkey::text,i.indclass::text,i.indcollation::text,"
        "i.indoption::text,i.indnatts,i.indnkeyatts,am.amname,t.relname "
        "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
        "JOIN pg_class t ON t.oid=i.indrelid JOIN pg_am am ON am.oid=c.relam "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname='uq_f8_local_kind'"
    ).fetchone()
    predicate = db.execute(
        "SELECT pg_get_expr(i.indpred,i.indrelid) FROM pg_index i "
        "JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname='uq_f8_local_kind'"
    ).fetchone()[0]
    truth = tuple(
        db.execute(
            sql.SQL("SELECT {} FROM (SELECT %s::varchar(30) kind) candidate").format(
                sql.SQL(predicate)
            ),
            (kind,),
        ).fetchone()[0]
        for kind in ("local_storage", "clamav", "object_storage")
    )
    if not shape or shape[-1] != "integration_configs" or truth != (True, True, False):
        raise RuntimeError("Unexpected local-provider unique index semantics")
    return shape, truth


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
            recovered = previous.snapshot(db)
            if recovered != before:
                changed = ",".join(key for key in before if recovered[key] != before[key])
                if changed == "indexes":
                    differing = {
                        entry[0] for entry in before["indexes"] if entry not in recovered["indexes"]
                    } | {
                        entry[0] for entry in recovered["indexes"] if entry not in before["indexes"]
                    }
                    if differing != {"uq_f8_local_kind"}:
                        raise RuntimeError("Unexpected restored index difference")
                    with local.role_connection(url) as source:
                        if index_signature(source) != index_signature(db):
                            raise RuntimeError("Restored index semantics differ")
                    local.journal(
                        directory,
                        "f8_index_restore_equivalent",
                        index="uq_f8_local_kind",
                        exhaustive_kind_domain=True,
                    )
                else:
                    raise RuntimeError("Restored schema/data differs: " + changed)
            if upgrade:
                previous.upgrade(destination, HEAD)
                after = previous.snapshot(db)
                upgraded(before, after)
                previous.upgrade(destination, HEAD)
                if previous.snapshot(db) != after:
                    raise RuntimeError("Restored upgrade is not a no-op")
                verify_runtime(destination)
        if root_seal is not None:
            verify_vault(destination, root_seal)
    local.journal(
        directory,
        "f8_restore_verified",
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
            raise RuntimeError("Only source 0006 is authorized; never repeat apply")
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
                raise RuntimeError("Insufficient space for verified backups")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f8-" + str(attempt))
            local.private_directory(directory)
            local.write_private(directory / "events.jsonl", b"")
            local.private_directory(local.LOCAL)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt, "phase": "F8"}))
            try:
                admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
                before, catalog, legacy = (
                    previous.snapshot(admin),
                    local.catalog(admin),
                    local.legacy_catalog(admin),
                )
                instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
                root_path = seal_path(instance)
                root_hash = local.digest(root_path)
                local.write_private(directory / "master.dpapi", root_path.read_bytes())
                files = {
                    path.relative_to(local.ROOT).as_posix(): local.digest(path)
                    for folder in ("backend/app", "backend/alembic", "src", "public/logos")
                    for path in (local.ROOT / folder).rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                }
                manifest = {
                    "files": files,
                    "source_revision": SOURCE,
                    "target_revision": HEAD,
                    "scope": "local_only",
                    "customer_package": False,
                }
                local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
                local.journal(directory, "f8_started", attempt=attempt, request_id=request_id)
                verified = backup(admin, directory, "before", upgrade=True, root_seal=root_path)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                migrated = previous.snapshot(admin)
                upgraded(before, migrated)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                if previous.snapshot(admin) != migrated:
                    raise RuntimeError("Source second upgrade changed state")
                verify_runtime(local.DATABASE_NAME)
                verify_vault(local.DATABASE_NAME, root_path)
                url = MigrationSettings().migration_database_url.get_secret_value()
                with local.role_connection(url) as db:
                    db.execute(
                        "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES(%s,%s,%s,'0.8.0',%s,%s,%s,%s,%s,'local','validation',"
                        "'running',%s,%s,%s)",
                        (
                            attempt,
                            started,
                            local.now(),
                            hashlib.sha256(local.canonical(files)).hexdigest(),
                            local.digest(directory / "artifact-manifest.json"),
                            SOURCE,
                            HEAD,
                            "LUIS ANGEL VALLEJO - DESARROLLADOR",
                            local.digest(directory / "before-manifest.json"),
                            verified["verified_at"],
                            request_id,
                        ),
                    )
                backup(admin, directory, "recorded", root_seal=root_path)
                with local.role_connection(url) as db:
                    changed = db.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,"
                        "finished_at=%s,status='succeeded',phase='complete',"
                        "result_code='F8_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Own terminal release transition failed")
                backup(admin, directory, "terminal", root_seal=root_path)
                preserved(before, previous.snapshot(admin), ledger=True)
                if (
                    local.catalog(admin) != catalog
                    or local.legacy_catalog(admin) != legacy
                    or local.digest(root_path) != root_hash
                ):
                    raise RuntimeError("Database identity/legacy/root changed")
                local.journal(
                    directory,
                    "f8_succeeded",
                    attempt=attempt,
                    revision=HEAD,
                    instance_id=instance,
                    tables=32,
                    historical_values_preserved=True,
                )
                local.MARKER.unlink()
                print("F8 verified: " + str(directory))
            except Exception as error:
                local.journal(
                    directory,
                    "f8_failed",
                    error_type=type(error).__name__,
                    maintenance_retained=True,
                )
                raise
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def resume(artifacts):
    directory = Path(artifacts).resolve()
    if directory.is_relative_to(local.ROOT) or directory.is_symlink():
        raise RuntimeError("Private attempt directory required")
    marker = json.loads(local.MARKER.read_bytes())
    attempt = UUID(marker["attempt"])
    if marker.get("phase") != "F8" or directory.name != "f8-" + str(attempt):
        raise RuntimeError("Only the matching interrupted F8 attempt may resume")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(HEAD,)]:
            raise RuntimeError("Resume never migrates; exact applied0007 required")
        own = admin.execute(
            "SELECT status,target_revision FROM release_history WHERE id=%s", (attempt,)
        ).fetchone()
        if own != ("running", HEAD):
            raise RuntimeError("Own running F8 record required; no terminal rewrite")
        if admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid()"
        ).fetchone()[0]:
            raise RuntimeError("Drain all writers before resume")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Release lock held")
        try:
            admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
            current = previous.snapshot(admin)
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
                        str(directory / "before.dump"),
                    ],
                    make_url(url).password,
                )
                with local.role_connection(url, destination) as recovered:
                    original = previous.snapshot(recovered)
                manifest = json.loads((directory / "before-manifest.json").read_bytes())
                if (
                    hashlib.sha256(local.canonical(original)).hexdigest()
                    != manifest["snapshot_sha256"]
                ):
                    raise RuntimeError("Original verified snapshot changed")
                preserved(original, current, ledger=True)
                verify_vault(destination, directory / "master.dpapi")
            instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
            root_path = seal_path(instance)
            if local.digest(root_path) != local.digest(directory / "master.dpapi"):
                raise RuntimeError("Existing instance root changed")
            verify_runtime(local.DATABASE_NAME)
            backup(admin, directory, "resumed", root_seal=root_path)
            with local.role_connection(url) as db:
                changed = db.execute(
                    "UPDATE release_history SET version=version+1,updated_at=%s,"
                    "finished_at=%s,status='succeeded',phase='complete',"
                    "result_code='F8_LOCAL_VERIFIED' "
                    "WHERE id=%s AND version=1 AND status='running'",
                    (local.now(), local.now(), attempt),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Own terminal transition failed")
            backup(admin, directory, "terminal", root_seal=root_path)
            preserved(original, previous.snapshot(admin), ledger=True)
            local.journal(
                directory,
                "f8_resumed_succeeded",
                attempt=attempt,
                revision=HEAD,
                instance_id=instance,
                tables=32,
                historical_values_preserved=True,
            )
            local.MARKER.unlink()
            print("F8 verified: " + str(directory))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))
