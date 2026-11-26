"""One-shot F10 local release with isolated restores and no origin business defaults."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings
from app.core.security import CONFIG_LOCK
from app.services.platform import seal_path
from tools import f1_local as local
from tools import f2_local as previous
from tools.f7_release import verify_vault
from tools.f8_release import index_signature, preserved
from tools.f9_release import verify_runtime as verify_f9_runtime

SOURCE, HEAD = "20261125_0008", "20261126_0009"
ADDED = frozenset(
    {
        "notification_connectors",
        "notification_connector_checks",
        "notification_rules",
        "notification_preferences",
        "notifications",
        "notification_deliveries",
        "notification_dispatches",
        "calendar_feeds",
    }
)
APPEND_ONLY = frozenset({"notification_connector_checks", "notification_dispatches"})


def upgraded(before, after):
    if (
        set(before["tables"]) - set(after["tables"])
        or set(after["tables"]) - set(before["tables"]) != ADDED
    ):
        raise RuntimeError("Unexpected F10 table set")
    if after["rows"]["alembic_version"] != [json.dumps({"version_num": HEAD})]:
        raise RuntimeError("Unexpected F10 revision")
    if any(after["rows"][table] for table in ADDED):
        raise RuntimeError("Unsolicited F10 business defaults")
    preserved(before, after)


def verify_runtime(database):
    verify_f9_runtime(database)
    with local.role_connection(Settings().database_url.get_secret_value(), database) as connection:
        if connection.execute("SELECT current_user").fetchone()[0] != "ocote_runtime":
            raise RuntimeError("Runtime identity required")
        for table in ADDED:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                expected = privilege in {"SELECT", "INSERT"} or (
                    privilege == "UPDATE" and table not in APPEND_ONLY
                )
                actual = connection.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)
                ).fetchone()[0]
                if actual != expected:
                    raise RuntimeError(
                        "Unexpected F10 runtime privilege: " + table + ":" + privilege
                    )


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
                str(directory / (label + ".dump")),
            ],
            make_url(url).password,
        )
        with local.role_connection(url, destination) as connection:
            recovered = previous.snapshot(connection)
            if recovered != before:
                changed = {key for key in before if recovered[key] != before[key]}
                differing = {
                    entry[0] for entry in before["indexes"] if entry not in recovered["indexes"]
                } | {entry[0] for entry in recovered["indexes"] if entry not in before["indexes"]}
                if changed != {"indexes"} or differing != {"uq_f8_local_kind"}:
                    raise RuntimeError("Restored schema/data differs")
                with local.role_connection(url) as source:
                    if index_signature(source) != index_signature(connection):
                        raise RuntimeError("Restored local-provider index semantics differ")
                local.journal(
                    directory, "f10_historical_index_restore_equivalent", index="uq_f8_local_kind"
                )
            if upgrade:
                previous.upgrade(destination, HEAD)
                after = previous.snapshot(connection)
                upgraded(before, after)
                previous.upgrade(destination, HEAD)
                if previous.snapshot(connection) != after:
                    raise RuntimeError("Restored F10 second upgrade is not a no-op")
            verify_runtime(destination)
        if root_seal is not None:
            verify_vault(destination, root_seal)
    local.journal(
        directory,
        "f10_restore_verified",
        label=label,
        upgraded=upgrade,
        vault_verified=root_seal is not None,
    )


def backup(admin, directory, label, *, upgrade=False, root_seal=None):
    baseline = previous.snapshot(admin)
    destination = directory / (label + ".dump")
    local.write_private(destination, b"")
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
            "--file=" + str(destination),
        ],
        os.environ["PGPASSWORD"],
    )
    restored(directory, label, baseline, upgrade=upgrade, root_seal=root_seal)
    if previous.snapshot(admin) != baseline:
        raise RuntimeError("Origin changed during F10 backup/restore")
    metadata = {
        "sha256": local.digest(destination),
        "bytes": destination.stat().st_size,
        "verified_at": local.now(),
        "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest(),
    }
    local.write_private(directory / (label + "-manifest.json"), local.canonical(metadata))
    return metadata


def apply(artifacts):
    supplied = Path(artifacts)
    if not supplied.is_absolute() or supplied.is_symlink() or supplied.is_junction():
        raise RuntimeError("Absolute private F10 artifact directory required")
    root = supplied.resolve()
    if root == local.ROOT or root.is_relative_to(local.ROOT):
        raise RuntimeError("F10 artifacts must remain outside checkout")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Existing maintenance must be investigated")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only source0008 is authorized; never repeat apply0009")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Release lock held")
        try:
            if admin.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Drain API/all writers before F10 release")
            local.private_directory(root)
            size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            if shutil.disk_usage(root).free < size * 6 + 134217728:
                raise RuntimeError("Insufficient space for verified F10 backups")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f10-" + str(attempt))
            local.private_directory(directory)
            local.write_private(directory / "events.jsonl", b"")
            local.private_directory(local.LOCAL)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt, "phase": "F10"}))
            try:
                admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
                before, catalog, legacy = (
                    previous.snapshot(admin),
                    local.catalog(admin),
                    local.legacy_catalog(admin),
                )
                if (
                    len(before["tables"]) != 50
                    or len(before["rows"]["release_history"]) != 9
                    or any(
                        json.loads(row)["status"] not in {"succeeded", "failed"}
                        for row in before["rows"]["release_history"]
                    )
                ):
                    raise RuntimeError("Exact 50-table/9-terminal-release F9 origin required")
                instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
                root_path = seal_path(instance)
                root_hash = local.digest(root_path)
                local.write_private(directory / "master.dpapi", root_path.read_bytes())
                files = {
                    path.relative_to(local.ROOT).as_posix(): local.digest(path)
                    for folder in (
                        "backend/app",
                        "backend/alembic",
                        "backend/tools",
                        "src",
                        "public/logos",
                    )
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
                local.journal(directory, "f10_started", attempt=attempt, request_id=request_id)
                verified = backup(admin, directory, "before", upgrade=True, root_seal=root_path)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                migrated = previous.snapshot(admin)
                upgraded(before, migrated)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                if previous.snapshot(admin) != migrated:
                    raise RuntimeError("Source F10 second upgrade changed state")
                verify_runtime(local.DATABASE_NAME)
                verify_vault(local.DATABASE_NAME, root_path)
                url = MigrationSettings().migration_database_url.get_secret_value()
                with local.role_connection(url) as connection:
                    connection.execute(
                        "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,"
                        "backup_verified_at,request_id) "
                        "VALUES(%s,%s,%s,'0.10.0',%s,%s,%s,%s,%s,'local','validation','running',%s,%s,%s)",
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
                with local.role_connection(url) as connection:
                    changed = connection.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,"
                        "finished_at=%s,status='succeeded',phase='complete',"
                        "result_code='F10_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Own terminal F10 release transition failed")
                backup(admin, directory, "terminal", root_seal=root_path)
                final = previous.snapshot(admin)
                preserved(before, final, ledger=True)
                old_releases = {json.loads(row)["id"] for row in before["rows"]["release_history"]}
                final_releases = {json.loads(row)["id"] for row in final["rows"]["release_history"]}
                if final_releases - old_releases != {str(attempt)} or len(final["tables"]) != 58:
                    raise RuntimeError("Unexpected new F10 release records/table set")
                if (
                    local.catalog(admin) != catalog
                    or local.legacy_catalog(admin) != legacy
                    or local.digest(root_path) != root_hash
                ):
                    raise RuntimeError("Database identity/legacy/root changed")
                if any(final["rows"][table] for table in ADDED):
                    raise RuntimeError("F10 business defaults appeared during release")
                current = {
                    path.relative_to(local.ROOT).as_posix(): local.digest(path)
                    for folder in (
                        "backend/app",
                        "backend/alembic",
                        "backend/tools",
                        "src",
                        "public/logos",
                    )
                    for path in (local.ROOT / folder).rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                }
                if current != files:
                    raise RuntimeError("F10 artifact changed during release")
                local.journal(
                    directory,
                    "f10_succeeded",
                    attempt=attempt,
                    revision=HEAD,
                    instance_id=instance,
                    tables=58,
                    historical_values_preserved=True,
                )
                local.MARKER.unlink()
                print("F10 verified: " + str(directory))
                return directory
            except Exception as error:
                local.journal(
                    directory,
                    "f10_failed",
                    error_type=type(error).__name__,
                    maintenance_retained=True,
                )
                raise
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        apply(arguments.artifacts)
        return 0
    except Exception as error:
        print("F10_RELEASE_FAILED_" + type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
