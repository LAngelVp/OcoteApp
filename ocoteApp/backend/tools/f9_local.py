"""Explicit F9 local authorization and isolated PostgreSQL gates."""

import argparse
import ctypes
import getpass
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
from urllib.parse import quote, quote_plus
from uuid import UUID

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError
from app.core.vault import OSSealedFile
from tools.f1_local import private_directory

OPERATOR_CONTEXT = UUID("cc1eccaf-fc25-41ac-96ad-7d30c2c74309")
AUTHORIZATION_SECONDS = 3600
PURPOSE = "ocote-f9-local-postgres-only"


def authorization_path():
    directory = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not directory:
        raise CommandError(503, "LOCAL_AUTHORIZATION_PLATFORM_NOT_VERIFIED")
    return Path(directory) / "OCOTE" / "f9-operator" / "administrator.dpapi"


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
    payload = {
        "purpose": PURPOSE,
        "issued_at": issued,
        "expires_at": issued + AUTHORIZATION_SECONDS,
        "password": password,
    }
    OSSealedFile(path, OPERATOR_CONTEXT).create(json.dumps(payload).encode("utf-8"))


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
            or type(payload["issued_at"]) not in {int, float}
            or type(payload["expires_at"]) not in {int, float}
            or type(moment) not in {int, float}
            or not all(
                math.isfinite(value)
                for value in (
                    payload["issued_at"],
                    payload["expires_at"],
                    moment,
                )
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


def authorized_password(*, path=None, current_time=None):
    return authorization(path=path, current_time=current_time)["password"]


def authorize():
    print("OCOTE F9 - autorizacion PostgreSQL local", flush=True)
    print("Entrada sin eco, exclusivamente aqui; nunca en el chat.", flush=True)
    print("Contexto DPAPI F9 propio, caducidad60min, sin renovar ni reutilizar F8.", flush=True)
    if not sys.stdin.isatty():
        raise CommandError(503, "VISIBLE_INTERACTIVE_TERMINAL_REQUIRED")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Credencial administrativa PostgreSQL local: ")
    save_authorization(password)
    try:
        if authorized_password() != password:
            raise CommandError(503, "LOCAL_AUTHORIZATION_READBACK_FAILED")
    except BaseException:
        revoke()
        raise
    print(
        "Autorizacion sellada y verificada; PostgreSQL no fue conectado ni modificado.", flush=True
    )
    print("Relevo F9: " + str(authorization_path()), flush=True)


def revoke():
    from tools.f8_local import authorization_path as f8_path

    for path in (authorization_path(), f8_path()):
        path.unlink(missing_ok=True)
        if path.exists():
            raise CommandError(503, "LOCAL_AUTHORIZATION_REVOCATION_FAILED")
    print("Relevos F8/F9 eliminados; raices de instancia intactas.", flush=True)


def run_authorized(arguments, payload):
    password = payload["password"]
    remaining = payload["expires_at"] - time.time()
    if remaining <= 0:
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED")
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
    for output, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        for representation in {password, quote(password, safe=""), quote_plus(password)}:
            output = output.replace(representation, "[REDACTED]")
        stream.write(output)
    return result.returncode


def run_pg_tests(test_slice):
    try:
        payload = authorization()
        target = {"f9": "backend/tests/test_f9.py", "all": "backend/tests"}[test_slice]
        return run_authorized(["-m", "pytest", "-q", "--tb=short", target], payload)
    finally:
        revoke()


def api_listeners():
    if os.name != "nt":
        raise CommandError(503, "API_DRAIN_PLATFORM_NOT_VERIFIED")

    class IPv4Row(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint32)
            for name in ("state", "address", "port", "remote_address", "remote_port", "pid")
        ]

    class IPv6Row(ctypes.Structure):
        _fields_ = [
            ("address", ctypes.c_ubyte * 16),
            ("scope", ctypes.c_uint32),
            ("port", ctypes.c_uint32),
            ("remote_address", ctypes.c_ubyte * 16),
            ("remote_scope", ctypes.c_uint32),
            ("remote_port", ctypes.c_uint32),
            ("state", ctypes.c_uint32),
            ("pid", ctypes.c_uint32),
        ]

    query = ctypes.WinDLL("iphlpapi", use_last_error=True).GetExtendedTcpTable
    query.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    query.restype = ctypes.c_uint32
    listeners = []
    for family, row_type in ((socket.AF_INET, IPv4Row), (socket.AF_INET6, IPv6Row)):
        size = ctypes.c_uint32()
        if query(None, ctypes.byref(size), False, family, 5, 0) not in (0, 122):
            raise OSError("TCP table size unavailable")
        for _attempt in range(4):
            buffer = ctypes.create_string_buffer(size.value)
            status = query(buffer, ctypes.byref(size), False, family, 5, 0)
            if status != 122:
                break
        if status:
            raise OSError("TCP table unavailable")
        count = ctypes.c_uint32.from_buffer(buffer).value
        if 4 + count * ctypes.sizeof(row_type) > len(buffer):
            raise OSError("TCP table bounds invalid")
        for index in range(count):
            row = row_type.from_buffer_copy(buffer, 4 + index * ctypes.sizeof(row_type))
            if row.state != 2 or socket.ntohs(row.port & 65535) != 8000:
                continue
            address = (
                row.address.to_bytes(4, "little")
                if family == socket.AF_INET
                else bytes(row.address)
            )
            listeners.append((socket.inet_ntop(family, address), row.pid))
    return sorted(set(listeners))


def api_owner_matches(image, command, directory=""):
    root = BACKEND_DIR.parent.as_posix().lower().rstrip("/") + "/"
    image = image.replace("\\", "/").lower()
    command = command.replace("\\", "/").lower()
    directory = directory.replace("\\", "/").lower().rstrip("/")
    target = re.search(r"(?:^|\s)app\.main:(app|create_app)(?:\s|$)", command)
    return (
        Path(image).name in {"python.exe", "pythonw.exe", "uvicorn.exe"}
        and (root in image or root in command or directory == root.rstrip("/"))
        and bool(re.search(r"(?:^|\s)(?:-m\s+)?uvicorn(?:\s|$)", command))
        and target is not None
        and (target[1] != "create_app" or "--factory" in command.split())
    )


class APIProcess:
    def __init__(self, pid):
        if os.name != "nt" or pid <= 4 or pid == os.getpid():
            raise OSError("API process identity unsafe")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self.kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel.WaitForSingleObject.restype = ctypes.c_uint32
        self.kernel.ReadProcessMemory.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel.IsWow64Process.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.handle = self.kernel.OpenProcess(0x1000 | 0x100000 | 0x400 | 0x10 | 1, False, pid)
        if not self.handle:
            raise OSError("API process handle unavailable")

    def __enter__(self):
        return self

    def __exit__(self, *_error):
        self.kernel.CloseHandle(self.handle)

    def verified(self):
        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ushort),
                ("maximum", ctypes.c_ushort),
                ("buffer", ctypes.c_void_p),
            ]

        image = ctypes.create_unicode_buffer(32768)
        length = ctypes.c_uint32(len(image))
        if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(length)):
            return False
        query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        query.restype = ctypes.c_int32
        size = ctypes.c_uint32()
        query(self.handle, 60, None, 0, ctypes.byref(size))
        if not ctypes.sizeof(UnicodeString) <= size.value <= 131072:
            return False
        buffer = ctypes.create_string_buffer(size.value)
        if query(self.handle, 60, buffer, size.value, ctypes.byref(size)) < 0:
            return False
        value = UnicodeString.from_buffer(buffer)
        if (
            value.length % 2
            or not value.buffer
            or value.buffer < ctypes.addressof(buffer)
            or value.buffer + value.length > ctypes.addressof(buffer) + len(buffer)
        ):
            return False
        command = ctypes.wstring_at(value.buffer, value.length // 2)
        return api_owner_matches(image.value, command, self.current_directory(query, UnicodeString))

    def current_directory(self, query, string_type):
        wow64 = ctypes.c_int()
        if not self.kernel.IsWow64Process(self.handle, ctypes.byref(wow64)) or wow64.value:
            raise OSError("API process architecture not verified")
        basic = (ctypes.c_void_p * 6)()
        returned = ctypes.c_uint32()
        if query(self.handle, 0, basic, ctypes.sizeof(basic), ctypes.byref(returned)) < 0:
            raise OSError("API process parameters unavailable")

        def read(address, destination):
            copied = ctypes.c_size_t()
            if not self.kernel.ReadProcessMemory(
                self.handle,
                address,
                ctypes.byref(destination),
                ctypes.sizeof(destination),
                ctypes.byref(copied),
            ) or copied.value != ctypes.sizeof(destination):
                raise OSError("API process parameters unreadable")

        pointer_size = ctypes.sizeof(ctypes.c_void_p)
        parameters = ctypes.c_void_p()
        read(basic[1] + (0x20 if pointer_size == 8 else 0x10), parameters)
        directory = string_type()
        read(parameters.value + (0x38 if pointer_size == 8 else 0x24), directory)
        if not directory.buffer or not 0 < directory.length <= 65534 or directory.length % 2:
            raise OSError("API process directory invalid")
        buffer = ctypes.create_unicode_buffer(directory.length // 2)
        read(directory.buffer, buffer)
        return buffer[:]

    def stop(self):
        if not self.kernel.TerminateProcess(self.handle, 0):
            raise OSError("API termination failed")
        if self.kernel.WaitForSingleObject(self.handle, 30000) != 0:
            raise OSError("API exit not verified")


def drain_api():
    try:
        listeners = api_listeners()
        if not listeners:
            print("F9_API_ALREADY_DRAINED", flush=True)
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
    print("F9_API_DRAINED", flush=True)


def run_final_gates(artifacts):
    try:
        if artifacts is None:
            raise CommandError(422, "PRIVATE_RELEASE_ARTIFACTS_REQUIRED")
        root = Path(artifacts)
        if (
            not root.is_absolute()
            or root.is_symlink()
            or root.is_junction()
            or root.resolve().is_relative_to(BACKEND_DIR.parent.resolve())
        ):
            raise CommandError(422, "PRIVATE_RELEASE_ARTIFACTS_REQUIRED")
        payload = authorization()
        tests = "backend/tests/test_f9.py::"
        stages = [
            [
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                tests + "test_f9_postgres_upgrade_from0007_noop_empty_and_preserves",
                tests + "test_f9_postgres_triggers_constraints_and_privileges",
            ],
            ["-m", "pytest", "-q", "--tb=short", "backend/tests"],
        ]
        for stage in stages:
            status = run_authorized(stage, payload)
            if status:
                return status
        if payload["expires_at"] - time.time() < 600:
            raise CommandError(503, "AUTHORIZATION_EXPIRING_NO_RELEASE_STARTED")
        print("F9_PG1_GREEN_BEGIN_CONTROLLED_RELEASE", flush=True)
        drain_api()
        return run_authorized(["-m", "tools.f9_release", "--artifacts", str(artifacts)], payload)
    finally:
        revoke()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "revoke", "pg-tests", "final-gates"))
    parser.add_argument("--test-slice", choices=("f9", "all"), default="f9")
    parser.add_argument("--artifacts", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "authorize":
            authorize()
        elif arguments.command == "revoke":
            revoke()
        elif arguments.command == "final-gates":
            return run_final_gates(arguments.artifacts)
        else:
            return run_pg_tests(arguments.test_slice)
        return 0
    except CommandError as error:
        print(error.code, file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("LOCAL_AUTHORIZATION_EXPIRED_TESTS_ABORTED_REVIEW_UUID_CLEANUP", file=sys.stderr)
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.SubprocessError):
        print("LOCAL_AUTHORIZATION_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
