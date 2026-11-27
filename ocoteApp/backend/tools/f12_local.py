"""F12 local-only operator capture and ordered gates; capture is always explicit."""

import argparse
import csv
import ctypes
import getpass
import hashlib
import io
import json
import math
import os
import re
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path
from uuid import UUID, uuid4

from packaging.requirements import Requirement

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from tools import f11_local as previous
from tools.f1_local import canonical, private_directory, write_private
from tools.f10_local import run_authorized

OPERATOR_CONTEXT = UUID("e3ee3faa-9ef6-4d51-8188-bf0537ff1201")
AUTHORIZATION_SECONDS = 3600
PURPOSE = "ocote-f12-local-postgres-only"


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE/f12-operator/administrator.dpapi"


def authorization_paths():
    return (authorization_path(), *previous.authorization_paths())


def save_authorization(password, *, path=None, issued_at=None):
    destination = path or authorization_path()
    if not isinstance(password, str) or not 1 <= len(password) <= 1024 or any(
        char in password for char in "\r\n\x00"
    ):
        raise CommandError(422, "INVALID_LOCAL_AUTHORIZATION")
    if destination.exists():
        raise CommandError(503, "FRESH_F12_CAPTURE_REQUIRED_NO_RENEWAL")
    if any(item.is_symlink() or item.is_junction() for item in (destination, *destination.parents)):
        raise CommandError(503, "LOCAL_AUTHORIZATION_PATH_UNSAFE")
    issued = time.time() if issued_at is None else issued_at
    payload = {"purpose": PURPOSE, "issued_at": issued,
               "expires_at": issued + AUTHORIZATION_SECONDS, "password": password}
    private_directory(destination.parent)
    OSSealedFile(destination, OPERATOR_CONTEXT).create(canonical(payload))


def authorization(*, path=None, current_time=None):
    try:
        destination = path or authorization_path()
        if any(item.is_symlink() or item.is_junction()
               for item in (destination, *destination.parents)):
            raise ValueError
        payload = json.loads(OSSealedFile(destination, OPERATOR_CONTEXT).read())
        moment = time.time() if current_time is None else current_time
        issued, expires = payload["issued_at"], payload["expires_at"]
        if any(type(value) not in {int, float} or not math.isfinite(value)
               for value in (issued, expires, moment)) or (
            payload["purpose"] != PURPOSE or expires - issued != AUTHORIZATION_SECONDS
            or not issued <= moment < expires or not isinstance(payload["password"], str)
            or not payload["password"] or any(char in payload["password"] for char in "\r\n\x00")
        ):
            raise ValueError
        return payload
    except (OSError, ValueError, TypeError, KeyError, CommandError):
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED") from None


def preflight(*, captured=False):
    if os.environ.get("PGPASSWORD"):
        raise CommandError(503, "ADMINISTRATIVE_ENVIRONMENT_MUST_BE_EMPTY")
    paths = authorization_paths()
    if paths[0].exists() != captured or any(path.exists() for path in paths[1:]):
        raise CommandError(503, "FRESH_F12_CAPTURE_REQUIRED_NO_RENEWAL")
    previous.preflight(captured=False)
    return {"phase": "F12", "captured": captured, "api": previous.api_listeners()}


def authorize():
    if os.environ.get("PGPASSWORD") or not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_FRESH_INTERACTIVE_CAPTURE_REQUIRED")
    preflight()
    print("OCOTE F12 - entrada administrativa local sin eco; nunca por chat.", flush=True)
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
    print("F12 sellada/verificada, TTL60min; sin conexion PostgreSQL.", flush=True)


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
    print("Relevos F8-F12 revocados y ausentes; raices de instancia intactas.", flush=True)


def run_final_gates(artifacts):
    summary = {"phase": "F12", "stages": [], "release_started": False}
    root = None
    try:
        if os.environ.get("PGPASSWORD") or artifacts is None:
            raise CommandError(422, "PRIVATE_ARTIFACTS_AND_FRESH_SEALED_AUTHORIZATION_REQUIRED")
        candidate = Path(artifacts)
        if not candidate.is_absolute() or candidate.exists() or any(
            path.is_symlink() or path.is_junction() for path in (candidate, *candidate.parents)
        ) or candidate.resolve().is_relative_to(BACKEND_DIR.parent.resolve()):
            raise CommandError(422, "PRIVATE_NEW_RELEASE_ARTIFACTS_REQUIRED")
        payload = authorization()
        preflight(captured=True)
        root = candidate.resolve()
        private_directory(root)
        stages = [
            ("migration-protections", ["-m", "pytest", "-q", "--tb=short",
                                       "backend/tests/test_f12_postgres.py"]),
            ("pg1", ["-m", "pytest", "-q", "--tb=short", "backend/tests"]),
        ]
        for name, arguments in stages:
            started = time.monotonic()
            status = run_authorized(arguments, payload, root / (name + ".txt"))
            summary["stages"].append({"name": name, "status": status,
                                       "seconds": round(time.monotonic() - started, 3)})
            if status:
                return status
        if authorization()["expires_at"] - time.time() < 900:
            raise CommandError(503, "AUTHORIZATION_EXPIRING_NO_RELEASE_STARTED")
        previous.drain_api()
        summary["release_started"] = True
        status = run_authorized(["-m", "tools.f12_release", "--artifacts", str(root)],
                                payload, root / "release.txt")
        summary["stages"].append({"name": "release", "status": status})
        return status
    finally:
        try:
            revoke()
        finally:
            if root is not None:
                write_private(root / "stage-summary.json", canonical(summary))


def check_cut1():
    root = BACKEND_DIR.parent
    previous_lock = subprocess.run(
        ["git", "show", "HEAD:./backend/requirements.lock"], cwd=root,
        capture_output=True, check=True, text=True,
    ).stdout
    current_lock = (BACKEND_DIR / "requirements.lock").read_text()

    def pins(content):
        values = {}
        for line in content.splitlines():
            if line and line[0].isalpha() and "==" in line:
                requirement = Requirement(line.rstrip(" \\"))
                values[requirement.name.lower().replace("_", "-")] = str(requirement.specifier)
        return values

    before, after = pins(previous_lock), pins(current_lock)
    if any(after.get(name) != value for name, value in before.items()) or not set(
        re.findall(r"--hash=sha256:([a-f0-9]{64})", previous_lock)
    ) <= set(re.findall(r"--hash=sha256:([a-f0-9]{64})", current_lock)):
        raise CommandError(409, "F12_PREVIOUS_DEPENDENCY_PINS_OR_HASHES_CHANGED")
    allowed = {"openpyxl", "reportlab", "defusedxml", "et-xmlfile", "charset-normalizer"}
    if set(after) - set(before) != allowed:
        raise CommandError(409, "F12_UNAPPROVED_DEPENDENCY_ADDITIONS")
    protected = ["scripts", "public/logos", "package-lock.json"]
    protected += [path.relative_to(root).as_posix() for path in
                  (BACKEND_DIR / "alembic/versions").glob("*.py")
                  if path.name.startswith(tuple("202611" + day for day in ("24", "25", "26")))
                  and "_0011_" not in path.name]
    protected += [path.relative_to(root).as_posix() for path in (BACKEND_DIR / "tools").glob("*")
                  if path.is_file() and re.match(r"f(?:[1-9]|10|11)_", path.name)]
    result = subprocess.run(["git", "diff", "--exit-code", "--quiet", "HEAD", "--", *protected],
                            cwd=root, capture_output=True)
    if result.returncode:
        raise CommandError(409, "F12_PROTECTED_TRACKED_FILES_CHANGED")
    status = preflight()
    if (BACKEND_DIR / ".local/maintenance.json").exists():
        raise CommandError(409, "F12_UNEXPECTED_MAINTENANCE")
    with socket.socket() as connection:
        connection.settimeout(2)
        closed = connection.connect_ex(("127.0.0.1", 8445)) != 0
    if not closed:
        raise CommandError(409, "F12_VISUAL_PORT_STILL_OPEN")
    report = {"phase": "F12_CUT1", "previous_pins_preserved": len(before),
              "previous_hashes_preserved": True,
              "added_dependencies": {name: after[name] for name in sorted(allowed)},
              "protected_files_unchanged": True, "maintenance_present": False,
              "seals_present": False, "port_8445_closed": closed,
              "api": status["api"], "angular_build_processes": angular_build_processes(),
              "postgres_connections_opened": 0}
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def angular_build_processes():
    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("maximum", ctypes.c_ushort),
                    ("buffer", ctypes.c_void_p)]

    result = subprocess.run(
        [str(Path(os.environ["SystemRoot"]) / "System32/tasklist.exe"), "/FI",
         "IMAGENAME eq node.exe", "/FO", "CSV", "/NH"], capture_output=True, check=True,
    )
    query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
    query.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                      ctypes.POINTER(ctypes.c_uint32)]
    query.restype = ctypes.c_int32
    found = []
    for row in csv.reader(io.StringIO(result.stdout.decode("utf-8", errors="replace"))):
        if len(row) < 2 or row[0].lower() != "node.exe" or not row[1].isdigit():
            continue
        try:
            with previous.APIProcess(int(row[1])) as process:
                size = ctypes.c_uint32()
                query(process.handle, 60, None, 0, ctypes.byref(size))
                if not ctypes.sizeof(UnicodeString) <= size.value <= 131072:
                    continue
                buffer = ctypes.create_string_buffer(size.value)
                if query(process.handle, 60, buffer, size.value, ctypes.byref(size)) < 0:
                    continue
                value = UnicodeString.from_buffer(buffer)
                if not value.buffer or value.length % 2 or not (
                    ctypes.addressof(buffer) <= value.buffer and
                    value.buffer + value.length <= ctypes.addressof(buffer) + len(buffer)
                ):
                    continue
                command = ctypes.wstring_at(value.buffer, value.length // 2).replace("\\", "/")
                if not re.search(r"[/]ng\.js[\"']?\s+build(?:\s|$)", command):
                    continue
                directory = process.current_directory(query, UnicodeString)
                if Path(directory).resolve() == BACKEND_DIR.parent.resolve():
                    found.append({"pid": int(row[1]), "command": "Angular CLI build",
                                  "checkout_verified": True})
        except OSError:
            continue
    return found


def record_cut1(visual_artifacts):
    from tools import f11_release as shared

    source = Path(visual_artifacts).resolve()
    if source.is_relative_to(BACKEND_DIR.parent.resolve()) or any(
        path.is_symlink() or path.is_junction() for path in (source, *source.parents)
    ):
        raise CommandError(422, "PRIVATE_VISUAL_ARTIFACTS_REQUIRED")
    visual = json.loads((source / "results.json").read_bytes())
    results = visual["results"]
    if not visual["synthetic"] or visual["errors"] or len(results) != 34 or {
        result["width"] for result in results
    } != {1280, 360} or any(result["contrast"]["failures"] for result in results) or (
        not all(request["intercepted"] for request in visual["requests"])
    ):
        raise CommandError(409, "F12_VISUAL_GATE_NOT_VERIFIED")
    status = check_cut1()
    if status["angular_build_processes"]:
        raise CommandError(409, "F12_BUILD_PROCESSES_STILL_RUNNING")
    root = Path(os.environ["LOCALAPPDATA"]) / "OCOTE/f12-cut1" / str(uuid4())
    private_directory(root)
    private_directory(root / "visual")
    for result in results:
        name = result["name"]
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise CommandError(422, "INVALID_VISUAL_EVIDENCE_NAME")
        write_private(root / "visual" / (name + ".png"), (source / (name + ".png")).read_bytes())
    write_private(root / "visual/results.json", (source / "results.json").read_bytes())
    files = shared.artifact_files()
    for name in ("backend/pyproject.toml", "backend/requirements.lock", "package-lock.json",
                 ".vscode/tasks.json", "angular.json"):
        files[name] = shared.local.digest(BACKEND_DIR.parent / name)
    fingerprint = hashlib.sha256(canonical(files)).hexdigest()
    samples = sum(result["contrast"]["tested"] for result in results)
    report = {"phase": "F12_CUT1", "recorded_at": shared.local.now(), "offline": status,
              "artifact_fingerprint": fingerprint, "files": files,
              "visual": {"synthetic": True, "screenshots": len(results),
                         "requests": len(visual["requests"]),
                         "contrast_samples": samples,
                         "results_sha256": shared.local.digest(root / "visual/results.json")},
              "source_known_revision": "20261126_0010", "target_revision": "20261126_0011",
              "migration_applied": False, "pg1_executed": False,
              "administrative_capture_launched": False}
    write_private(root / "cut1-manifest.json", canonical(report))
    print(json.dumps({"evidence_directory": str(root), "artifact_fingerprint": fingerprint,
                      "manifest_sha256": shared.local.digest(root / "cut1-manifest.json"),
                      "visual": report["visual"]}, sort_keys=True), flush=True)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "revoke", "preflight", "check-cut1",
                                            "record-cut1", "final-gates"))
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--visual-artifacts", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            revoke()
        elif arguments.command == "preflight":
            preflight()
        elif arguments.command == "check-cut1":
            check_cut1()
        elif arguments.command == "record-cut1":
            if arguments.visual_artifacts is None:
                raise CommandError(422, "PRIVATE_VISUAL_ARTIFACTS_REQUIRED")
            record_cut1(arguments.visual_artifacts)
        else:
            return run_final_gates(arguments.artifacts)
        return 0
    except Exception as error:
        print("F12_FAILED_" + (error.code if isinstance(error, CommandError)
                              else type(error).__name__))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())