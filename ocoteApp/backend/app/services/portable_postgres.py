import ctypes
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

from app.core.config import BACKEND_DIR, DATABASE_NAME
from app.core.errors import CommandError
from app.core.evidence import private_root

EXECUTABLES = (
    "initdb.exe",
    "pg_ctl.exe",
    "postgres.exe",
    "psql.exe",
    "pg_dump.exe",
    "pg_restore.exe",
)
OPTIONS = (
    "-h 127.0.0.1 -p {port} -c log_statement=none -c log_min_error_statement=panic "
    "-c log_parameter_max_length=0 -c log_parameter_max_length_on_error=0"
)


def failure(code="SETUP_LOCAL_PREPARATION_FAILED", status=503):
    return CommandError(status, code)


def state_data_directory(state, selected):
    state = Path(os.path.abspath(state))
    selected = Path(selected)
    candidate = Path(os.path.abspath(selected if selected.is_absolute() else state / selected))
    if candidate == state or not candidate.is_relative_to(state):
        raise failure("SETUP_LOCAL_DATA_PATH_REJECTED", 409)
    for path in (candidate, *candidate.parents):
        if path.is_symlink() or path.is_junction():
            raise failure("SETUP_LOCAL_DATA_PATH_REJECTED", 409)
        if path == state:
            break
    if candidate.resolve().is_relative_to(BACKEND_DIR.parent.resolve()):
        raise failure("SETUP_LOCAL_DATA_PATH_REJECTED", 409)
    return candidate


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            if os.name == "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", port))
        except OSError:
            raise failure("SETUP_LOCAL_PORT_IN_USE", 409) from None


def validate_binaries(root):
    root = Path(root).absolute()
    if root.is_symlink() or root.is_junction():
        raise failure("SETUP_PORTABLE_UNAVAILABLE")
    for name in EXECUTABLES:
        path = root / "bin" / name
        if not path.is_file() or path.is_symlink() or path.is_junction():
            raise failure("SETUP_PORTABLE_UNAVAILABLE")
    if not all((root / folder).is_dir() for folder in ("lib", "share")):
        raise failure("SETUP_PORTABLE_UNAVAILABLE")
    return root


def native_command(binary, arguments, state, *, label, check=True):
    from app.services.installation import write_private

    environment = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
    result_log = state / (label + "-" + uuid4().hex + ".log")
    write_private(result_log, b"")
    try:
        with result_log.open("wb") as output:
            result = subprocess.run(
                [str(binary), *map(str, arguments)],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                timeout=120,
                cwd=state,
            )
        if check and result.returncode:
            raise failure()
        return result.returncode
    except (OSError, subprocess.SubprocessError):
        raise failure() from None


def process_matches(pid, executable, data):
    if os.name != "nt" or pid <= 4:
        return False
    from ctypes import wintypes

    class String(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.USHORT),
            ("maximum", wintypes.USHORT),
            ("buffer", ctypes.c_void_p),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    handle = kernel.OpenProcess(0x1000 | 0x400 | 0x10, False, pid)
    if not handle:
        return False
    try:
        image = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(image))
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            return False
        if Path(image.value).resolve() != Path(executable).resolve():
            return False
        query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
        query.argtypes = [
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
        ]
        query.restype = ctypes.c_long
        size = wintypes.ULONG()
        query(handle, 60, None, 0, ctypes.byref(size))
        if not ctypes.sizeof(String) <= size.value <= 131072:
            return False
        buffer = ctypes.create_string_buffer(size.value)
        if query(handle, 60, buffer, size.value, ctypes.byref(size)) < 0:
            return False
        value = String.from_buffer(buffer)
        if not value.buffer or not (
            ctypes.addressof(buffer) <= value.buffer
            and value.buffer + value.length <= ctypes.addressof(buffer) + len(buffer)
        ):
            return False
        command = ctypes.wstring_at(value.buffer, value.length // 2)
        shell = ctypes.WinDLL("shell32")
        shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        count = ctypes.c_int()
        pointers = shell.CommandLineToArgvW(command, ctypes.byref(count))
        if not pointers:
            return False
        try:
            arguments = [pointers[index] for index in range(count.value)]
        finally:
            kernel.LocalFree(ctypes.cast(pointers, ctypes.c_void_p))
        return any(
            value.casefold() == "-d"
            and index + 1 < len(arguments)
            and Path(arguments[index + 1]).resolve() == Path(data).resolve()
            for index, value in enumerate(arguments)
        )
    finally:
        kernel.CloseHandle(handle)


class PortablePostgres:
    def __init__(self, state, binaries, configuration):
        self.state = Path(state).absolute()
        self.binaries = Path(binaries).absolute()
        self.configuration = configuration
        self.data = state_data_directory(self.state, configuration.data_directory)
        self.created = False
        self.started = False

    def validate(self):
        private_root(self.state)
        if any(
            (self.state / name).exists()
            for name in (
                "sealed.json",
                "installing.json",
                "portable-postgres.json",
                "local-failure.json",
            )
        ):
            raise failure("SETUP_LOCAL_EXISTING_STATE", 409)
        validate_binaries(self.binaries)
        if self.data.exists() and (not self.data.is_dir() or any(self.data.iterdir())):
            raise failure("SETUP_LOCAL_DATA_NOT_EMPTY", 409)
        port_available(self.configuration.port)
        return {
            "database": DATABASE_NAME,
            "port": self.configuration.port,
            "data_directory": self.configuration.data_directory,
            "portable_verified": True,
        }

    def prepare(self):
        from app.services.installation import canonical, private_directory, write_private

        self.validate()
        verify_version(self.binaries)
        private_directory(self.data)
        self.created = True
        password_file = self.state / ("local-password-" + uuid4().hex)
        try:
            write_private(
                password_file,
                self.configuration.postgres_password.get_secret_value().encode("utf-8") + b"\n",
            )
            native_command(
                self.binaries / "bin/initdb.exe",
                [
                    "-D",
                    self.data,
                    "-U",
                    "postgres",
                    "--encoding=UTF8",
                    "--auth=scram-sha-256",
                    "--no-locale",
                    "--pwfile=" + str(password_file),
                ],
                self.state,
                label="initdb",
            )
        finally:
            password_file.unlink(missing_ok=True)
        port_available(self.configuration.port)
        self.started = True
        native_command(
            self.binaries / "bin/pg_ctl.exe",
            [
                "-D",
                self.data,
                "-l",
                self.state / "postgres-server.log",
                "-o",
                OPTIONS.format(port=self.configuration.port),
                "-w",
                "-t",
                "60",
                "start",
            ],
            self.state,
            label="pg-start",
        )
        with psycopg.connect(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=self.configuration.port,
            dbname="postgres",
            user="postgres",
            password=self.configuration.postgres_password.get_secret_value(),
            sslmode="disable",
            connect_timeout=3,
            autocommit=True,
            options="-c statement_timeout=15000 -c lock_timeout=3000",
            application_name="ocote-first-run-portable",
        ) as admin:
            identity = admin.execute(
                "SELECT current_user,current_setting('data_directory'),"
                "current_setting('server_version_num')"
            ).fetchone()
            if (
                identity[0] != "postgres"
                or Path(identity[1]).resolve() != self.data.resolve()
                or not (180000 <= int(identity[2]) < 190000)
            ):
                raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
            for role, password in (
                ("ocote_migrador", self.configuration.migrator_password),
                ("ocote_runtime", self.configuration.runtime_password),
            ):
                verifier = admin.pgconn.encrypt_password(
                    password.get_secret_value().encode("utf-8"),
                    role.encode("ascii"),
                    b"scram-sha-256",
                )
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(role), sql.Literal(verifier.decode("ascii")))
                )
            admin.execute(
                sql.SQL(
                    "CREATE DATABASE {} OWNER ocote_migrador ENCODING 'UTF8' TEMPLATE template0"
                ).format(sql.Identifier(DATABASE_NAME))
            )
        with psycopg.connect(
            host="127.0.0.1",
            hostaddr="127.0.0.1",
            port=self.configuration.port,
            dbname=DATABASE_NAME,
            user="postgres",
            password=self.configuration.postgres_password.get_secret_value(),
            sslmode="disable",
            connect_timeout=3,
            autocommit=True,
            options="-c statement_timeout=15000 -c lock_timeout=3000",
            application_name="ocote-first-run-portable",
        ) as admin:
            admin.execute("ALTER SCHEMA public OWNER TO ocote_migrador")
            admin.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            admin.execute("GRANT USAGE ON SCHEMA public TO ocote_runtime")
            admin.execute("CREATE EXTENSION btree_gist")
        metadata = {
            "kind": "local-portable-v1",
            "data_directory": str(self.data),
            "port": self.configuration.port,
            "host": "127.0.0.1",
            "major": 18,
        }
        write_private(self.state / "portable-postgres.json", canonical(metadata))
        return metadata

    def stop_failed_attempt(self):
        if not self.created or not self.started:
            return
        pid_file = self.data / "postmaster.pid"
        if not pid_file.is_file():
            return
        lines = pid_file.read_text().splitlines()
        if (
            len(lines) < 4
            or Path(lines[1]).resolve() != self.data.resolve()
            or int(lines[3]) != self.configuration.port
            or not process_matches(int(lines[0]), self.binaries / "bin/postgres.exe", self.data)
        ):
            raise failure("SETUP_LOCAL_STOP_IDENTITY_REJECTED", 409)
        native_command(
            self.binaries / "bin/pg_ctl.exe",
            ["-D", self.data, "-m", "fast", "-w", "-t", "30", "stop"],
            self.state,
            label="pg-stop",
        )


def verify_version(binaries):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
    try:
        version = subprocess.run(
            [str(Path(binaries) / "bin/postgres.exe"), "--version"],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            text=True,
        )
        if version.returncode or not re.search(r"PostgreSQL\)?\s+18\.", version.stdout):
            raise failure("SETUP_PORTABLE_VERSION_REJECTED", 409)
    except (OSError, subprocess.SubprocessError):
        raise failure("SETUP_PORTABLE_VERSION_REJECTED", 409) from None


def ensure_started(state, metadata, binaries):
    from app.services.installation import write_private

    state = Path(state).absolute()
    private_root(state)
    root = validate_binaries(binaries)
    if (
        metadata.get("kind") != "local-portable-v1"
        or metadata.get("host") != "127.0.0.1"
        or metadata.get("major") != 18
        or not 1 <= int(metadata.get("port", 0)) <= 65535
    ):
        raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
    data = state_data_directory(state, metadata["data_directory"])
    if not (data / "PG_VERSION").is_file() or (data / "PG_VERSION").read_text().strip() != "18":
        raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
    stored = state / "portable-postgres.json"
    if not stored.is_file() or json.loads(stored.read_text()) != metadata:
        raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
    lock = state / "postgres-start.lock"
    try:
        write_private(lock, b"owned-portable-start")
    except FileExistsError:
        raise failure("SETUP_LOCAL_START_BUSY", 409) from None
    try:
        verify_version(root)
        status = native_command(
            root / "bin/pg_ctl.exe", ["-D", data, "status"], state, label="pg-status", check=False
        )
        if status == 0:
            lines = (data / "postmaster.pid").read_text().splitlines()
            if (
                len(lines) < 4
                or Path(lines[1]).resolve() != data.resolve()
                or int(lines[3]) != metadata["port"]
                or not process_matches(int(lines[0]), root / "bin/postgres.exe", data)
            ):
                raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
            return {"started": False, "already_running": True}
        if status != 3 or (data / "postmaster.pid").exists():
            raise failure("SETUP_LOCAL_RECOVERY_REQUIRED", 409)
        port_available(metadata["port"])
        native_command(
            root / "bin/pg_ctl.exe",
            [
                "-D",
                data,
                "-l",
                state / "postgres-server.log",
                "-o",
                OPTIONS.format(port=metadata["port"]),
                "-w",
                "-t",
                "60",
                "start",
            ],
            state,
            label="pg-runtime-start",
        )
        lines = (data / "postmaster.pid").read_text().splitlines()
        if (
            len(lines) < 4
            or Path(lines[1]).resolve() != data.resolve()
            or int(lines[3]) != metadata["port"]
            or not process_matches(int(lines[0]), root / "bin/postgres.exe", data)
        ):
            raise failure("SETUP_LOCAL_IDENTITY_REJECTED", 409)
        return {"started": True, "already_running": False}
    finally:
        lock.unlink(missing_ok=True)
