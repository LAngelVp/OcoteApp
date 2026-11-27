import argparse
import ctypes
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import psycopg
from defusedxml.ElementTree import parse as parse_xml
from psycopg import sql

from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from app.services.installation import canonical, private_directory, write_private

CONTEXT = UUID("917442bc-d239-4813-96cf-a29638f8b352")
ROOT = Path(__file__).resolve().parents[2]


def authorization_path():
    return Path(os.environ["LOCALAPPDATA"]) / "OCOTE/f7-delivery-operator/administrator.dpapi"


def validate_approval(path):
    approval = json.loads(path.read_text())
    if approval.get("phase") != "F7_DELIVERY_CUT1" or approval.get("ready") is not True:
        raise CommandError(409, "DELIVERY_CUT1_NOT_APPROVED")
    for name, digest in approval["files"].items():
        target = (ROOT / name).resolve()
        if (
            not target.is_relative_to(ROOT)
            or hashlib.sha256(target.read_bytes()).hexdigest() != digest
        ):
            raise CommandError(409, "DELIVERY_APPROVAL_CHANGED")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_gate(command, *, cwd, env, log, timeout):
    if os.name != "nt":
        raise CommandError(503, "DELIVERY_PROCESS_PLATFORM_UNVERIFIED")

    class Limits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", ctypes.c_uint32),
            ("minimum", ctypes.c_size_t),
            ("maximum", ctypes.c_size_t),
            ("active", ctypes.c_uint32),
            ("affinity", ctypes.c_size_t),
            ("priority", ctypes.c_uint32),
            ("scheduling", ctypes.c_uint32),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Limits),
            ("io", ctypes.c_uint64 * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    resume = ctypes.WinDLL("ntdll").NtResumeProcess
    resume.argtypes = [ctypes.c_void_p]
    resume.restype = ctypes.c_long
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise CommandError(503, "DELIVERY_PROCESS_JOB_UNAVAILABLE")
    process = None
    attached = False
    try:
        write_private(log, b"")
        limits = Extended()
        limits.basic.flags = 0x2000
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise CommandError(503, "DELIVERY_PROCESS_JOB_UNAVAILABLE")
        with log.open("wb") as output:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=4 | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            if not kernel.AssignProcessToJobObject(job, int(process._handle)):
                raise CommandError(503, "DELIVERY_PROCESS_JOB_UNAVAILABLE")
            attached = True
            if resume(int(process._handle)) < 0:
                raise CommandError(503, "DELIVERY_PROCESS_RESUME_FAILED")
            try:
                return process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return 124
    finally:
        kernel.CloseHandle(job)
        if process is not None:
            if not attached and process.poll() is None:
                process.kill()
            process.wait(timeout=30)


def cleanup_uuids(names, password, artifacts, label):
    if not names:
        return
    if any(not re.fullmatch(r"ocote_f2_(test|restore)_[0-9a-f]{32}", name) for name in names):
        raise CommandError(409, "DELIVERY_CLEANUP_DESTINATION_REJECTED")
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="postgres",
        user="postgres",
        password=password,
        connect_timeout=3,
        autocommit=True,
        options="-c statement_timeout=15000 -c lock_timeout=3000",
        application_name="ocote-delivery-uuid-cleanup",
    ) as connection:
        identity = connection.execute(
            "SELECT current_user,current_setting('server_version_num'),"
            "current_setting('data_directory')"
        ).fetchone()
        if (
            identity[:2] != ("postgres", "180004")
            or Path(identity[2]).resolve() != (ROOT / "database/data").resolve()
        ):
            raise CommandError(409, "DELIVERY_CLEANUP_CLUSTER_REJECTED")
        removed = []
        for name in names:
            found = connection.execute(
                "SELECT pg_get_userbyid(datdba),(SELECT count(*) FROM pg_stat_activity a"
                " WHERE a.datid=d.oid) FROM pg_database d WHERE datname=%s",
                (name,),
            ).fetchone()
            if found is None:
                continue
            if found != ("ocote_migrador", 0):
                raise CommandError(409, "DELIVERY_CLEANUP_OWNERSHIP_OR_SESSIONS")
            write_private(
                artifacts / (label + "-" + name + ".json"),
                canonical(
                    {
                        "database": name,
                        "owner": found[0],
                        "sessions": 0,
                        "action": "DROP DATABASE",
                    }
                ),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            removed.append(name)
        write_private(artifacts / (label + "-complete.json"), canonical({"removed": removed}))


def uuid_databases(password):
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="postgres",
        user="postgres",
        password=password,
        connect_timeout=3,
        autocommit=True,
        application_name="ocote-delivery-uuid-inventory",
    ) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT datname FROM pg_database WHERE datname ~ %s",
                (r"^ocote_f2_(test|restore)_[0-9a-f]{32}$",),
            ).fetchall()
        }


def main():
    parser = argparse.ArgumentParser(description="Explicit F7 delivery Cut2; never run in Cut1")
    parser.add_argument("action", choices=["prepare", "authorize", "final-gates", "revoke"])
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    if arguments.action == "prepare":
        print(
            json.dumps(
                {
                    "prepared_only": True,
                    "postgres_connections": 0,
                    "sequence": ["test_delivery_postgres.py", "full PG1"],
                    "context": str(CONTEXT),
                    "ttl_seconds": 3600,
                    "origin_release": "0011 unchanged; no source apply",
                }
            )
        )
        return
    path = authorization_path()
    if arguments.action == "revoke":
        path.unlink(missing_ok=True)
        return
    if not arguments.execute or not arguments.approval:
        raise CommandError(403, "DELIVERY_EXPLICIT_AUTHORIZATION_REQUIRED")
    if arguments.action == "authorize":
        approval = validate_approval(arguments.approval)
        if path.exists():
            raise CommandError(409, "DELIVERY_CAPTURE_ALREADY_EXISTS")
        private_directory(path.parent)
        password = getpass.getpass("OCOTE F7 final: PostgreSQL administrator (no echo): ")
        if not password:
            raise CommandError(422, "DELIVERY_CAPTURE_EMPTY")
        OSSealedFile(path, CONTEXT).create(
            canonical(
                {
                    "purpose": "f7-delivery-uuid-and-pg1-only",
                    "expires": time.time() + 3600,
                    "approval": approval,
                    "password": password,
                }
            )
        )
        print("F7 delivery authorization sealed; no database connection opened.")
        return
    try:
        approval = validate_approval(arguments.approval)
        sealed = json.loads(OSSealedFile(path, CONTEXT).read())
        if (
            sealed["approval"] != approval
            or sealed["expires"] - time.time() < 1200
            or sealed["purpose"] != "f7-delivery-uuid-and-pg1-only"
        ):
            raise CommandError(403, "DELIVERY_CAPTURE_INVALID_OR_EXPIRED")
        if not arguments.artifacts or arguments.artifacts.exists():
            raise CommandError(409, "DELIVERY_FRESH_EVIDENCE_REQUIRED")
        private_directory(arguments.artifacts)
        approved = json.loads(arguments.approval.read_text())
        cleanup_uuids(
            approved.get("pending_uuid_cleanup", []),
            sealed["password"],
            arguments.artifacts,
            "approved-existing-cleanup",
        )
        if uuid_databases(sealed["password"]):
            raise CommandError(409, "DELIVERY_UNAPPROVED_EXISTING_UUID")
        environment = {
            name: value for name, value in os.environ.items() if not name.startswith("PG")
        }
        environment.update(
            PGPASSWORD=sealed["password"],
            OCOTE_RUN_PG_TESTS="1",
            PYTHONPATH=str(ROOT / "backend"),
            OCOTE_DELIVERY_APPROVAL=str(arguments.approval.resolve()),
        )
        for label, target in [
            ("isolated-install-upgrade", "backend/tests/test_delivery_postgres.py"),
            ("pg1", "backend/tests"),
        ]:
            if sealed["expires"] - time.time() < 900:
                raise CommandError(403, "DELIVERY_CAPTURE_EXPIRED")
            validate_approval(arguments.approval)
            print("F7_DELIVERY_GATE_STARTED=" + label, flush=True)
            junit = arguments.artifacts / (label + ".xml")
            budget = max(1, int(sealed["expires"] - time.time() - 180))
            if label == "isolated-install-upgrade":
                budget = min(budget, 600)
            try:
                returncode = run_gate(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "pytest",
                        "-vv",
                        "--durations=25",
                        "--tb=short",
                        "--junitxml=" + str(junit),
                        target,
                    ],
                    cwd=ROOT,
                    env=environment,
                    log=arguments.artifacts / (label + ".txt"),
                    timeout=budget,
                )
            finally:
                if sealed["expires"] <= time.time():
                    raise CommandError(403, "DELIVERY_CAPTURE_EXPIRED")
                cleanup_uuids(
                    sorted(uuid_databases(sealed["password"])),
                    sealed["password"],
                    arguments.artifacts,
                    label + "-residual-cleanup",
                )
            if returncode == 124:
                write_private(
                    arguments.artifacts / (label + "-timeout.json"),
                    canonical(
                        {
                            "budget_seconds": budget,
                            "capture_expires": sealed["expires"],
                            "capture_renewed": False,
                            "gate_passed": False,
                        }
                    ),
                )
                raise CommandError(409, "DELIVERY_GATE_TIMEOUT") from None
            if returncode:
                raise CommandError(409, "DELIVERY_GATE_FAILED")
            suites = list(parse_xml(junit).getroot().iter("testsuite"))
            summary = {
                field: sum(int(suite.get(field, "0")) for suite in suites)
                for field in ("tests", "failures", "errors", "skipped")
            }
            if (
                not summary["tests"]
                or summary["failures"]
                or summary["errors"]
                or (label == "isolated-install-upgrade" and summary["skipped"])
            ):
                raise CommandError(409, "DELIVERY_GATE_NOT_FULLY_EXECUTED")
            write_private(arguments.artifacts / (label + "-summary.json"), canonical(summary))
            print("F7_DELIVERY_GATE_PASSED=" + label, flush=True)
        write_private(
            arguments.artifacts / "complete.json",
            canonical(
                {
                    "uuid_install_upgrade": "passed",
                    "pg1": "passed",
                    "source_apply": False,
                    "approval": approval,
                }
            ),
        )
    finally:
        path.unlink(missing_ok=True)
        for administrative in (Path(os.environ["LOCALAPPDATA"]) / "OCOTE").glob(
            "f*-operator/administrator.dpapi"
        ):
            administrative.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("F7 delivery stopped safely; credential revoked after gates.", file=sys.stderr)
        raise SystemExit(1) from None
