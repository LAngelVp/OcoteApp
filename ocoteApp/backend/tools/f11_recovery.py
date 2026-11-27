"""Prepared contingency for the existing F11 validation attempt; never runs Alembic."""

import argparse
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings
from app.core.security import CONFIG_LOCK
from app.services.platform import seal_path
from tools import f11_local as operator
from tools import f11_release as release

local, previous = release.local, release.previous
ATTEMPT = UUID("2fa9dc8d-7028-4f24-8000-f468897b0bb4")
REQUEST = UUID("93731b27-42a7-4e5f-b3b7-181b6ce4c267")
EVIDENCE = {
    "artifact-manifest.json": "666f9e5bd2f06097c0990fcfa0ebd6c611dc808ceab05c9aacf17a9d4a50c24a",
    "before-manifest.json": "6966247495dd2a171d3c4f663c9998ec25d734343b23a3ba45028d1beda43976",
    "before.dump": "6f0752086ccf2700c4d4ccdd0711240c22d84fc9cc8e87943fcea7f653b49629",
    "events.jsonl": "eb23cf956cd810c0ab85e57bc5ba0aaeb6ea872699b63c2eb3aa5dafa9f6781f",
    "master.dpapi": "08dd2b0cfd5fa274ed2c953e81bc8da157c92680201019d80462fd56940bd8c4",
    "recorded.dump": "d2d92fd8196e1d106c1849212980992b58f0addcf64e7cabed926deb6f8deee8",
}
TOOLS = frozenset({
    "backend/tools/f11_release.py", "backend/tools/f11_local.py", "backend/tools/f11_recovery.py",
})


def require(condition, code):
    if not condition:
        raise release.ReleaseFailure(code)


def private_path(value):
    from pathlib import Path

    supplied = Path(value)
    require(supplied.is_absolute() and not any(
        path.is_symlink() or path.is_junction() for path in (supplied, *supplied.parents)
    ), "RECOVERY_PRIVATE_ABSOLUTE_PATH_REQUIRED")
    path = supplied.resolve()
    require(not path.is_relative_to(local.ROOT.resolve()), "RECOVERY_ARTIFACTS_OUTSIDE_CHECKOUT")
    return path


def verify_evidence(source):
    require(source.name == "f11-" + str(ATTEMPT), "RECOVERY_ATTEMPT_DIRECTORY_DIFFERS")
    require({path.name for path in source.iterdir()} == set(EVIDENCE),
            "ORIGINAL_EVIDENCE_SET_DIFFERS")
    for name, digest in EVIDENCE.items():
        path = source / name
        require(path.is_file() and not path.is_symlink() and local.digest(path) == digest,
                "ORIGINAL_EVIDENCE_HASH_DIFFERS")


def verify_tools(source, approved):
    manifest = json.loads((source / "artifact-manifest.json").read_bytes())
    require(manifest["source_revision"] == release.SOURCE and
            manifest["target_revision"] == release.HEAD, "ORIGINAL_MANIFEST_REVISION_DIFFERS")
    original, current = manifest["files"], release.artifact_files()
    changes = {name for name in original.keys() | current.keys()
               if original.get(name) != current.get(name)}
    require(changes == TOOLS and TOOLS <= current.keys(), "UNAPPROVED_ARTIFACT_DELTA")
    tools = {name: current[name] for name in sorted(TOOLS)}
    require(hashlib.sha256(local.canonical(tools)).hexdigest() == approved,
            "RECOVERY_TOOL_APPROVAL_HASH_DIFFERS")
    return current


def verify_marker():
    require(not local.MARKER.is_symlink() and
            json.loads(local.MARKER.read_bytes()) == {"attempt": str(ATTEMPT), "phase": "F11"},
            "OWNED_F11_MAINTENANCE_REQUIRED")


@contextmanager
def locked(admin):
    require(admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0],
            "RECOVERY_RELEASE_LOCK_HELD")
    try:
        require(admin.execute("SELECT pg_try_advisory_lock(%s)", (CONFIG_LOCK,)).fetchone()[0],
                "RECOVERY_CONFIG_LOCK_HELD")
        try:
            yield
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
    finally:
        admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def quiet(admin):
    require(not admin.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
        "AND pid<>pg_backend_pid()"
    ).fetchone()[0], "RECOVERY_OTHER_SESSIONS_PRESENT")
    require(not admin.execute(
        "SELECT count(*) FROM pg_database WHERE datname ~ '_[0-9a-f]{32}$'"
    ).fetchone()[0], "RECOVERY_UUID_DATABASES_PRESENT")
    require(not operator.api_listeners(), "RECOVERY_API_MUST_REMAIN_STOPPED")


def state(snapshot, source):
    require(len(snapshot["tables"]) == 67 and
            snapshot["rows"]["alembic_version"] == [json.dumps({"version_num": release.HEAD})],
            "RECOVERY_REQUIRES_HEAD0010_AND_67_TABLES")
    require(not any(snapshot["rows"][name] for name in release.ADDED), "F11_TABLES_NOT_EMPTY")
    rows = [json.loads(row) for row in snapshot["rows"]["release_history"]]
    own = [row for row in rows if row["id"] == str(ATTEMPT)]
    manifest = json.loads((source / "artifact-manifest.json").read_bytes())
    require(len(rows) == 11 and len(own) == 1, "RECOVERY_LEDGER_SET_DIFFERS")
    expected = {
        "request_id": str(REQUEST), "source_revision": release.SOURCE,
        "target_revision": release.HEAD, "application_version": "0.11.0",
        "deployment_mode": "local", "phase": "validation", "status": "running",
        "version": 1, "result_code": None, "finished_at": None,
        "artifact_sha256": hashlib.sha256(local.canonical(manifest["files"])).hexdigest(),
        "manifest_sha256": EVIDENCE["artifact-manifest.json"],
        "backup_manifest_sha256": EVIDENCE["before-manifest.json"],
    }
    require(all(own[0].get(key) == value for key, value in expected.items()),
            "RECOVERY_OWN_RUNNING_VALIDATION_V1_REQUIRED")
    require(all(row["status"] in {"succeeded", "failed"} for row in rows
                if row["id"] != str(ATTEMPT)), "RECOVERY_OTHER_RUNNING_RELEASE")


def restore_before(directory, root_seal):
    url = MigrationSettings().migration_database_url.get_secret_value()
    with previous.isolated_database("restore") as destination:
        release.pg_run([
            str(local.PG_BIN / "pg_restore"), "-w", "-h", "127.0.0.1", "-p", "5432",
            "-U", local.MIGRATOR, "-d", destination, "--exit-on-error", "--no-owner",
            str(directory / "before.dump"),
        ], make_url(url).password)
        with local.role_connection(url, destination) as connection:
            before = previous.snapshot(connection)
        release.verify_f10_runtime(destination)
        release.verify_vault(destination, root_seal)
    local.journal(directory, "f11_recovery_before_restored_without_upgrade")
    return before


def terminal(admin, directory, baseline, root_seal):
    url = MigrationSettings().migration_database_url.get_secret_value()
    with local.role_connection(url) as connection:
        require(connection.execute(
            "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
            "status='succeeded',phase='complete',result_code='F11_LOCAL_VERIFIED' "
            "WHERE id=%s AND request_id=%s AND version=1 AND status='running' "
            "AND phase='validation' AND target_revision=%s AND source_revision=%s",
            (local.now(), local.now(), ATTEMPT, REQUEST, release.HEAD, release.SOURCE),
        ).rowcount == 1, "RECOVERY_LEDGER_CAS_FAILED")
    local.journal(directory, "f11_recovery_own_ledger_terminal", attempt=ATTEMPT)
    release.backup(admin, directory, "terminal", root_seal=root_seal)
    final = previous.snapshot(admin)
    expected_rows = [json.loads(row) for row in baseline["rows"]["release_history"]]
    actual_rows = [json.loads(row) for row in final["rows"]["release_history"]]
    expected = next(row for row in expected_rows if row["id"] == str(ATTEMPT))
    actual = next(row for row in actual_rows if row["id"] == str(ATTEMPT))
    require(actual["version"] == 2 and actual["status"] == "succeeded" and
            actual["phase"] == "complete" and actual["result_code"] == "F11_LOCAL_VERIFIED"
            and actual["finished_at"] is not None, "RECOVERY_TERMINAL_STATE_DIFFERS")
    allowed = {"version", "status", "phase", "result_code", "finished_at", "updated_at"}
    require({key: value for key, value in actual.items() if key not in allowed} ==
            {key: value for key, value in expected.items() if key not in allowed},
            "RECOVERY_OWN_LEDGER_UNEXPECTED_CHANGE")
    historical = {**baseline, "rows": {**baseline["rows"], "release_history": [
        row for row in baseline["rows"]["release_history"] if json.loads(row)["id"] != str(ATTEMPT)
    ]}}
    release.preserved(historical, final, ledger=True)
    require({key: value for key, value in baseline.items() if key != "rows"} ==
            {key: value for key, value in final.items() if key != "rows"} and
            len(actual_rows) == len(expected_rows), "RECOVERY_SCHEMA_OR_LEDGER_SET_CHANGED")


def recover(original, artifacts, approved):
    source, root = private_path(original), private_path(artifacts)
    verify_evidence(source)
    files = verify_tools(source, approved)
    verify_marker()
    require(not root.is_relative_to(source) and not source.is_relative_to(root),
            "RECOVERY_EVIDENCE_MUST_BE_SEPARATE")
    payload = operator.authorization()
    require(os.environ.get("PGPASSWORD") == payload["password"] and
            payload["expires_at"] - operator.time.time() >= 900,
            "FRESH_F11_RECOVERY_AUTHORIZATION_REQUIRED")
    directory = root / ("f11-recovery-" + str(uuid4()))
    local.private_directory(directory)
    local.write_private(directory / "events.jsonl", b"")
    local.write_private(directory / "recovery-manifest.json", local.canonical({
        "attempt": ATTEMPT, "original_evidence": EVIDENCE, "files": files,
        "approved_tools_sha256": approved, "reapplies_migration": False,
    }))
    try:
        with local.admin_connection() as admin:
            local.verify_identity(admin)
            with locked(admin):
                quiet(admin)
                verify_marker()
                baseline = previous.snapshot(admin)
                state(baseline, source)
                require(not admin.execute(
                    "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace "
                    "AND NOT convalidated"
                ).fetchone()[0], "RECOVERY_UNVALIDATED_CONSTRAINTS")
                instance = admin.execute("SELECT id FROM deployment_instances").fetchall()
                require(len(instance) == 1, "RECOVERY_INSTANCE_COUNT_DIFFERS")
                root_seal = seal_path(instance[0][0])
                require(local.digest(root_seal) == EVIDENCE["master.dpapi"],
                        "RECOVERY_INSTANCE_ROOT_DIFFERS")
                catalog, legacy = local.catalog(admin), local.legacy_catalog(admin)
                security = release.security_catalog(admin)
                size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
                require(shutil.disk_usage(directory).free >= size * 6 + 134217728,
                        "RECOVERY_INSUFFICIENT_SPACE")
                for name in ("before.dump", "recorded.dump"):
                    local.write_private(directory / name, (source / name).read_bytes())
                before = restore_before(directory, root_seal)
                historical = {**baseline, "rows": {**baseline["rows"], "release_history": [
                    row for row in baseline["rows"]["release_history"]
                    if json.loads(row)["id"] != str(ATTEMPT)
                ]}}
                require(len(before["tables"]) == 58 and
                        len(before["rows"]["release_history"]) == 10,
                        "RECOVERY_BEFORE_SNAPSHOT_DIFFERS")
                release.upgraded(before, historical)
                release.restored(directory, "recorded", baseline, root_seal=root_seal)
                local.write_private(directory / "recorded-manifest.json", local.canonical({
                    "sha256": EVIDENCE["recorded.dump"], "verified_at": local.now(),
                    "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest(),
                }))
                require(previous.snapshot(admin) == baseline, "RECOVERY_ORIGIN_CHANGED")
                quiet(admin)
                verify_marker()
                verify_evidence(source)
                require(verify_tools(source, approved) == files, "RECOVERY_ARTIFACT_CHANGED")
                require(operator.authorization()["expires_at"] - operator.time.time() >= 900,
                    "RECOVERY_TERMINAL_AUTHORIZATION_BUDGET_REQUIRED")
                require(local.catalog(admin) == catalog and
                    local.legacy_catalog(admin) == legacy and
                    local.digest(root_seal) == EVIDENCE["master.dpapi"],
                    "RECOVERY_PRE_TERMINAL_IDENTITY_OR_ROOT_CHANGED")
                require(release.security_catalog(admin) == security,
                    "RECOVERY_PRE_TERMINAL_SECURITY_CATALOG_CHANGED")
                terminal(admin, directory, baseline, root_seal)
                quiet(admin)
                require(local.catalog(admin) == catalog and
                        local.legacy_catalog(admin) == legacy and
                        local.digest(root_seal) == EVIDENCE["master.dpapi"],
                        "RECOVERY_IDENTITY_OR_ROOT_CHANGED")
                require(release.security_catalog(admin) == security,
                        "RECOVERY_SECURITY_CATALOG_CHANGED")
                verify_evidence(source)
                require(verify_tools(source, approved) == files, "RECOVERY_ARTIFACT_CHANGED")
                verify_marker()
                require(operator.authorization()["expires_at"] > operator.time.time(),
                        "RECOVERY_AUTHORIZATION_EXPIRED")
                local.journal(directory, "f11_recovery_verified", attempt=ATTEMPT,
                              revision=release.HEAD, api_started=False)
                local.MARKER.unlink()
        return directory
    except Exception as error:
        local.journal(directory, "f11_recovery_failed", error_type=type(error).__name__,
                      diagnostic=({"code": error.code, **error.details}
                                  if isinstance(error, release.ReleaseFailure) else None),
                      maintenance_retained=local.MARKER.exists())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--approved-tools-sha256", required=True)
    arguments = parser.parse_args()
    try:
        recover(arguments.original, arguments.artifacts, arguments.approved_tools_sha256)
        return 0
    except Exception as error:
        print("F11_RECOVERY_FAILED_" + (
            error.code if isinstance(error, release.ReleaseFailure) else type(error).__name__
        ))
        return 1
    finally:
        operator.revoke()


if __name__ == "__main__":
    raise SystemExit(main())