"""Explicit, local-only F1 provisioning and recovery rehearsal; not a customer updater."""

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.core.config import DATABASE_NAME, MigrationSettings  # noqa: E402

LOCAL = BACKEND / ".local"
MARKER = LOCAL / "maintenance.json"
PG_BIN = ROOT / "database" / "postgres" / "bin"
RUNTIME = "ocote_runtime"
MIGRATOR = "ocote_migrador"
HEAD = "20261124_0001"
LOCK_KEY = 726_018_241


def now():
    return datetime.now(UTC)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def protect(path):
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        permission = f"{identity}:(OI)(CI)F" if path.is_dir() else f"{identity}:F"
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", permission],
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    protect(path)


def write_private(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    protect(path)
    with path.open("wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def journal(directory, event, **values):
    payload = {"at": now().isoformat(), "event": event, **values}
    with (directory / "events.jsonl").open("ab") as stream:
        stream.write(canonical(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(payload, default=str), flush=True)


def admin_connection(database=DATABASE_NAME):
    password = os.environ.get("PGPASSWORD")
    if not password:
        raise RuntimeError("Export the authorized local administrative credential first")
    return psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=database,
        user="postgres",
        password=password,
        connect_timeout=3,
        autocommit=True,
        sslmode="disable",
        application_name="ocote-f1-local",
    )


def role_connection(url, database=DATABASE_NAME):
    parsed = make_url(url)
    return psycopg.connect(
        host=parsed.host,
        port=parsed.port,
        dbname=database,
        user=parsed.username,
        password=parsed.password,
        connect_timeout=3,
        autocommit=True,
        application_name="ocote-f1-role-check",
        sslmode="disable",
    )


def verify_identity(admin):
    version = admin.execute("SHOW server_version_num").fetchone()[0]
    data = admin.execute("SHOW data_directory").fetchone()[0]
    database = admin.execute("SELECT current_database()").fetchone()[0]
    if (
        not 180000 <= int(version) < 190000
        or database != DATABASE_NAME
        or Path(data).resolve() != (ROOT / "database" / "data").resolve()
        or (ROOT / "database" / "data" / "PG_VERSION").read_text().strip() != "18"
    ):
        raise RuntimeError("Unexpected cluster identity; no changes authorized")


def catalog(admin):
    return admin.execute(
        "SELECT oid, datname FROM pg_database WHERE datname IN ('ocote', 'ocoteAppDatabase') "
        "ORDER BY datname"
    ).fetchall()


def legacy_catalog(admin):
    if not admin.execute("SELECT 1 FROM pg_database WHERE datname = 'ocote'").fetchone():
        return []
    with admin_connection("ocote") as legacy:
        return legacy.execute(
            "SELECT n.nspname, c.relname, c.oid, c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
            "AND n.nspname NOT LIKE 'pg_toast%' ORDER BY 1,2"
        ).fetchall()


def tables(connection):
    return [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ).fetchall()
    ]


def snapshot(connection):
    names = tables(connection)
    if set(names) - {"alembic_version", "release_history"}:
        raise RuntimeError("F1 rehearsal refuses a database with business or unknown tables")
    rows = {}
    for name in names:
        rows[name] = sorted(
            row[0]
            for row in connection.execute(
                sql.SQL("SELECT row_to_json(record)::text FROM public.{} AS record").format(
                    sql.Identifier(name)
                )
            ).fetchall()
        )
    constraints = connection.execute(
        "SELECT c.relname, con.conname, con.contype, con.conkey, con.confkey, "
        "ref.relname, con.convalidated, con.condeferrable, con.condeferred, "
        "con.confupdtype, con.confdeltype, con.confmatchtype "
        "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
        "LEFT JOIN pg_class ref ON ref.oid=con.confrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2"
    ).fetchall()
    columns = connection.execute(
        "SELECT table_name,column_name,data_type,is_nullable,column_default,"
        "character_maximum_length,numeric_precision,datetime_precision "
        "FROM information_schema.columns WHERE table_schema='public' "
        "ORDER BY table_name,ordinal_position"
    ).fetchall()
    indexes = connection.execute(
        "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY indexname"
    ).fetchall()
    triggers = connection.execute(
        "SELECT c.relname, pg_get_triggerdef(t.oid) FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2"
    ).fetchall()
    functions = connection.execute(
        "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public' AND p.proname='protect_release_history' ORDER BY 1"
    ).fetchall()
    return {
        "tables": names,
        "rows": rows,
        "constraints": constraints,
        "columns": columns,
        "indexes": indexes,
        "triggers": triggers,
        "functions": functions,
    }


def probe_release_contract(connection):
    if "release_history" not in tables(connection):
        return
    timestamp = now()
    valid = {
        "id": uuid4(),
        "created_at": timestamp,
        "updated_at": timestamp,
        "version": 1,
        "application_version": "rollback-only-probe",
        "artifact_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "target_revision": HEAD,
        "operator_ref": "local-f1-probe",
        "deployment_mode": "local",
        "phase": "validation",
        "status": "running",
        "request_id": uuid4(),
    }

    def insert(values):
        connection.execute(
            sql.SQL("INSERT INTO public.release_history ({}) VALUES ({})").format(
                sql.SQL(",").join(sql.Identifier(key) for key in values),
                sql.SQL(",").join(sql.Placeholder() for key in values),
            ),
            tuple(values.values()),
        )

    invalid = [
        {"version": 0},
        {"artifact_sha256": "invalid"},
        {"manifest_sha256": "invalid"},
        {"deployment_mode": "invalid"},
        {"phase": "invalid"},
        {"status": "invalid"},
        {"updated_at": datetime(2000, 1, 1, tzinfo=UTC)},
        {"retry_of_id": valid["id"]},
        {"retry_of_id": uuid4()},
        {"status": "failed"},
        {"finished_at": timestamp},
        {"result_code": "UNEXPECTED"},
        {"backup_verified_at": timestamp},
        {"backup_manifest_sha256": "invalid"},
        {
            "backup_manifest_sha256": "c" * 64,
            "backup_verified_at": datetime(2000, 1, 1, tzinfo=UTC),
        },
        {
            "status": "succeeded",
            "phase": "complete",
            "source_revision": HEAD,
            "finished_at": timestamp,
            "result_code": "PROBE",
        },
        {
            "status": "succeeded",
            "phase": "validation",
            "finished_at": timestamp,
            "result_code": "PROBE",
        },
    ]
    with connection.transaction(force_rollback=True):
        for overrides in invalid:
            try:
                with connection.transaction():
                    insert(valid | overrides)
            except psycopg.IntegrityError:
                continue
            raise RuntimeError("Restored release constraint accepted an invalid fixture")
        insert(valid)
        for statement in (
            "DELETE FROM public.release_history WHERE id=%s",
            "UPDATE public.release_history SET operator_ref='changed',version=2 WHERE id=%s",
            "UPDATE public.release_history SET phase='backup' WHERE id=%s",
        ):
            try:
                with connection.transaction():
                    connection.execute(statement, (valid["id"],))
            except psycopg.errors.CheckViolation:
                continue
            raise RuntimeError("Restored release trigger accepted an invalid mutation")
        connection.execute(
            "UPDATE public.release_history SET status='failed',finished_at=%s,"
            "result_code='ROLLBACK_ONLY_PROBE',version=2 WHERE id=%s",
            (timestamp, valid["id"]),
        )
        try:
            with connection.transaction():
                connection.execute(
                    "UPDATE public.release_history SET version=3 WHERE id=%s",
                    (valid["id"],),
                )
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise RuntimeError("Restored terminal release was mutable")


def provision(admin):
    if (BACKEND / ".env").exists() or tables(admin):
        raise RuntimeError(
            "Provisioning requires no backend .env and an empty application database"
        )
    existing = admin.execute(
        "SELECT rolname FROM pg_roles WHERE rolname IN (%s,%s)",
        (RUNTIME, MIGRATOR),
    ).fetchall()
    if existing:
        raise RuntimeError("Dedicated roles already exist; do not rotate or overwrite implicitly")
    passwords = {role: secrets.token_urlsafe(36) for role in (RUNTIME, MIGRATOR)}
    urls = {
        role: URL.create(
            "postgresql+psycopg",
            username=role,
            password=password,
            host="127.0.0.1",
            port=5432,
            database=DATABASE_NAME,
        ).render_as_string(hide_password=False)
        for role, password in passwords.items()
    }
    with admin.transaction():
        for role, password in passwords.items():
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                    "NOBYPASSRLS CONNECTION LIMIT {} PASSWORD {}"
                ).format(
                    sql.Identifier(role),
                    sql.Literal(8 if role == RUNTIME else 3),
                    sql.Literal(password),
                )
            )
            admin.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET timezone TO 'UTC'").format(
                    sql.Identifier(role),
                    sql.Identifier(DATABASE_NAME),
                )
            )
            admin.execute(
                sql.SQL(
                    "ALTER ROLE {} IN DATABASE {} SET search_path TO public, pg_catalog"
                ).format(sql.Identifier(role), sql.Identifier(DATABASE_NAME))
            )
        admin.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(DATABASE_NAME),
            )
        )
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                sql.Identifier(DATABASE_NAME),
                sql.Identifier(RUNTIME),
                sql.Identifier(MIGRATOR),
            )
        )
        admin.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME)))
        admin.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                sql.Identifier(MIGRATOR),
            )
        )
        admin.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "REVOKE ALL ON TABLES FROM PUBLIC"
            ).format(sql.Identifier(MIGRATOR))
        )
        private_directory(LOCAL)
        env = {
            "APP_ENV": "development",
            "DEPLOYMENT_MODE": "local",
            "ORGANIZATION_TIMEZONE": "America/Mexico_City",
            "DATABASE_URL": urls[RUNTIME],
            "MIGRATION_DATABASE_URL": urls[MIGRATOR],
            "HEALTH_TOKEN": secrets.token_urlsafe(36),
        }
        content = "".join(f"{key}={json.dumps(value)}\n" for key, value in env.items())
        write_private(BACKEND / ".env", content.encode("ascii"))
    for role, url in urls.items():
        with role_connection(url) as connection:
            identity = connection.execute(
                "SELECT current_database(), current_user, rolsuper, rolcreatedb, rolcreaterole, "
                "rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if identity[:2] != (DATABASE_NAME, role) or any(identity[2:]):
                raise RuntimeError("Unexpected dedicated role privileges")
            print(f"Role connection verified: {role}; no elevated attributes", flush=True)
    print(
        "Provisioned dedicated roles; credentials generated in ignored backend/.env "
        "with private ACL"
    )


def pg_command(executable, arguments, directory, event, password=None):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment["PGPASSWORD"] = password or os.environ["PGPASSWORD"]
    environment["PGSSLMODE"] = "disable"
    environment["PGAPPNAME"] = "ocote-f1-backup"
    started = perf_counter()
    result = subprocess.run(
        [str(PG_BIN / f"{executable}.exe"), *arguments],
        env=environment,
        capture_output=True,
        text=True,
    )
    journal(
        directory,
        event,
        command=[executable, *arguments],
        exit_code=result.returncode,
        duration_seconds=round(perf_counter() - started, 3),
    )
    if result.returncode:
        raise RuntimeError(f"{executable} failed; maintenance retained; no continuation")
    return result.stdout


def backup_and_restore(admin, directory, label, migration_url):
    probe_release_contract(admin)
    before = snapshot(admin)
    backup = directory / f"{label}.dump"
    pg_command(
        "pg_dump",
        [
            "-w",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            DATABASE_NAME,
            "--format=custom",
            f"--file={backup}",
        ],
        directory,
        f"{label}_dump",
    )
    if not backup.is_file() or backup.stat().st_size <= 0 or backup.read_bytes()[:5] != b"PGDMP":
        raise RuntimeError("Invalid or empty custom backup")
    pg_command("pg_restore", ["--list", str(backup)], directory, f"{label}_archive_list")
    manifest = {
        "file": backup.name,
        "bytes": backup.stat().st_size,
        "sha256": digest(backup),
        "database": DATABASE_NAME,
        "label": label,
    }
    temporary = f"ocote_f1_restore_{uuid4().hex}"
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
            sql.Identifier(temporary),
            sql.Identifier(MIGRATOR),
        )
    )
    journal(directory, "isolated_database_created", database=temporary)
    started = perf_counter()
    try:
        pg_command(
            "pg_restore",
            [
                "-w",
                "-h",
                "127.0.0.1",
                "-p",
                "5432",
                "-U",
                MIGRATOR,
                "-d",
                temporary,
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                str(backup),
            ],
            directory,
            f"{label}_restore",
            password=make_url(migration_url).password,
        )
        with role_connection(migration_url, temporary) as restored:
            after = snapshot(restored)
            probe_release_contract(restored)
        if before != after:
            raise RuntimeError("Restored schema, rows, constraints, indexes or triggers differ")
        manifest["verified_at"] = now().isoformat()
        manifest["restore_seconds"] = round(perf_counter() - started, 3)
        manifest["snapshot_sha256"] = hashlib.sha256(canonical(before)).hexdigest()
        manifest["constraint_probe"] = "17 invalid inserts and protected transitions; rolled back"
        journal(directory, f"{label}_restore_verified", **manifest, tables=before["tables"])
    finally:
        if not re.fullmatch(r"ocote_f1_restore_[0-9a-f]{32}", temporary):
            raise RuntimeError("Unsafe cleanup target")
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(temporary)))
        journal(directory, "isolated_database_removed", database=temporary)
    write_private(directory / f"{label}-manifest.json", canonical(manifest))
    return manifest


def alembic_upgrade(directory, label):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    journal(
        directory,
        label,
        command=["python", "-m", "alembic", "upgrade", "head"],
        exit_code=result.returncode,
    )
    if result.returncode:
        raise RuntimeError("Alembic failed; maintenance retained; inspect securely before retry")


def artifact_manifest():
    files = sorted(
        [
            *BACKEND.glob("app/**/*.py"),
            *BACKEND.glob("alembic/**/*.py"),
            *BACKEND.glob("tools/*.py"),
            BACKEND / "pyproject.toml",
            BACKEND / "requirements.lock",
            BACKEND / "alembic.ini",
        ]
    )
    manifest = {
        "application_version": "0.1.0",
        "target_revision": HEAD,
        "compatible_source_revisions": [None],
        "rehearsal_only": True,
        "signed": False,
        "files": {path.relative_to(BACKEND).as_posix(): digest(path) for path in files},
    }
    return manifest, hashlib.sha256(canonical(manifest["files"])).hexdigest()


def controlled_upgrade(admin, directory, migration_url):
    before = snapshot(admin)
    if before["tables"]:
        raise RuntimeError("This initial rehearsal only supports a virgin application database")
    backup = backup_and_restore(admin, directory, "before", migration_url)
    alembic_upgrade(directory, "initial_upgrade")
    migrated = snapshot(admin)
    if migrated["tables"] != ["alembic_version", "release_history"]:
        raise RuntimeError("Unexpected technical schema")
    revision = admin.execute("SELECT version_num FROM public.alembic_version").fetchall()
    if revision != [(HEAD,)]:
        raise RuntimeError("Unexpected Alembic revision")
    alembic_upgrade(directory, "second_upgrade")
    if snapshot(admin) != migrated:
        raise RuntimeError("The second upgrade was not a no-op")
    journal(
        directory,
        "noop_verified",
        revision=HEAD,
        tables=migrated["tables"],
        snapshot_sha256=hashlib.sha256(canonical(migrated)).hexdigest(),
    )
    return backup


def rehearse(admin):
    if MARKER.exists():
        raise RuntimeError("Maintenance already exists; investigate the prior attempt before retry")
    if not admin.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        raise RuntimeError("Another operator holds the persistent F1 release lock")
    try:
        sessions = admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
            (DATABASE_NAME,),
        ).fetchone()[0]
        if sessions:
            raise RuntimeError("Stop and drain all API and external writers before the rehearsal")
        private_directory(LOCAL)
        attempt = uuid4()
        request_id = uuid4()
        started = now()
        directory = ROOT / "database" / "backups" / f"f1-{attempt}"
        private_directory(directory)
        write_private(directory / "events.jsonl", b"")
        write_private(MARKER, canonical({"attempt": str(attempt), "request_id": str(request_id)}))
        journal(
            directory,
            "maintenance_entered",
            attempt=attempt,
            request_id=request_id,
            lock="session_advisory_direct",
            other_sessions=sessions,
        )
        original_catalog = catalog(admin)
        original_legacy = legacy_catalog(admin)
        migration_url = MigrationSettings().migration_database_url.get_secret_value()
        manifest, artifact_hash = artifact_manifest()
        write_private(directory / "artifact-manifest.json", canonical(manifest))
        try:
            backup = controlled_upgrade(admin, directory, migration_url)
            backup_hash = digest(directory / "before-manifest.json")
            manifest_hash = digest(directory / "artifact-manifest.json")
            with role_connection(migration_url) as migrator:
                migrator.execute(
                    "INSERT INTO public.release_history (id,created_at,updated_at,version,"
                    "application_version,artifact_sha256,manifest_sha256,source_revision,"
                    "target_revision,operator_ref,deployment_mode,phase,status,"
                    "backup_manifest_sha256,backup_verified_at,request_id) "
                    "VALUES (%s,%s,%s,1,'0.1.0',%s,%s,NULL,%s,%s,'local','validation','running',"
                    "%s,%s,%s)",
                    (
                        attempt,
                        started,
                        now(),
                        artifact_hash,
                        manifest_hash,
                        HEAD,
                        getpass.getuser()[:120],
                        backup_hash,
                        backup["verified_at"],
                        request_id,
                    ),
                )
            post = backup_and_restore(admin, directory, "after", migration_url)
            if catalog(admin) != original_catalog or legacy_catalog(admin) != original_legacy:
                raise RuntimeError("Original databases or legacy catalog changed unexpectedly")
            with role_connection(migration_url) as migrator:
                changed = migrator.execute(
                    "UPDATE public.release_history SET phase='complete',status='succeeded',"
                    "finished_at=%s,updated_at=%s,version=version+1,"
                    "result_code='F1_LOCAL_VERIFIED' "
                    "WHERE id=%s AND status='running' AND version=1",
                    (now(), now(), attempt),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Release ledger transition failed")
            journal(
                directory,
                "rehearsal_succeeded",
                attempt=attempt,
                request_id=request_id,
                revision=HEAD,
                source_and_legacy_preserved=True,
                post_restore_seconds=post["restore_seconds"],
                elapsed_seconds=round((now() - started).total_seconds(), 3),
                limits="local unsigned rehearsal; not a production release or cloud approval",
            )
            MARKER.unlink()
            print(f"Private evidence directory: database/backups/{directory.name}", flush=True)
        except Exception as error:
            journal(
                directory,
                "rehearsal_failed",
                attempt=attempt,
                request_id=request_id,
                error_type=type(error).__name__,
                sqlstate=getattr(error, "sqlstate", None),
                maintenance_retained=True,
            )
            raise
    finally:
        admin.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def retry_verification(admin):
    if not MARKER.exists():
        raise RuntimeError("A failed rehearsal maintenance record is required")
    marker = json.loads(MARKER.read_text())
    previous_id = str(UUID(marker["attempt"]))
    previous_directory = ROOT / "database" / "backups" / f"f1-{previous_id}"
    if not admin.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        raise RuntimeError("Another operator holds the release lock")
    try:
        if admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
            (DATABASE_NAME,),
        ).fetchone()[0]:
            raise RuntimeError("Drain all other connections before retrying")
        if admin.execute("SELECT version_num FROM public.alembic_version").fetchall() != [(HEAD,)]:
            raise RuntimeError("This recovery only verifies the already applied technical head")
        migration_url = MigrationSettings().migration_database_url.get_secret_value()
        with role_connection(migration_url) as migrator:
            changed = migrator.execute(
                "UPDATE public.release_history SET status='failed',finished_at=%s,updated_at=%s,"
                "version=version+1,result_code='RESTORE_COMPARISON_FAILED' "
                "WHERE id=%s AND status='running' AND version=1",
                (now(), now(), previous_id),
            ).rowcount
            if changed != 1:
                raise RuntimeError("Prior release is not the expected incomplete attempt")
        journal(
            previous_directory,
            "failed_attempt_reconciled",
            attempt=previous_id,
            result_code="RESTORE_COMPARISON_FAILED",
            original_timestamps_preserved=True,
        )
        started = now()
        attempt, request_id = uuid4(), uuid4()
        directory = ROOT / "database" / "backups" / f"f1-{attempt}"
        private_directory(directory)
        write_private(directory / "events.jsonl", b"")
        replacement = LOCAL / f"maintenance-{attempt}.json"
        write_private(
            replacement, canonical({"attempt": str(attempt), "request_id": str(request_id)})
        )
        os.replace(replacement, MARKER)
        journal(
            directory,
            "retry_entered",
            attempt=attempt,
            retry_of_id=previous_id,
            request_id=request_id,
            maintenance_retained=True,
        )
        original_catalog, original_legacy = catalog(admin), legacy_catalog(admin)
        manifest, artifact_hash = artifact_manifest()
        manifest["compatible_source_revisions"] = [HEAD]
        manifest["retry_of_id"] = previous_id
        write_private(directory / "artifact-manifest.json", canonical(manifest))
        try:
            backup = backup_and_restore(admin, directory, "before", migration_url)
            baseline = snapshot(admin)
            alembic_upgrade(directory, "retry_upgrade_noop")
            alembic_upgrade(directory, "retry_second_upgrade_noop")
            if snapshot(admin) != baseline:
                raise RuntimeError("Retry upgrade changed the technical schema or existing records")
            journal(directory, "noop_verified", revision=HEAD, both_invocations=True)
            with role_connection(migration_url) as migrator:
                migrator.execute(
                    "INSERT INTO public.release_history (id,retry_of_id,created_at,updated_at,"
                    "version,application_version,artifact_sha256,manifest_sha256,source_revision,"
                    "target_revision,operator_ref,deployment_mode,phase,status,"
                    "backup_manifest_sha256,backup_verified_at,request_id) "
                    "VALUES (%s,%s,%s,%s,1,'0.1.0',%s,%s,%s,%s,%s,'local','validation',"
                    "'running',%s,%s,%s)",
                    (
                        attempt,
                        previous_id,
                        started,
                        now(),
                        artifact_hash,
                        digest(directory / "artifact-manifest.json"),
                        HEAD,
                        HEAD,
                        getpass.getuser()[:120],
                        digest(directory / "before-manifest.json"),
                        backup["verified_at"],
                        request_id,
                    ),
                )
            post = backup_and_restore(admin, directory, "after", migration_url)
            if catalog(admin) != original_catalog or legacy_catalog(admin) != original_legacy:
                raise RuntimeError("Original databases or legacy catalog changed")
            with role_connection(migration_url) as migrator:
                changed = migrator.execute(
                    "UPDATE public.release_history SET phase='complete',status='succeeded',"
                    "finished_at=%s,updated_at=%s,version=version+1,"
                    "result_code='F1_RETRY_VERIFIED' "
                    "WHERE id=%s AND version=1 AND status='running'",
                    (now(), now(), attempt),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Retry terminal ledger transition failed")
            journal(
                directory,
                "retry_succeeded",
                attempt=attempt,
                retry_of_id=previous_id,
                request_id=request_id,
                revision=HEAD,
                source_and_legacy_preserved=True,
                post_restore_seconds=post["restore_seconds"],
                elapsed_seconds=round((now() - started).total_seconds(), 3),
            )
            MARKER.unlink()
            print(f"Private evidence directory: database/backups/{directory.name}", flush=True)
        except Exception as error:
            journal(
                directory,
                "retry_failed",
                attempt=attempt,
                error_type=type(error).__name__,
                sqlstate=getattr(error, "sqlstate", None),
                maintenance_retained=True,
            )
            raise
    finally:
        admin.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def verify_existing_upgrade(admin, directory, migration_url):
    baseline = snapshot(admin)
    if baseline["tables"] != ["alembic_version", "release_history"]:
        raise RuntimeError("Expected the F1 technical schema only")
    if admin.execute("SELECT version_num FROM public.alembic_version").fetchall() != [(HEAD,)]:
        raise RuntimeError("The current revision does not match the technical artifact")
    backup = backup_and_restore(admin, directory, "closure", migration_url)
    for label in ("closure_upgrade_noop", "closure_second_upgrade_noop"):
        alembic_upgrade(directory, label)
        if snapshot(admin) != baseline:
            raise RuntimeError("Closure verification changed schema or historical release records")
    journal(
        directory,
        "closure_noop_verified",
        revision=HEAD,
        both_invocations=True,
        history_preserved=True,
        snapshot_sha256=hashlib.sha256(canonical(baseline)).hexdigest(),
    )
    return backup


def verify_existing(admin):
    if MARKER.exists():
        raise RuntimeError("Existing maintenance must be investigated before closure verification")
    if not admin.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        raise RuntimeError("Another operator holds the release lock")
    try:
        if admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
            (DATABASE_NAME,),
        ).fetchone()[0]:
            raise RuntimeError("Drain other connections before closure verification")
        private_directory(LOCAL)
        verification, request_id = uuid4(), uuid4()
        started = now()
        directory = ROOT / "database" / "backups" / f"f1-closure-{verification}"
        private_directory(directory)
        write_private(directory / "events.jsonl", b"")
        write_private(
            MARKER, canonical({"verification": str(verification), "request_id": str(request_id)})
        )
        journal(
            directory,
            "closure_started",
            verification=verification,
            request_id=request_id,
            verification_only=True,
            release_history_mutation=False,
        )
        try:
            original_catalog, original_legacy = catalog(admin), legacy_catalog(admin)
            manifest, artifact_hash = artifact_manifest()
            manifest.update(compatible_source_revisions=[HEAD], verification_only=True)
            write_private(directory / "artifact-manifest.json", canonical(manifest))
            migration_url = MigrationSettings().migration_database_url.get_secret_value()
            backup = verify_existing_upgrade(admin, directory, migration_url)
            if catalog(admin) != original_catalog or legacy_catalog(admin) != original_legacy:
                raise RuntimeError("Existing database identity or legacy catalog changed")
            journal(
                directory,
                "closure_succeeded",
                verification=verification,
                request_id=request_id,
                revision=HEAD,
                artifact_sha256=artifact_hash,
                backup_sha256=backup["sha256"],
                restore_seconds=backup["restore_seconds"],
                elapsed_seconds=round((now() - started).total_seconds(), 3),
                history_preserved=True,
                source_and_legacy_preserved=True,
            )
            MARKER.unlink()
            print(f"Private evidence directory: database/backups/{directory.name}", flush=True)
        except Exception as error:
            journal(
                directory,
                "closure_failed",
                verification=verification,
                error_type=type(error).__name__,
                sqlstate=getattr(error, "sqlstate", None),
                maintenance_retained=True,
            )
            raise
    finally:
        admin.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["provision", "rehearse", "retry-verification", "verify-existing"],
    )
    parser.add_argument("--execute", action="store_true", required=True)
    arguments = parser.parse_args()
    try:
        with admin_connection() as admin:
            verify_identity(admin)
            previous = catalog(admin)
            legacy = legacy_catalog(admin)
            if arguments.action == "provision":
                provision(admin)
            elif arguments.action == "retry-verification":
                retry_verification(admin)
            elif arguments.action == "verify-existing":
                verify_existing(admin)
            else:
                rehearse(admin)
            if catalog(admin) != previous or legacy_catalog(admin) != legacy:
                raise RuntimeError("Existing database identity or legacy catalog changed")
    except Exception as error:
        print(
            f"F1 operation stopped ({type(error).__name__}); no automatic reset or retry",
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
