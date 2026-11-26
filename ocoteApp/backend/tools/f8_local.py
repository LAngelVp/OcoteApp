"""Explicit F8 local PostgreSQL authorization and isolated test runner."""

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
from tools.f1_local import private_directory

OPERATOR_CONTEXT = UUID("2bde9193-ece0-4a81-8699-661b72558455")
AUTHORIZATION_SECONDS = 3600
PURPOSE = "ocote-f8-local-postgres-only"


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "f8-operator" / "administrator.dpapi"


def save_authorization(password, *, path=None, issued_at=None):
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    path = Path(path) if path is not None else authorization_path()
    if path.parent.is_symlink() or path.parent.is_junction():
        raise CommandError(503, "LOCAL_AUTHORIZATION_PATH_UNSAFE")
    private_directory(path.parent)
    issued = time.time() if issued_at is None else issued_at
    if type(issued) not in {int, float} or not math.isfinite(issued):
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    payload = json.dumps(
        {
            "purpose": PURPOSE,
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
            or payload["purpose"] != PURPOSE
            or not isinstance(payload["password"], str)
            or not 1 <= len(payload["password"]) <= 1024
            or type(payload["issued_at"]) not in {int, float}
            or type(payload["expires_at"]) not in {int, float}
            or not math.isfinite(payload["issued_at"])
            or not math.isfinite(payload["expires_at"])
            or payload["expires_at"] - payload["issued_at"] != AUTHORIZATION_SECONDS
            or not payload["issued_at"] <= current < payload["expires_at"]
        ):
            raise ValueError
        return payload["password"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED") from None


def authorize():
    print("OCOTE F8 - autorizacion PostgreSQL local", flush=True)
    print("Entrada sin eco. No escribir la credencial en el chat.", flush=True)
    print("Relevo DPAPI privado de 60 minutos, distinto del relevo historico F7.", flush=True)
    if not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_INTERACTIVE_TERMINAL_REQUIRED")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Credencial administrativa PostgreSQL local: ")
    save_authorization(password)
    print("Autorizacion sellada; PostgreSQL no fue conectado ni modificado.", flush=True)


def run_pg_tests(test_slice):
    password = authorized_password()
    environment = dict(os.environ, PGPASSWORD=password, OCOTE_RUN_PG_TESTS="1")
    target = {
        "f8": "backend/tests/test_f8.py",
        "identity": "backend/tests/test_identity.py",
        "analytics": "backend/tests/test_analytics.py",
        "all": "backend/tests",
    }[test_slice]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", target],
        cwd=BACKEND_DIR.parent,
        env=environment,
        capture_output=True,
        text=True,
    )
    for output, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        for representation in {password, quote(password, safe=""), quote_plus(password)}:
            output = output.replace(representation, "[REDACTED]")
        stream.write(output)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "revoke", "pg-tests", "apply", "resume"))
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--test-slice", choices=("f8", "identity", "analytics", "all"), default="f8"
    )
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            authorization_path().unlink(missing_ok=True)
            print("Relevo F8 eliminado; ninguna clave de instancia fue modificada.")
        elif arguments.command in {"apply", "resume"}:
            if not arguments.execute or arguments.artifacts is None:
                parser.error("apply requires --execute and private --artifacts outside checkout")
            from tools.f8_release import apply, resume

            os.environ["PGPASSWORD"] = authorized_password()
            try:
                (apply if arguments.command == "apply" else resume)(arguments.artifacts)
            finally:
                os.environ.pop("PGPASSWORD", None)
        else:
            return run_pg_tests(arguments.test_slice)
        return 0
    except CommandError as error:
        print(error.code, file=sys.stderr)
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.SubprocessError):
        print("LOCAL_AUTHORIZATION_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
