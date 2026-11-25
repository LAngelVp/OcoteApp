"""Authorized local/synthetic F3 release; not a signed customer updater."""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import MigrationSettings, Settings  # noqa: E402
from app.models.operations import Base  # noqa: E402
from tools import f1_local as local  # noqa: E402
from tools import f2_local as previous  # noqa: E402

HEAD = "20261124_0003"
SOURCE = "20261124_0002"
NEW_TABLES = {
    "annual_plans",
    "objectives",
    "tasks",
    "subtasks",
    "task_history",
    "due_date_requests",
}
snapshot = previous.snapshot
upgrade = previous.upgrade
backup_restore = previous.backup_restore


def verify_upgrade(before, after):
    if set(after["tables"]) != set(Base.metadata.tables) | {"alembic_version", "release_history"}:
        raise RuntimeError("Unexpected F3 schema")
    if after["rows"]["alembic_version"] != ['{"version_num": "20261124_0003"}']:
        raise RuntimeError("Unexpected F3 head")
    for table, rows in before["rows"].items():
        if table != "alembic_version" and after["rows"][table] != rows:
            raise RuntimeError("Existing rows changed during F3")
    if any(after["rows"][table] for table in NEW_TABLES):
        raise RuntimeError("F3 inserted unsolicited operational data")
    old_columns = {tuple(row[:2]): row for row in before["columns"]}
    new_columns = {tuple(row[:2]): row for row in after["columns"]}
    if any(new_columns.get(key) != row for key, row in old_columns.items()):
        raise RuntimeError("F3 changed an existing column")


def restore_upgrade_rehearsal(directory, before):
    migration_url = MigrationSettings().migration_database_url.get_secret_value()
    from sqlalchemy.engine import make_url

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
            make_url(migration_url).password,
        )
        with local.role_connection(migration_url, destination) as restored:
            if snapshot(restored) != before:
                raise RuntimeError("Pre-upgrade restore differs from source")
            upgrade(destination)
            migrated = snapshot(restored)
            verify_upgrade(before, migrated)
            upgrade(destination)
            if snapshot(restored) != migrated:
                raise RuntimeError("Isolated second upgrade changed data or schema")
    local.journal(directory, "f3_restored_upgrade_noop_verified", revision=HEAD)


def verify_runtime():
    with local.role_connection(Settings().database_url.get_secret_value()) as runtime:
        if runtime.execute("SELECT current_user").fetchone() != (local.RUNTIME,):
            raise RuntimeError("Unexpected runtime role")
        for table in sorted(NEW_TABLES):
            for privilege in ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"]:
                expected = privilege in {"SELECT", "INSERT"} or (
                    privilege == "UPDATE" and table != "task_history"
                )
                actual = runtime.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", ("public." + table, privilege)
                ).fetchone()[0]
                if actual is not expected:
                    raise RuntimeError("Unexpected F3 runtime privileges")
        if runtime.execute(
            "SELECT has_schema_privilege(current_user,'public','CREATE')"
        ).fetchone()[0]:
            raise RuntimeError("Runtime can create schema objects")


def controlled_upgrade(admin, directory):
    before = snapshot(admin)
    backup = backup_restore(admin, directory, "before")
    restore_upgrade_rehearsal(directory, before)
    if snapshot(admin) != before:
        raise RuntimeError("Source changed during F3 rehearsal")
    upgrade(local.DATABASE_NAME)
    migrated = snapshot(admin)
    verify_upgrade(before, migrated)
    upgrade(local.DATABASE_NAME)
    if snapshot(admin) != migrated:
        raise RuntimeError("Source second upgrade changed data or schema")
    verify_runtime()
    backup_restore(admin, directory, "after")
    return backup


def record_failure(attempt):
    with local.role_connection(MigrationSettings().migration_database_url.get_secret_value()) as db:
        return db.execute(
            "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
            "status='failed',result_code='F3_LOCAL_FAILED' "
            "WHERE id=%s AND version=1 AND status='running'",
            (local.now(), local.now(), attempt),
        ).rowcount


def apply():
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Investigate existing maintenance before F3")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only the verified F2 source revision is authorized")
        before = snapshot(admin)
        if set(before["tables"]) != (set(Base.metadata.tables) - NEW_TABLES) | {
            "alembic_version",
            "release_history",
        }:
            raise RuntimeError("Unexpected source schema")
        if any(before["rows"][name] for name in set(Base.metadata.tables) - NEW_TABLES):
            raise RuntimeError("This local rehearsal requires the verified empty F2 source")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Another operator holds the release lock")
        try:
            if admin.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Drain all other connections first")
            identity, legacy = local.catalog(admin), local.legacy_catalog(admin)
            attempt, request_id = uuid4(), uuid4()
            started = local.now()
            directory = local.ROOT / "database" / "backups" / f"f3-{attempt}"
            local.private_directory(directory)
            local.private_directory(local.LOCAL)
            local.write_private(directory / "events.jsonl", b"")
            local.write_private(local.MARKER, local.canonical({"attempt": attempt}))
            manifest, artifact_hash = local.artifact_manifest()
            manifest.update(
                application_version="0.3.0",
                target_revision=HEAD,
                compatible_source_revisions=[SOURCE],
            )
            local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
            local.journal(directory, "f3_started", attempt=attempt, request_id=request_id)
            try:
                backup = controlled_upgrade(admin, directory)
                if local.catalog(admin) != identity or local.legacy_catalog(admin) != legacy:
                    raise RuntimeError("Database identity or legacy catalog changed")
                with local.role_connection(
                    MigrationSettings().migration_database_url.get_secret_value()
                ) as db:
                    db.execute(
                        "INSERT INTO release_history (id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES (%s,%s,%s,'0.3.0',%s,%s,%s,%s,%s,"
                        "'local','validation','running',%s,%s,%s)",
                        (
                            attempt,
                            started,
                            local.now(),
                            artifact_hash,
                            local.digest(directory / "artifact-manifest.json"),
                            SOURCE,
                            HEAD,
                            "LUIS ANGEL VALLEJO - DESARROLLADOR",
                            local.digest(directory / "before-manifest.json"),
                            backup["verified_at"],
                            request_id,
                        ),
                    )
                backup_restore(admin, directory, "recorded")
                with local.role_connection(
                    MigrationSettings().migration_database_url.get_secret_value()
                ) as db:
                    changed = db.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F3_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Release terminal transition failed")
                backup_restore(admin, directory, "terminal")
                if local.catalog(admin) != identity or local.legacy_catalog(admin) != legacy:
                    raise RuntimeError("Database identity changed before reopening")
                local.journal(
                    directory,
                    "f3_succeeded",
                    attempt=attempt,
                    request_id=request_id,
                    revision=HEAD,
                    seconds=round((local.now() - started).total_seconds(), 3),
                )
                local.MARKER.unlink()
            except Exception as error:
                try:
                    ledger = "recorded" if record_failure(attempt) else "no_running_record"
                except Exception:
                    ledger = "unavailable"
                local.journal(
                    directory,
                    "f3_failed",
                    attempt=attempt,
                    error_type=type(error).__name__,
                    ledger=ledger,
                    maintenance_retained=True,
                )
                raise
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check-migration", "apply"])
    parser.add_argument("--execute", action="store_true", required=True)
    arguments = parser.parse_args()
    if arguments.action == "apply":
        apply()
    else:
        with previous.isolated_database() as name:
            upgrade(name, SOURCE)
            url = MigrationSettings().migration_database_url.get_secret_value()
            with local.role_connection(url, name) as connection:
                before = snapshot(connection)
                upgrade(name)
                migrated = snapshot(connection)
                verify_upgrade(before, migrated)
                upgrade(name)
                if snapshot(connection) != migrated:
                    raise RuntimeError("Isolated migration was not a no-op")
        print("F3 isolated migration, preserved F2, empty operational tables and no-op: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"F3 stopped safely ({type(error).__name__}); inspect protected evidence.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
