"""Local F7 operator authorization, PostgreSQL tests and guarded release commands."""

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from uuid import UUID

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from tools.f1_local import private_directory

OPERATOR_CONTEXT = UUID("cbbe8cda-dd1c-4c93-b477-b6a088d831f2")
AUTHORIZATION_SECONDS = 3600


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "f7-operator" / "administrator.dpapi"


def save_authorization(password: str, *, path=None, issued_at=None):
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    path = Path(path) if path is not None else authorization_path()
    if path.parent.is_symlink() or path.parent.is_junction():
        raise CommandError(503, "LOCAL_AUTHORIZATION_PATH_UNSAFE")
    private_directory(path.parent)
    issued = time.time() if issued_at is None else issued_at
    payload = json.dumps(
        {
            "purpose": "ocote-f7-local-postgres-only",
            "issued_at": issued,
            "expires_at": issued + AUTHORIZATION_SECONDS,
            "password": password,
        }
    ).encode("utf-8")
    OSSealedFile(path, OPERATOR_CONTEXT).create(payload)


def authorized_password(*, path=None, current_time=None):
    path = Path(path) if path is not None else authorization_path()
    try:
        payload = json.loads(OSSealedFile(path, OPERATOR_CONTEXT).read())
        current = time.time() if current_time is None else current_time
        if (
            set(payload) != {"purpose", "issued_at", "expires_at", "password"}
            or payload["purpose"] != "ocote-f7-local-postgres-only"
            or not isinstance(payload["password"], str)
            or not 1 <= len(payload["password"]) <= 1024
            or type(payload["issued_at"]) not in {int, float}
            or type(payload["expires_at"]) not in {int, float}
            or payload["expires_at"] - payload["issued_at"] != AUTHORIZATION_SECONDS
            or not payload["issued_at"] <= current < payload["expires_at"]
        ):
            raise ValueError
        return payload["password"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED") from None


def authorize():
    print("OCOTE F7 - autorizacion PostgreSQL local", flush=True)
    print("Entrada sin eco. No escribir la credencial en el chat.", flush=True)
    print(
        "Relevo temporal DPAPI del usuario Windows fuera del checkout; caduca en 60 minutos.",
        flush=True,
    )
    if not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_INTERACTIVE_TERMINAL_REQUIRED")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Credencial administrativa PostgreSQL local: ")
    save_authorization(password)
    print("Autorizacion temporal sellada. No se conecto ni modifico PostgreSQL.", flush=True)


def run_pg_tests():
    password = authorized_password()
    environment = dict(os.environ, PGPASSWORD=password, OCOTE_RUN_PG_TESTS="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "backend/tests"],
        cwd=BACKEND_DIR.parent,
        env=environment,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout.replace(password, "[REDACTED]"))
    sys.stderr.write(result.stderr.replace(password, "[REDACTED]"))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("authorize", "revoke", "pg-tests", "check-release", "apply")
    )
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            authorization_path().unlink(missing_ok=True)
            print("Relevo temporal eliminado; no se modifico ninguna clave de instancia.")
        elif arguments.command in {"check-release", "apply"}:
            if not arguments.execute:
                parser.error("Release rehearsal/application requires --execute")
            from tools.f7_release import apply, check_release

            os.environ["PGPASSWORD"] = authorized_password()
            try:
                if arguments.command == "check-release":
                    check_release()
                else:
                    if arguments.artifacts is None:
                        parser.error("apply requires private --artifacts outside checkout")
                    apply(arguments.artifacts)
            finally:
                os.environ.pop("PGPASSWORD", None)
        else:
            return run_pg_tests()
        return 0
    except CommandError as error:
        print(error.code, file=sys.stderr)
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.SubprocessError):
        print("LOCAL_AUTHORIZATION_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
