"""Authorized F5 local/synthetic release; preserves operator data and previous releases."""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import MigrationSettings, Settings  # noqa: E402
from app.core.security import CONFIG_LOCK  # noqa: E402
from app.models.operations import Base  # noqa: E402
from tools import f1_local as local  # noqa: E402
from tools import f2_local as previous  # noqa: E402

HEAD = "20261124_0004"
SOURCE = "20261124_0003"


def verify_upgrade(before, after):
    expected = set(Base.metadata.tables) | {"alembic_version", "release_history"}
    if set(after["tables"]) != expected or set(after["tables"]) - set(before["tables"]) != {
        "evidence_files"
    }:
        raise RuntimeError("Unexpected F5 schema")
    if after["rows"]["alembic_version"] != ['{"version_num": "20261124_0004"}']:
        raise RuntimeError("Unexpected F5 revision")
    if after["rows"]["evidence_files"]:
        raise RuntimeError("Unsolicited evidence data")
    for table, rows in before["rows"].items():
        if table != "alembic_version" and rows != after["rows"][table]:
            raise RuntimeError("Existing operator or historical data changed")
    for key in ("columns", "constraints", "indexes", "functions", "triggers"):
        if not set(map(local.canonical, before[key])) <= set(map(local.canonical, after[key])):
            raise RuntimeError("An existing schema object changed")


def verify_runtime():
    with local.role_connection(Settings().database_url.get_secret_value()) as db:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
            permitted = db.execute(
                "SELECT has_table_privilege(current_user,%s,%s)",
                ("public.evidence_files", privilege),
            ).fetchone()[0]
            if permitted is not (privilege in {"SELECT", "INSERT"}):
                raise RuntimeError("Unexpected evidence runtime privileges")


def restored_upgrade(directory, before):
    from sqlalchemy.engine import make_url

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
            previous.upgrade(destination)
            migrated = previous.snapshot(db)
            verify_upgrade(before, migrated)
            previous.upgrade(destination)
            if previous.snapshot(db) != migrated:
                raise RuntimeError("Restored upgrade is not idempotent")
    local.journal(directory, "f5_restored_upgrade_noop_verified", revision=HEAD)


def apply():
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Existing maintenance must be investigated")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only the verified F3 database is an authorized source")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Another operator holds the release lock")
        if admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid()"
        ).fetchone()[0]:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))
            raise RuntimeError("Drain and stop API and all other writers before F5")
        attempt, request_id, started = uuid4(), uuid4(), local.now()
        directory = local.ROOT / "database" / "backups" / f"f5-{attempt}"
        try:
            local.private_directory(directory)
            local.private_directory(local.LOCAL)
            local.write_private(directory / "events.jsonl", b"")
            local.write_private(local.MARKER, local.canonical({"attempt": attempt}))
            local.journal(directory, "f5_started", attempt=attempt, request_id=request_id)
            admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
            identity, legacy = local.catalog(admin), local.legacy_catalog(admin)
            before = previous.snapshot(admin)
            manifest, artifact_hash = local.artifact_manifest()
            manifest.update(
                application_version="0.5.0",
                target_revision=HEAD,
                compatible_source_revisions=[SOURCE],
                evidence_files=0,
            )
            local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
            try:
                backup = previous.backup_restore(admin, directory, "before")
                restored_upgrade(directory, before)
                if previous.snapshot(admin) != before:
                    raise RuntimeError("Source changed during rehearsal")
                previous.upgrade(local.DATABASE_NAME)
                migrated = previous.snapshot(admin)
                verify_upgrade(before, migrated)
                previous.upgrade(local.DATABASE_NAME)
                if previous.snapshot(admin) != migrated:
                    raise RuntimeError("Source second upgrade changed data or schema")
                verify_runtime()
                previous.backup_restore(admin, directory, "after")
                with local.role_connection(
                    MigrationSettings().migration_database_url.get_secret_value()
                ) as db:
                    db.execute(
                        "INSERT INTO release_history (id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES (%s,%s,%s,'0.5.0',%s,%s,%s,%s,%s,"
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
                previous.backup_restore(admin, directory, "recorded")
                with local.role_connection(
                    MigrationSettings().migration_database_url.get_secret_value()
                ) as db:
                    changed = db.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F5_LOCAL_VERIFIED' "
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
                    if (
                        table not in {"alembic_version", "release_history"}
                        and final["rows"][table] != rows
                    ):
                        raise RuntimeError("Operator data changed before reopening")
                if not set(before["rows"]["release_history"]) <= set(
                    final["rows"]["release_history"]
                ):
                    raise RuntimeError("Historical releases changed")
                local.journal(
                    directory,
                    "f5_succeeded",
                    attempt=attempt,
                    request_id=request_id,
                    revision=HEAD,
                    seconds=round((local.now() - started).total_seconds(), 3),
                )
                local.MARKER.unlink()
                print(f"F5 revision/backup/four restores/no-op verified. Attempt: {attempt}")
            except Exception as error:
                try:
                    with local.role_connection(
                        MigrationSettings().migration_database_url.get_secret_value()
                    ) as db:
                        changed = db.execute(
                            "UPDATE release_history SET version=version+1,"
                            "updated_at=%s,finished_at=%s,"
                            "status='failed',result_code='F5_LOCAL_FAILED' "
                            "WHERE id=%s AND version=1 AND status='running'",
                            (local.now(), local.now(), attempt),
                        ).rowcount
                    ledger = "recorded" if changed else "no_running_record"
                except Exception:
                    ledger = "unavailable"
                local.journal(
                    directory,
                    "f5_failed",
                    attempt=attempt,
                    error_type=type(error).__name__,
                    ledger=ledger,
                    maintenance_retained=True,
                )
                raise
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
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
            previous.upgrade(name, SOURCE)
            with local.role_connection(
                MigrationSettings().migration_database_url.get_secret_value(), name
            ) as db:
                before = previous.snapshot(db)
                previous.upgrade(name)
                migrated = previous.snapshot(db)
                verify_upgrade(before, migrated)
                previous.upgrade(name)
                if previous.snapshot(db) != migrated:
                    raise RuntimeError("Isolated upgrade is not a no-op")
        print("F5 isolated upgrade/no-op and preserved operator data: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"F5 stopped safely ({type(error).__name__}); inspect protected journal.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
