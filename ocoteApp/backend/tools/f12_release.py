"""F12 local controlled release; execution requires a fresh F12 seal and ordered gates."""

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
from tools import f11_release as shared
from tools import f12_local as operator

local, previous = shared.local, shared.previous
SOURCE, HEAD = "20261126_0010", "20261126_0011"
ADDED = frozenset({"import_jobs", "import_rows", "export_jobs", "retention_policies",
                   "backup_records"})
APPEND_ONLY = frozenset({"import_rows", "export_jobs", "backup_records"})


def require(condition, code):
    if not condition:
        raise shared.ReleaseFailure(code)


def authorization_budget():
    payload = operator.authorization()
    require(payload["password"] == os.environ.get("PGPASSWORD") and
            payload["expires_at"] - operator.time.time() >= 900,
            "FRESH_F12_AUTHORIZATION_BUDGET_REQUIRED")


def quiet(admin):
    require(not admin.execute("SELECT count(*) FROM pg_stat_activity WHERE "
                              "datname=current_database() AND pid<>pg_backend_pid()").fetchone()[0],
            "F12_OTHER_SESSIONS_PRESENT")
    require(not admin.execute("SELECT count(*) FROM pg_database "
                              "WHERE datname ~ '_[0-9a-f]{32}$'").fetchone()[0],
            "F12_UUID_DATABASES_PRESENT")
    require(not operator.previous.api_listeners(), "F12_API_MUST_BE_DRAINED")


def upgraded(before, after):
    require(not set(before["tables"]) - set(after["tables"]) and
            set(after["tables"]) - set(before["tables"]) == ADDED,
            "F12_ADDITIVE_TABLE_SET_DIFFERS")
    require(after["rows"]["alembic_version"] == [json.dumps({"version_num": HEAD})],
            "F12_REVISION_DIFFERS")
    require(not any(after["rows"][table] for table in ADDED), "F12_UNSOLICITED_DEFAULTS")
    shared.preserved(before, after)


def verify_runtime(database):
    shared.verify_runtime(database)
    with local.role_connection(Settings().database_url.get_secret_value(), database) as connection:
        require(connection.execute("SELECT current_user").fetchone()[0] == "ocote_runtime",
                "F12_RUNTIME_IDENTITY_REQUIRED")
        for table in ADDED:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                expected = privilege in {"SELECT", "INSERT"} or (
                    privilege == "UPDATE" and table not in APPEND_ONLY
                )
                actual = connection.execute("SELECT has_table_privilege(current_user,%s,%s)",
                                             (table, privilege)).fetchone()[0]
                require(actual == expected, "F12_RUNTIME_PRIVILEGES_DIFFER")


def restored(directory, label, baseline, *, upgrade=False, root_seal=None):
    url = MigrationSettings().migration_database_url.get_secret_value()
    with previous.isolated_database("restore") as destination:
        with shared.verification(directory, label, "pg_restore"):
            shared.pg_run([
                str(local.PG_BIN / "pg_restore"), "-w", "-h", "127.0.0.1", "-p", "5432",
                "-U", local.MIGRATOR, "-d", destination, "--exit-on-error", "--no-owner",
                str(directory / (label + ".dump")),
            ], make_url(url).password)
        with local.role_connection(url, destination) as connection:
            with shared.verification(directory, label, "snapshot_compare"):
                recovered = previous.snapshot(connection)
                with local.role_connection(url) as source:
                    equivalent = shared.compare_restored(baseline, recovered, source, connection)
                    shared.compare_security_catalog(source, connection)
                if any(equivalent.values()):
                    local.journal(directory, "f12_restore_equivalent", label=label, **equivalent)
            if upgrade:
                with shared.verification(directory, label, "isolated_upgrade"):
                    previous.upgrade(destination, HEAD)
                    after = previous.snapshot(connection)
                    upgraded(baseline, after)
                    previous.upgrade(destination, HEAD)
                    require(previous.snapshot(connection) == after, "F12_RESTORE_NOOP_DIFFERS")
            with shared.verification(directory, label, "runtime_grants"):
                verify_runtime(destination)
        if root_seal is not None:
            with shared.verification(directory, label, "vault"):
                shared.verify_vault(destination, root_seal)
    local.journal(directory, "f12_restore_verified", label=label, upgraded=upgrade,
                  vault_verified=root_seal is not None)


def backup(admin, directory, label, *, upgrade=False, root_seal=None):
    baseline = previous.snapshot(admin)
    dump = directory / (label + ".dump")
    local.write_private(dump, b"")
    shared.pg_run([
        str(local.PG_BIN / "pg_dump"), "-w", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres",
        "-d", local.DATABASE_NAME, "--format=custom", "--file=" + str(dump),
    ], os.environ["PGPASSWORD"])
    restored(directory, label, baseline, upgrade=upgrade, root_seal=root_seal)
    require(previous.snapshot(admin) == baseline, "F12_ORIGIN_CHANGED_DURING_BACKUP")
    manifest = {"sha256": local.digest(dump), "bytes": dump.stat().st_size,
                "verified_at": local.now(),
                "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest()}
    local.write_private(directory / (label + "-manifest.json"), local.canonical(manifest))
    return manifest


def apply(artifacts):
    authorization_budget()
    candidate = Path(artifacts)
    require(candidate.is_absolute() and not any(
        path.is_symlink() or path.is_junction() for path in (candidate, *candidate.parents)
    ), "F12_PRIVATE_ARTIFACT_PATH_REQUIRED")
    root = candidate.resolve()
    require(not root.is_relative_to(local.ROOT.resolve()), "F12_ARTIFACTS_OUTSIDE_CHECKOUT")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        require(not local.MARKER.exists(), "F12_EXISTING_MAINTENANCE_REQUIRES_DECISION")
        require(admin.execute("SELECT version_num FROM alembic_version").fetchall() == [(SOURCE,)],
                "F12_REQUIRES_SOURCE0010_NEVER_REPEAT0011")
        require(admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0],
                "F12_RELEASE_LOCK_HELD")
        try:
            quiet(admin)
            local.private_directory(root)
            size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            require(shutil.disk_usage(root).free >= size * 6 + 134217728,
                    "F12_INSUFFICIENT_BACKUP_SPACE")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f12-" + str(attempt))
            local.private_directory(directory)
            local.write_private(directory / "events.jsonl", b"")
            local.private_directory(local.LOCAL)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt, "phase": "F12"}))
            try:
                require(admin.execute("SELECT pg_try_advisory_lock(%s)",
                                      (CONFIG_LOCK,)).fetchone()[0], "F12_CONFIG_LOCK_HELD")
                before = previous.snapshot(admin)
                require(len(before["tables"]) == 67 and
                        len(before["rows"]["release_history"]) == 11 and all(
                            json.loads(row)["status"] in {"succeeded", "failed"}
                            for row in before["rows"]["release_history"]
                        ), "F12_EXACT_F11_TERMINAL_ORIGIN_REQUIRED")
                catalog, legacy = local.catalog(admin), local.legacy_catalog(admin)
                instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
                root_path = seal_path(instance)
                root_hash = local.digest(root_path)
                local.write_private(directory / "master.dpapi", root_path.read_bytes())
                files = shared.artifact_files()
                manifest = {"files": files, "source_revision": SOURCE, "target_revision": HEAD,
                            "scope": "local_only", "customer_package": False}
                local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
                local.journal(directory, "f12_started", attempt=attempt, request_id=request_id)
                verified = backup(admin, directory, "before", upgrade=True, root_seal=root_path)
                authorization_budget()
                previous.upgrade(local.DATABASE_NAME, HEAD)
                migrated = previous.snapshot(admin)
                upgraded(before, migrated)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                require(previous.snapshot(admin) == migrated, "F12_ORIGIN_NOOP_DIFFERS")
                verify_runtime(local.DATABASE_NAME)
                shared.verify_vault(local.DATABASE_NAME, root_path)
                security = shared.security_catalog(admin)
                url = MigrationSettings().migration_database_url.get_secret_value()
                with local.role_connection(url) as connection:
                    connection.execute(
                        "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,"
                        "backup_verified_at,request_id) VALUES(%s,%s,%s,'0.12.0',%s,%s,%s,%s,%s,"
                        "'local','validation','running',%s,%s,%s)",
                        (attempt, started, local.now(),
                         hashlib.sha256(local.canonical(files)).hexdigest(),
                         local.digest(directory / "artifact-manifest.json"), SOURCE, HEAD,
                         "LUIS ANGEL VALLEJO - DESARROLLADOR",
                         local.digest(directory / "before-manifest.json"),
                         verified["verified_at"], request_id),
                    )
                backup(admin, directory, "recorded", root_seal=root_path)
                authorization_budget()
                quiet(admin)
                require(shared.security_catalog(admin) == security and
                    local.catalog(admin) == catalog and
                    local.legacy_catalog(admin) == legacy and
                        local.digest(root_path) == root_hash and shared.artifact_files() == files,
                        "F12_PRE_CAS_INVARIANTS_CHANGED")
                with local.role_connection(url) as connection:
                    require(connection.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                        "status='succeeded',phase='complete',result_code='F12_LOCAL_VERIFIED' "
                        "WHERE id=%s AND request_id=%s AND version=1 AND status='running' "
                        "AND phase='validation' AND source_revision=%s AND target_revision=%s",
                        (local.now(), local.now(), attempt, request_id, SOURCE, HEAD),
                    ).rowcount == 1, "F12_OWN_LEDGER_CAS_FAILED")
                backup(admin, directory, "terminal", root_seal=root_path)
                final = previous.snapshot(admin)
                shared.preserved(before, final, ledger=True)
                previous_ids = {json.loads(row)["id"] for row in before["rows"]["release_history"]}
                final_rows = [json.loads(row) for row in final["rows"]["release_history"]]
                own = [row for row in final_rows if row["id"] == str(attempt)]
                require({row["id"] for row in final_rows} - previous_ids == {str(attempt)} and
                        len(final_rows) == 12 and len(final["tables"]) == 72 and len(own) == 1 and
                        own[0]["version"] == 2 and own[0]["status"] == "succeeded" and
                        own[0]["result_code"] == "F12_LOCAL_VERIFIED" and
                        not any(final["rows"][table] for table in ADDED),
                        "F12_FINAL_LEDGER_OR_DATA_DIFFERS")
                quiet(admin)
                require(shared.security_catalog(admin) == security and
                    local.catalog(admin) == catalog and
                    local.legacy_catalog(admin) == legacy and
                        local.digest(root_path) == root_hash and shared.artifact_files() == files,
                        "F12_FINAL_INVARIANTS_CHANGED")
                require(operator.authorization()["expires_at"] > operator.time.time(),
                        "F12_AUTHORIZATION_EXPIRED")
                local.journal(directory, "f12_succeeded", attempt=attempt, revision=HEAD,
                              instance_id=instance, tables=72, historical_values_preserved=True)
                local.MARKER.unlink()
                return directory
            except Exception as error:
                local.journal(directory, "f12_failed", error_type=type(error).__name__,
                              diagnostic=({"code": error.code, **error.details}
                                          if isinstance(error, shared.ReleaseFailure) else None),
                              maintenance_retained=local.MARKER.exists())
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
        print("F12_RELEASE_FAILED_" + (error.code if isinstance(error, shared.ReleaseFailure)
                                      else type(error).__name__))
        return 1
    finally:
        operator.revoke()


if __name__ == "__main__":
    raise SystemExit(main())