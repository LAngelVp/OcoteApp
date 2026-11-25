import csv
import hashlib
import os
import socket
import struct
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from app.core.config import BACKEND_DIR, EnvironmentSettings
from app.core.errors import CommandError

MAX_BYTES = 10485760
TYPES = {"application/pdf": {".pdf"}, "image/png": {".png"}, "image/jpeg": {".jpg", ".jpeg"}}


class EvidenceSettings(EnvironmentSettings):
    evidence_storage_root: Path | None = None
    evidence_clamav_port: int | None = Field(default=None, ge=1, le=65535)
    evidence_scan_timeout: int = Field(default=5, ge=1, le=8)


def failure():
    return CommandError(503, "EVIDENCE_STORAGE_OR_SCANNER_UNAVAILABLE")


def private_root(root):
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or root.is_junction():
        raise failure()
    if root.resolve().is_relative_to(BACKEND_DIR.parent.resolve()):
        raise failure()
    if os.name == "nt":
        windows_private_acl(root)
    elif root.stat().st_mode & 0o077:
        raise failure()


def windows_private_acl(root):
    import ctypes
    from ctypes import wintypes

    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    current_sid = next(csv.reader([result.stdout.strip()]))[-1]
    allowed = {current_sid, "S-1-5-18", "S-1-5-32-544"}
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    security.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        pointer,
        pointer,
        ctypes.POINTER(pointer),
        pointer,
        ctypes.POINTER(pointer),
    ]
    security.GetNamedSecurityInfoW.restype = wintypes.DWORD
    security.GetAce.argtypes = [pointer, wintypes.DWORD, ctypes.POINTER(pointer)]
    security.GetAce.restype = wintypes.BOOL
    security.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(wintypes.LPWSTR)]
    security.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    acl, descriptor = pointer(), pointer()
    if security.GetNamedSecurityInfoW(
        str(root), 1, 4, None, None, ctypes.byref(acl), None, ctypes.byref(descriptor)
    ):
        raise failure()
    try:
        if not acl.value:
            raise failure()
        ace_count = ctypes.c_ushort.from_address(acl.value + 4).value
        for index in range(ace_count):
            entry = pointer()
            if not security.GetAce(acl, index, ctypes.byref(entry)):
                raise failure()
            kind = ctypes.c_ubyte.from_address(entry.value).value
            if kind == 1:
                continue
            if kind != 0:
                raise failure()
            sid = wintypes.LPWSTR()
            if not security.ConvertSidToStringSidW(pointer(entry.value + 8), ctypes.byref(sid)):
                raise failure()
            try:
                if sid.value not in allowed:
                    raise failure()
            finally:
                kernel.LocalFree(ctypes.cast(sid, pointer))
    finally:
        kernel.LocalFree(descriptor)


class ClamAV:
    def __init__(self, port, timeout=5):
        self.port, self.timeout = port, timeout

    def exchange(self, command, content=None):
        with socket.create_connection(("127.0.0.1", self.port), self.timeout) as connection:
            connection.settimeout(self.timeout)
            connection.sendall(command)
            if content is not None:
                for offset in range(0, len(content), 65536):
                    chunk = content[offset : offset + 65536]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.sendall(struct.pack("!I", 0))
            reply = bytearray()
            while not reply.endswith(b"\0"):
                chunk = connection.recv(1024)
                if not chunk or len(reply) + len(chunk) > 1024:
                    raise failure()
                reply.extend(chunk)
            return bytes(reply[:-1]).decode("ascii", errors="strict")

    def __call__(self, content):
        try:
            version = self.exchange(b"zVERSION\0")
            parts = version.split("/")
            if len(parts) != 3 or not parts[0].startswith("ClamAV ") or not parts[1].isdigit():
                raise failure()
            updated = datetime.strptime(parts[2], "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
            age = datetime.now(UTC) - updated
            if not -timedelta(minutes=5) <= age <= timedelta(days=1):
                raise failure()
            result = self.exchange(b"zINSTREAM\0", content)
            if result.endswith(" FOUND"):
                raise CommandError(422, "MALWARE_DETECTED")
            if result != "stream: OK":
                raise failure()
            return version[:200]
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            raise failure() from None


def validate_content(content, name, media_type, limit):
    if not content or len(content) > min(limit, MAX_BYTES):
        raise CommandError(413, "PAYLOAD_TOO_LARGE")
    if (
        not name
        or len(name) > 255
        or any(ord(character) < 32 for character in name)
        or any(character in name for character in "/\\:")
    ):
        raise CommandError(422, "INVALID_FILE_NAME")
    if media_type not in TYPES or Path(name).suffix.lower() not in TYPES[media_type]:
        raise CommandError(415, "INVALID_EVIDENCE_TYPE")
    valid = {
        "application/pdf": content.startswith(b"%PDF-") and content.rstrip().endswith(b"%%EOF"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n")
        and content.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"),
    }
    if not valid[media_type]:
        raise CommandError(415, "INVALID_EVIDENCE_TYPE")


class EvidenceStore:
    def __init__(self, root, scanner):
        self.root, self.scanner = Path(root), scanner

    def path(self, key):
        if len(key) != 32 or any(character not in "0123456789abcdef" for character in key):
            raise failure()
        candidate = self.root / "objects" / key
        if candidate.is_symlink():
            raise failure()
        return candidate

    def publish(self, content):
        try:
            private_root(self.root)
            for name in ("quarantine", "objects"):
                directory = self.root / name
                if not directory.is_dir() or directory.is_symlink():
                    raise failure()
                private_root(directory)
            key = uuid4().hex
            staging = self.root / "quarantine" / key
            try:
                with staging.open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                scan_version = self.scanner(content)
                if not isinstance(scan_version, str) or not scan_version.startswith("ClamAV "):
                    raise failure()
                destination = self.path(key)
                os.replace(staging, destination)
                return key, hashlib.sha256(content).hexdigest(), scan_version
            finally:
                staging.unlink(missing_ok=True)
        except (OSError, subprocess.SubprocessError):
            raise failure() from None

    def available(self, key, size, digest):
        try:
            private_root(self.root)
            private_root(self.root / "objects")
            path = self.path(key)
            if path.stat().st_size != size:
                raise failure()
            with path.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                    raise failure()
            return path
        except (OSError, subprocess.SubprocessError):
            raise failure() from None


def configured_store():
    settings = EvidenceSettings()
    if settings.evidence_storage_root is None or settings.evidence_clamav_port is None:
        raise failure()
    return EvidenceStore(
        settings.evidence_storage_root,
        ClamAV(settings.evidence_clamav_port, settings.evidence_scan_timeout),
    )
