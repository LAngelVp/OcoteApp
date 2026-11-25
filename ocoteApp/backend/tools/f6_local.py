"""Explicit F6 local rehearsal/release; private artifacts must be outside the checkout."""

import argparse
import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings
from app.core.security import CONFIG_LOCK
from app.models.evaluations import Evaluation
from app.models.operations import Base
from tools import f1_local as local
from tools import f2_local as previous

HEAD = "20261125_0005"
SOURCE = "20261124_0004"
OPERATOR = "LUIS ANGEL VALLEJO - DESARROLLADOR"


def verify_upgrade(before, after):
    expected = set(Base.metadata.tables) | {"alembic_version", "release_history"}
    added = {Evaluation.__tablename__, "evaluation_items"}
    if set(after["tables"]) != expected or set(after["tables"]) - set(before["tables"]) != added:
        raise RuntimeError("Unexpected F6 schema")
    if after["rows"]["alembic_version"] != ['{"version_num": "20261125_0005"}']:
        raise RuntimeError("Unexpected F6 revision")
    if any(after["rows"][table] for table in added):
        raise RuntimeError("Unsolicited F6 data")
    for table, rows in before["rows"].items():
        if table != "alembic_version" and after["rows"][table] != rows:
            raise RuntimeError("Existing operator or historical data changed")
    for key in ("columns", "constraints", "indexes", "functions", "triggers"):
        if not set(map(local.canonical, before[key])) <= set(map(local.canonical, after[key])):
            raise RuntimeError("An existing schema object changed")


def verify_runtime(database=local.DATABASE_NAME):
    with local.role_connection(Settings().database_url.get_secret_value(), database) as db:
        for table, allowed in (
            ("evaluations", {"SELECT", "INSERT", "UPDATE"}),
            ("evaluation_items", {"SELECT", "INSERT", "DELETE"}),
        ):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                permitted = db.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)",
                    ("public." + table, privilege),
                ).fetchone()[0]
                if permitted is not (privilege in allowed):
                    raise RuntimeError("Unexpected F6 runtime privileges")


def verify_isolated():
    with previous.isolated_database() as name:
        previous.upgrade(name, SOURCE)
        with local.role_connection(
            MigrationSettings().migration_database_url.get_secret_value(), name
        ) as db:
            before = previous.snapshot(db)
            previous.upgrade(name, HEAD)
            migrated = previous.snapshot(db)
            verify_upgrade(before, migrated)
            verify_runtime(name)
            previous.upgrade(name, HEAD)
            if previous.snapshot(db) != migrated:
                raise RuntimeError("Isolated upgrade is not a no-op")


def restored_upgrade(directory, before):
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
        with local.role_connection(url, destination) as db:
            if previous.snapshot(db) != before:
                raise RuntimeError("Source restore differs")
            previous.upgrade(destination, HEAD)
            migrated = previous.snapshot(db)
            verify_upgrade(before, migrated)
            previous.upgrade(destination, HEAD)
            if previous.snapshot(db) != migrated:
                raise RuntimeError("Restored upgrade is not idempotent")
    local.journal(directory, "f6_restored_upgrade_noop_verified", revision=HEAD)


def artifact_manifest():
    manifest, _ = local.artifact_manifest()
    files = {"backend/" + key: value for key, value in manifest["files"].items()}
    sources = [
        *local.ROOT.glob("src/**/*"),
        local.ROOT / "package.json",
        local.ROOT / "angular.json",
        *local.ROOT.glob("tsconfig*.json"),
    ]
    files.update(
        {
            path.relative_to(local.ROOT).as_posix(): local.digest(path)
            for path in sources
            if path.is_file()
        }
    )
    manifest.update(
        application_version="0.6.0",
        target_revision=HEAD,
        compatible_source_revisions=[SOURCE],
        files=files,
        operator=OPERATOR,
        scope="local_loopback_synthetic_only",
        real_storage_clamav=False,
        customer_release=False,
    )
    return manifest, hashlib.sha256(local.canonical(files)).hexdigest()


def record_failure(attempt):
    with local.role_connection(MigrationSettings().migration_database_url.get_secret_value()) as db:
        return db.execute(
            "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
            "status='failed',result_code='F6_LOCAL_FAILED' "
            "WHERE id=%s AND version=1 AND status='running'",
            (local.now(), local.now(), attempt),
        ).rowcount


def apply(artifacts, *, temporary_create=False):
    root = Path(artifacts).resolve()
    if root == local.ROOT or local.ROOT in root.parents:
        raise RuntimeError("Artifacts must be outside the checkout")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Existing maintenance must be investigated")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only the verified F5 source revision is authorized")
        url = MigrationSettings().migration_database_url.get_secret_value()
        with local.role_connection(url) as migrator:
            can_create, available = migrator.execute(
                "SELECT has_database_privilege(current_user,current_database(),'CREATE'), "
                "EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='btree_gist')"
            ).fetchone()
            if not available or not (can_create or temporary_create):
                raise RuntimeError("Migrator extension capability is not ready")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Another operator holds the release lock")
        try:
            if admin.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Drain and stop API and all writers before F6")
            local.private_directory(root)
            size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            if any(
                shutil.disk_usage(path).free < size * 6 + 134217728 for path in (root, local.ROOT)
            ):
                raise RuntimeError("Insufficient space for backups and isolated restores")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f6-" + str(attempt))
            local.private_directory(directory)
            local.private_directory(local.LOCAL)
            local.write_private(directory / "events.jsonl", b"")
            local.journal(directory, "f6_started", attempt=attempt, request_id=request_id)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt}))
            try:
                admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
                identity, legacy = local.catalog(admin), local.legacy_catalog(admin)
                before = previous.snapshot(admin)
                manifest, artifact_hash = artifact_manifest()
                local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
                backup = previous.backup_restore(admin, directory, "before")
                restored_upgrade(directory, before)
                if previous.snapshot(admin) != before:
                    raise RuntimeError("Source changed during rehearsal")
                granted = False
                try:
                    if not can_create:
                        admin.execute(
                            sql.SQL("GRANT CREATE ON DATABASE {} TO ocote_migrador").format(
                                sql.Identifier(local.DATABASE_NAME)
                            )
                        )
                        granted = True
                        local.journal(directory, "f6_temporary_create_granted", role=local.MIGRATOR)
                    previous.upgrade(local.DATABASE_NAME, HEAD)
                    migrated = previous.snapshot(admin)
                    verify_upgrade(before, migrated)
                    previous.upgrade(local.DATABASE_NAME, HEAD)
                    if previous.snapshot(admin) != migrated:
                        raise RuntimeError("Source second upgrade changed data or schema")
                finally:
                    if granted:
                        admin.execute(
                            sql.SQL("REVOKE CREATE ON DATABASE {} FROM ocote_migrador").format(
                                sql.Identifier(local.DATABASE_NAME)
                            )
                        )
                        if admin.execute(
                            "SELECT has_database_privilege(%s,current_database(),'CREATE')",
                            (local.MIGRATOR,),
                        ).fetchone()[0]:
                            raise RuntimeError("Temporary database privilege remains effective")
                        local.journal(directory, "f6_temporary_create_revoked", role=local.MIGRATOR)
                verify_runtime()
                previous.backup_restore(admin, directory, "after")
                with local.role_connection(url) as db:
                    db.execute(
                        "INSERT INTO release_history (id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES (%s,%s,%s,'0.6.0',%s,%s,%s,%s,%s,"
                        "'local','validation','running',%s,%s,%s)",
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
                            backup["verified_at"],
                            request_id,
                        ),
                    )
                previous.backup_restore(admin, directory, "recorded")
                with local.role_connection(url) as db:
                    changed = db.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F6_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Own release terminal transition failed")
                previous.backup_restore(admin, directory, "terminal")
                if local.catalog(admin) != identity or local.legacy_catalog(admin) != legacy:
                    raise RuntimeError("Database identity or legacy catalog changed")
                final = previous.snapshot(admin)
                for table, rows in before["rows"].items():
                    if table not in {"alembic_version", "release_history"}:
                        if final["rows"][table] != rows:
                            raise RuntimeError("Operator data changed before reopening")
                if not set(before["rows"]["release_history"]) <= set(
                    final["rows"]["release_history"]
                ):
                    raise RuntimeError("Historical releases changed")
                local.journal(
                    directory,
                    "f6_succeeded",
                    attempt=attempt,
                    request_id=request_id,
                    revision=HEAD,
                    tables=len(final["tables"]),
                    seconds=round((local.now() - started).total_seconds(), 3),
                )
                local.MARKER.unlink()
                print("F6 revision/backup/four restores/no-op verified. Attempt: " + str(attempt))
            except Exception as error:
                try:
                    ledger = "recorded" if record_failure(attempt) else "no_running_record"
                except Exception:
                    ledger = "unavailable"
                local.journal(
                    directory,
                    "f6_failed",
                    attempt=attempt,
                    error_type=type(error).__name__,
                    ledger=ledger,
                    maintenance_retained=True,
                )
                raise
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check-migration", "apply"])
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--temporary-create", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "apply":
        if arguments.artifacts is None:
            parser.error("apply requires an explicit --artifacts directory outside checkout")
        apply(arguments.artifacts, temporary_create=arguments.temporary_create)
    else:
        verify_isolated()
        print("F6 isolated migration/no-op, preserved data and runtime grants: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("F6 stopped safely (" + type(error).__name__ + "); inspect protected journal.")
        raise SystemExit(1) from None
