"""Fresh F11 operator capture and ordered isolated gates for one local release."""

import argparse
import getpass
import json
import math
import os
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path
from uuid import UUID

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from tools.f1_local import canonical, private_directory, write_private
from tools.f9_local import APIProcess, api_listeners
from tools.f10_local import run_authorized

OPERATOR_CONTEXT = UUID("e8d11c63-0bdf-48fd-95c4-f2ef9041b511")
AUTHORIZATION_SECONDS = 3600
PURPOSE = "ocote-f11-local-postgres-only"


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "f11-operator" / "administrator.dpapi"


def authorization_paths():
    from tools.f8_local import authorization_path as f8_path
    from tools.f9_local import authorization_path as f9_path
    from tools.f10_local import authorization_path as f10_path

    return (authorization_path(), f10_path(), f9_path(), f8_path())


def save_authorization(password, *, path=None, issued_at=None):
    if (
        not isinstance(password, str)
        or not 1 <= len(password) <= 1024
        or any(value in password for value in "\r\n\x00")
    ):
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    path = Path(path) if path is not None else authorization_path()
    if path.exists() or path.parent.is_symlink() or path.parent.is_junction():
        raise CommandError(503, "FRESH_F11_CAPTURE_REQUIRED_NO_RENEWAL")
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


def preflight(*, captured=False):
    if os.environ.get("PGPASSWORD"):
        raise CommandError(503, "RUNTIME_MUST_NOT_INHERIT_ADMINISTRATIVE_PASSWORD")
    paths = authorization_paths()
    if any(path.exists() for path in paths[1:]) or paths[0].exists() != captured:
        raise CommandError(503, "FRESH_F11_CAPTURE_REQUIRED_NO_RENEWAL")
    listeners = api_listeners()
    if listeners:
        if len(listeners) != 1 or listeners[0][0] != "127.0.0.1":
            raise CommandError(503, "API_OWNERSHIP_NOT_VERIFIED")
        with APIProcess(listeners[0][1]) as process:
            if not process.verified() or api_listeners() != listeners:
                raise CommandError(503, "API_OWNERSHIP_NOT_VERIFIED")
    ports = {}
    for port in (8443, 8445):
        with socket.socket() as connection:
            connection.settimeout(2)
            ports[str(port)] = connection.connect_ex(("127.0.0.1", port)) == 0
    if ports["8445"]:
        raise CommandError(503, "F11_PREVIEW_MUST_BE_CLOSED")
    report = {"phase": "F11", "captured": captured, "api": listeners, "ports": ports}
    print(json.dumps(report), flush=True)
    return report


def authorize():
    if os.environ.get("PGPASSWORD") or not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_FRESH_INTERACTIVE_CAPTURE_REQUIRED")
    preflight()
    print("OCOTE F11 - credencial administrativa PostgreSQL local", flush=True)
    print("Entrada sin eco solo aqui; nunca en el chat. DPAPI F11 propio, TTL60min.", flush=True)
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
        "F11 sellada/verificada; sin conexion PostgreSQL, sin renovar/reutilizar sellos.",
        flush=True,
    )


def revoke():
    failed = False
    for path in authorization_paths():
        try:
            path.unlink(missing_ok=True)
            failed = path.exists() or failed
        except OSError:
            failed = True
    if failed:
        raise CommandError(503, "LOCAL_AUTHORIZATION_REVOCATION_FAILED")
    print("Relevos F8/F9/F10/F11 revocados y ausentes; raices de instancia intactas.", flush=True)


def drain_api():
    try:
        listeners = api_listeners()
        if not listeners:
            print("F11_API_ALREADY_DRAINED", flush=True)
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
    print("F11_API_DRAINED", flush=True)


def run_final_gates(artifacts):
    summary = {"phase": "F11", "stages": [], "release_started": False}
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
        preflight(captured=True)
        root = candidate.resolve()
        private_directory(root)
        tests = "backend/tests/test_f11_postgres.py::"
        stages = [
            (
                "migration-protections",
                [
                    "-m", "pytest", "-q", "--tb=short",
                    tests + "test_real_f11_additive_migration_noop_preservation_and_privileges",
                    tests + "test_real_f11_version_audit_and_runtime_protections",
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
            ["-m", "tools.f11_release", "--artifacts", str(root)], payload, root / "release.txt"
        )
        summary["stages"].append({"name": "release", "status": status})
        return status
    finally:
        try:
            revoke()
        finally:
            if root is not None:
                write_private(root / "stage-summary.json", canonical(summary))


def run_recovery(artifacts, original, approved_tools_sha256):
    try:
        if os.environ.get("PGPASSWORD") or any(
            value is None for value in (artifacts, original, approved_tools_sha256)
        ):
            raise CommandError(422, "PRIVATE_RECOVERY_INPUTS_REQUIRED")
        from tools.f11_recovery import private_path, verify_evidence, verify_tools

        root, source = private_path(artifacts), private_path(original)
        if root.exists() or root.is_relative_to(source) or source.is_relative_to(root):
            raise CommandError(422, "NEW_SEPARATE_RECOVERY_DIRECTORY_REQUIRED")
        verify_evidence(source)
        verify_tools(source, approved_tools_sha256)
        payload = authorization()
        preflight(captured=True)
        if api_listeners():
            raise CommandError(503, "RECOVERY_REQUIRES_API_ALREADY_STOPPED")
        if payload["expires_at"] - time.time() < 900:
            raise CommandError(503, "AUTHORIZATION_EXPIRING_NO_RECOVERY_STARTED")
        private_directory(root)
        return run_authorized(
            ["-m", "tools.f11_recovery", "--original", str(source), "--artifacts", str(root),
             "--approved-tools-sha256", approved_tools_sha256], payload, root / "recovery.txt",
        )
    finally:
        revoke()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("preflight", "authorize", "revoke", "final-gates", "recover"),
    )
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--approved-tools-sha256")
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            revoke()
        elif arguments.command == "preflight":
            preflight()
        elif arguments.command == "recover":
            return run_recovery(
                arguments.artifacts, arguments.original, arguments.approved_tools_sha256,
            )
        else:
            return run_final_gates(arguments.artifacts)
        return 0
    except CommandError as error:
        print(error.code, file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("F11_AUTHORIZATION_EXPIRED_ABORTED_REVIEW_UUID_CLEANUP", file=sys.stderr)
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.SubprocessError):
        print("F11_LOCAL_AUTHORIZATION_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())