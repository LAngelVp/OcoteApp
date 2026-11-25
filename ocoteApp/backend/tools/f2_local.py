"""Explicit local/synthetic F2 migration and isolated verification; never a customer release."""

import argparse
import hashlib
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import MigrationSettings  # noqa: E402
from app.models.identity import Base  # noqa: E402
from tools import f1_local as local  # noqa: E402

HEAD = "20261124_0002"


def migration_engine(database):
    url = make_url(MigrationSettings().migration_database_url.get_secret_value())
    return create_engine(
        url.set(database=database),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=60000",
        },
    )


def upgrade(database, target="head"):
    engine = migration_engine(database)
    try:
        with engine.connect() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes.update(connection=connection, expected_database=database)
            command.upgrade(config, target)
    finally:
        engine.dispose()


@contextmanager
def isolated_database(kind="test"):
    if kind not in {"test", "restore"}:
        raise ValueError("Invalid isolated destination")
    name = f"ocote_f2_{kind}_{uuid4().hex}"
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER ocote_migrador TEMPLATE template0").format(
                sql.Identifier(name)
            )
        )
        try:
            yield name
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def snapshot(connection):
    names = local.tables(connection)
    if set(names) - (set(Base.metadata.tables) | {"alembic_version", "release_history"}):
        raise RuntimeError("Unexpected tables outside the F2 scope")
    rows = {}
    for name in names:
        rows[name] = sorted(
            local.canonical(row[0]).decode("ascii")
            for row in connection.execute(
                sql.SQL("SELECT row_to_json(record) FROM public.{} AS record").format(
                    sql.Identifier(name)
                )
            ).fetchall()
        )
    return {
        "tables": names,
        "rows": rows,
        "columns": connection.execute(
            "SELECT table_name,column_name,data_type,is_nullable,column_default,"
            "character_maximum_length,numeric_precision,datetime_precision "
            "FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2"
        ).fetchall(),
        "constraints": connection.execute(
            "SELECT tab.relname,con.conname,con.contype,con.conkey,con.confkey,ref.relname,"
            "con.convalidated,con.condeferrable,con.condeferred,con.confdeltype "
            "FROM pg_constraint con JOIN pg_class tab ON tab.oid=con.conrelid "
            "JOIN pg_namespace ns ON ns.oid=tab.relnamespace "
            "LEFT JOIN pg_class ref ON ref.oid=con.confrelid "
            "WHERE ns.nspname='public' ORDER BY 1,2"
        ).fetchall(),
        "indexes": connection.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1"
        ).fetchall(),
        "functions": connection.execute(
            "SELECT proname,pg_get_functiondef(pg_proc.oid) FROM pg_proc "
            "JOIN pg_namespace ns ON ns.oid=pronamespace WHERE ns.nspname='public' ORDER BY 1"
        ).fetchall(),
        "triggers": connection.execute(
            "SELECT tab.relname,pg_get_triggerdef(tr.oid) FROM pg_trigger tr "
            "JOIN pg_class tab ON tab.oid=tr.tgrelid "
            "JOIN pg_namespace ns ON ns.oid=tab.relnamespace "
            "WHERE ns.nspname='public' AND NOT tr.tgisinternal ORDER BY 1,2"
        ).fetchall(),
    }


def pg_run(arguments, password):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment["PGPASSWORD"] = password
    result = subprocess.run(arguments, env=environment, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"PostgreSQL command failed: {Path(arguments[0]).stem}")


def backup_restore(admin, directory, label):
    baseline = snapshot(admin)
    dump = directory / f"{label}.dump"
    local.write_private(dump, b"")
    pg_run(
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
            f"--file={dump}",
        ],
        os.environ["PGPASSWORD"],
    )
    with dump.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise RuntimeError("Invalid backup header")
    pg_run([str(local.PG_BIN / "pg_restore"), "--list", str(dump)], os.environ["PGPASSWORD"])
    migration_url = MigrationSettings().migration_database_url.get_secret_value()
    parsed = make_url(migration_url)
    with isolated_database("restore") as destination:
        started = perf_counter()
        pg_run(
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
                str(dump),
            ],
            parsed.password,
        )
        with local.role_connection(migration_url, destination) as restored:
            if snapshot(restored) != baseline:
                raise RuntimeError("Restored schema or data differs")
            local.probe_release_contract(restored)
        elapsed = round(perf_counter() - started, 3)
    if snapshot(admin) != baseline:
        raise RuntimeError("Source changed during backup verification")
    result = {
        "file": dump.name,
        "bytes": dump.stat().st_size,
        "sha256": local.digest(dump),
        "restore_seconds": elapsed,
        "verified_at": local.now().isoformat(),
        "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest(),
    }
    local.write_private(directory / f"{label}-manifest.json", local.canonical(result))
    local.journal(directory, "backup_restore_verified", label=label, **result)
    return result


def controlled_upgrade(admin, directory):
    before = snapshot(admin)
    backup = backup_restore(admin, directory, "before")
    upgrade(local.DATABASE_NAME)
    migrated = snapshot(admin)
    if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(HEAD,)]:
        raise RuntimeError("Incorrect migrated head")
    for name in Base.metadata.tables:
        if migrated["rows"][name]:
            raise RuntimeError("F2 migration inserted unsolicited identity/configuration rows")
    if before["rows"]["release_history"] != migrated["rows"]["release_history"]:
        raise RuntimeError("Historical release records changed")
    upgrade(local.DATABASE_NAME)
    if snapshot(admin) != migrated:
        raise RuntimeError("Second upgrade was not a no-op")
    backup_restore(admin, directory, "after")
    return backup


def record_failure(attempt):
    with local.role_connection(
        MigrationSettings().migration_database_url.get_secret_value()
    ) as migrator:
        return migrator.execute(
            "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
            "status='failed',result_code='F2_LOCAL_FAILED' "
            "WHERE id=%s AND version=1 AND status='running'",
            (local.now(), local.now(), attempt),
        ).rowcount


def apply():
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Investigate existing maintenance before F2")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(local.HEAD,)]:
            raise RuntimeError("Only the verified F1 source revision is authorized")
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
            directory = local.ROOT / "database" / "backups" / f"f2-{attempt}"
            local.private_directory(directory)
            local.private_directory(local.LOCAL)
            local.write_private(directory / "events.jsonl", b"")
            local.write_private(local.MARKER, local.canonical({"attempt": attempt}))
            manifest, artifact_hash = local.artifact_manifest()
            manifest.update(target_revision=HEAD, compatible_source_revisions=[local.HEAD])
            local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
            local.journal(directory, "f2_started", attempt=attempt, request_id=request_id)
            try:
                backup = controlled_upgrade(admin, directory)
                if local.catalog(admin) != identity or local.legacy_catalog(admin) != legacy:
                    raise RuntimeError("Database identity or legacy catalog changed")
                with local.role_connection(
                    MigrationSettings().migration_database_url.get_secret_value()
                ) as migrator:
                    migrator.execute(
                        "INSERT INTO release_history (id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,"
                        "request_id) VALUES (%s,%s,%s,'0.2.0',%s,%s,%s,%s,%s,'local','validation',"
                        "'running',%s,%s,%s)",
                        (
                            attempt,
                            started,
                            local.now(),
                            artifact_hash,
                            local.digest(directory / "artifact-manifest.json"),
                            local.HEAD,
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
                ) as migrator:
                    changed = migrator.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F2_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Release terminal transition failed")
                local.journal(
                    directory,
                    "f2_succeeded",
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
                    "f2_failed",
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
        with isolated_database() as name:
            upgrade(name)
            with local.role_connection(
                MigrationSettings().migration_database_url.get_secret_value(), name
            ) as connection:
                assert set(local.tables(connection)) == set(Base.metadata.tables) | {
                    "alembic_version",
                    "release_history",
                }
                baseline = snapshot(connection)
                upgrade(name)
                assert snapshot(connection) == baseline
                assert all(not baseline["rows"][table] for table in Base.metadata.tables)
                print("F2 isolated migration, empty catalogs and second no-op: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"F2 stopped safely ({type(error).__name__}); inspect protected evidence.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
