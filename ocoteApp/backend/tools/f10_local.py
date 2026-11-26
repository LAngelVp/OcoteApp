"""Fresh F10 operator capture and ordered isolated gates for one local release."""

import argparse
import getpass
import json
import math
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from urllib.parse import quote, quote_plus
from uuid import UUID

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from tools.f1_local import canonical, private_directory, write_private
from tools.f9_local import APIProcess, api_listeners

OPERATOR_CONTEXT = UUID("090f10c7-8fa4-4d86-b6c1-bcda00926110")
AUTHORIZATION_SECONDS = 3600
PURPOSE = "ocote-f10-local-postgres-only"


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "f10-operator" / "administrator.dpapi"


def save_authorization(password, *, path=None, issued_at=None):
    if (
        not isinstance(password, str)
        or not 1 <= len(password) <= 1024
        or any(value in password for value in "\r\n\x00")
    ):
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    path = Path(path) if path is not None else authorization_path()
    if path.exists() or path.parent.is_symlink() or path.parent.is_junction():
        raise CommandError(503, "FRESH_F10_CAPTURE_REQUIRED_NO_RENEWAL")
    issued = time.time() if issued_at is None else issued_at
    if type(issued) not in {int, float} or not math.isfinite(issued):
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    private_directory(path.parent)
    OSSealedFile(path, OPERATOR_CONTEXT).create(
        json.dumps(
            {
                "purpose": PURPOSE,
                "issued_at": issued,
                "expires_at": issued + AUTHORIZATION_SECONDS,
                "password": password,
            }
        ).encode("utf-8")
    )


def authorization(*, path=None, current_time=None):
    path = Path(path) if path is not None else authorization_path()
    try:
        payload = json.loads(OSSealedFile(path, OPERATOR_CONTEXT).read())
        moment = time.time() if current_time is None else current_time
        if (
            not isinstance(payload, dict)
            or set(payload) != {"purpose", "issued_at", "expires_at", "password"}
            or payload["purpose"] != PURPOSE
            or not isinstance(payload["password"], str)
            or not 1 <= len(payload["password"]) <= 1024
            or any(value in payload["password"] for value in "\r\n\x00")
            or any(
                type(value) not in {int, float} or not math.isfinite(value)
                for value in (payload["issued_at"], payload["expires_at"], moment)
            )
            or payload["expires_at"] - payload["issued_at"] != AUTHORIZATION_SECONDS
            or not payload["issued_at"] <= moment < payload["expires_at"]
        ):
            raise ValueError
        return payload
    except CommandError:
        raise CommandError(503, "LOCAL_AUTHORIZATION_STORAGE_UNAVAILABLE") from None
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED") from None


def authorize():
    if os.environ.get("PGPASSWORD") or not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_FRESH_INTERACTIVE_CAPTURE_REQUIRED")
    print("OCOTE F10 - credencial administrativa PostgreSQL local", flush=True)
    print("Entrada sin eco solo aqui; nunca en el chat. DPAPI F10 propio, TTL60min.", flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Credencial administrativa PostgreSQL local: ")
    save_authorization(password)
    try:
        if authorization()["password"] != password:
            raise CommandError(503, "LOCAL_AUTHORIZATION_READBACK_FAILED")
    except BaseException:
        revoke()
        raise
    print(
        "F10 sellada/verificada; sin conexion PostgreSQL, sin renovar ni reutilizar F8/F9.",
        flush=True,
    )


def revoke():
    from tools.f8_local import authorization_path as f8_path
    from tools.f9_local import authorization_path as f9_path

    for path in (authorization_path(), f9_path(), f8_path()):
        path.unlink(missing_ok=True)
        if path.exists():
            raise CommandError(503, "LOCAL_AUTHORIZATION_REVOCATION_FAILED")
    print("Relevos F8/F9/F10 revocados y ausentes; raices de instancia intactas.", flush=True)


def run_authorized(arguments, payload, output_path):
    remaining = payload["expires_at"] - time.time()
    if remaining <= 0:
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED")
    password = payload["password"]
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=BACKEND_DIR.parent,
        env=dict(
            os.environ, PGPASSWORD=password, OCOTE_RUN_PG_TESTS="1", PYTHONPATH=str(BACKEND_DIR)
        ),
        capture_output=True,
        text=True,
        timeout=remaining,
    )
    outputs = []
    for output, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        for representation in {
            password,
            quote(password, safe=""),
            quote_plus(password),
            json.dumps(password)[1:-1],
            repr(password)[1:-1],
        }:
            output = output.replace(representation, "[REDACTED]")
        outputs.append(output)
        stream.write(output)
    write_private(output_path, "\n".join(outputs).encode("utf-8"))
    return result.returncode


def drain_api():
    try:
        listeners = api_listeners()
        if not listeners:
            print("F10_API_ALREADY_DRAINED", flush=True)
            return
        if len(listeners) != 1 or listeners[0][0] != "127.0.0.1":
            raise OSError("API listener ambiguous or not loopback")
        with APIProcess(listeners[0][1]) as process:
            if not process.verified() or api_listeners() != listeners:
                raise OSError("API ownership not verified")
            process.stop()
        if api_listeners():
            raise OSError("API listener still present")
    except OSError:
        raise CommandError(503, "API_DRAIN_NOT_VERIFIED") from None
    print("F10_API_DRAINED", flush=True)


def run_final_gates(artifacts):
    summary = {"phase": "F10", "stages": [], "release_started": False}
    root = None
    try:
        if os.environ.get("PGPASSWORD") or artifacts is None:
            raise CommandError(422, "PRIVATE_ARTIFACTS_AND_FRESH_SEALED_AUTHORIZATION_REQUIRED")
        candidate = Path(artifacts)
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or candidate.is_junction()
            or candidate.resolve().is_relative_to(BACKEND_DIR.parent.resolve())
        ):
            raise CommandError(422, "PRIVATE_RELEASE_ARTIFACTS_REQUIRED")
        payload = authorization()
        root = candidate.resolve()
        private_directory(root)
        tests = "backend/tests/test_f10.py::"
        stages = [
            (
                "migration-protections",
                [
                    "-m",
                    "pytest",
                    "-q",
                    "--tb=short",
                    tests + "test_real_f10_additive_migration_noop_preservation_and_privileges",
                    tests + "test_real_f10_version_audit_timezone_and_runtime_protections",
                ],
            ),
            ("pg1", ["-m", "pytest", "-q", "--tb=short", "backend/tests"]),
        ]
        for name, arguments in stages:
            started = time.monotonic()
            status = run_authorized(arguments, payload, root / (name + ".txt"))
            summary["stages"].append(
                {"name": name, "status": status, "seconds": round(time.monotonic() - started, 3)}
            )
            if status:
                return status
        if payload["expires_at"] - time.time() < 600:
            raise CommandError(503, "AUTHORIZATION_EXPIRING_NO_RELEASE_STARTED")
        drain_api()
        summary["release_started"] = True
        status = run_authorized(
            ["-m", "tools.f10_release", "--artifacts", str(root)], payload, root / "release.txt"
        )
        summary["stages"].append({"name": "release", "status": status})
        return status
    finally:
        try:
            revoke()
        finally:
            if root is not None:
                write_private(root / "stage-summary.json", canonical(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "revoke", "final-gates"))
    parser.add_argument("--artifacts", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            revoke()
        else:
            return run_final_gates(arguments.artifacts)
        return 0
    except CommandError as error:
        print(error.code, file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("F10_AUTHORIZATION_EXPIRED_ABORTED_REVIEW_UUID_CLEANUP", file=sys.stderr)
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.SubprocessError):
        print("F10_LOCAL_AUTHORIZATION_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
