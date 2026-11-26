import ctypes
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import CommandError
from app.core.evidence import private_root

ALGORITHM = "AES-256-GCM"
PURPOSES = frozenset({"jwt_signing", "csrf", "health_monitor", "local_storage", "clamav", "backup",
                      "object_storage", "notifications", "calendar_feed"})


def unavailable():
    return CommandError(503, "VAULT_UNAVAILABLE")


def associated_data(**values):
    return json.dumps(values, sort_keys=True, separators=(",", ":")).encode("ascii")


@dataclass(frozen=True)
class WrappedKey:
    id: UUID
    instance_id: UUID
    purpose: str
    epoch: int
    root_key_ref: str
    nonce: bytes = field(repr=False)
    wrapped_dek: bytes = field(repr=False)


@dataclass(frozen=True)
class EncryptedValue:
    key_id: UUID
    owner_id: UUID
    version: int
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


class Vault:
    def __init__(self, root_key: bytes, instance_id: UUID, root_key_ref: str):
        if len(root_key) != 32 or not root_key_ref or len(root_key_ref) > 200:
            raise unavailable()
        self._root = AESGCM(root_key)
        self.instance_id = instance_id
        self.root_key_ref = root_key_ref

    def _key_context(self, key):
        if (
            key.instance_id != self.instance_id
            or key.root_key_ref != self.root_key_ref
            or key.purpose not in PURPOSES
            or key.epoch < 1
        ):
            raise unavailable()
        return associated_data(
            algorithm=ALGORITHM,
            instance=str(self.instance_id),
            key=str(key.id),
            purpose=key.purpose,
            epoch=key.epoch,
            root=key.root_key_ref,
            format=1,
        )

    def new_key(self, purpose: str, epoch: int) -> WrappedKey:
        if purpose not in PURPOSES or type(epoch) is not int or epoch < 1:
            raise unavailable()
        metadata = WrappedKey(
            uuid4(), self.instance_id, purpose, epoch, self.root_key_ref, os.urandom(12), b""
        )
        wrapped = self._root.encrypt(
            metadata.nonce, AESGCM.generate_key(bit_length=256), self._key_context(metadata)
        )
        return WrappedKey(
            metadata.id,
            metadata.instance_id,
            purpose,
            epoch,
            metadata.root_key_ref,
            metadata.nonce,
            wrapped,
        )

    def _cipher(self, key):
        try:
            return AESGCM(self._root.decrypt(key.nonce, key.wrapped_dek, self._key_context(key)))
        except (InvalidTag, ValueError, TypeError):
            raise unavailable() from None

    def _value_context(self, key, owner_id, version):
        if type(version) is not int or version < 1 or not isinstance(owner_id, UUID):
            raise unavailable()
        return associated_data(
            algorithm=ALGORITHM,
            instance=str(self.instance_id),
            key=str(key.id),
            purpose=key.purpose,
            owner=str(owner_id),
            version=version,
            format=1,
        )

    def encrypt(
        self, key: WrappedKey, owner_id: UUID, version: int, plaintext: bytes
    ) -> EncryptedValue:
        if not isinstance(plaintext, bytes) or not 1 <= len(plaintext) <= 65536:
            raise unavailable()
        nonce = os.urandom(12)
        ciphertext = self._cipher(key).encrypt(
            nonce, plaintext, self._value_context(key, owner_id, version)
        )
        return EncryptedValue(key.id, owner_id, version, nonce, ciphertext)

    def decrypt(self, key: WrappedKey, value: EncryptedValue) -> bytes:
        if value.key_id != key.id:
            raise unavailable()
        try:
            return self._cipher(key).decrypt(
                value.nonce,
                value.ciphertext,
                self._value_context(key, value.owner_id, value.version),
            )
        except (InvalidTag, ValueError, TypeError):
            raise unavailable() from None


def os_protect(content: bytes, instance_id: UUID, *, decrypt=False) -> bytes:
    if os.name != "nt":
        raise CommandError(503, "OS_SEAL_PLATFORM_NOT_VERIFIED")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = (ctypes.c_ubyte * len(content)).from_buffer_copy(content)
    entropy_buffer = (ctypes.c_ubyte * 16).from_buffer_copy(instance_id.bytes)
    source = Blob(len(content), source_buffer)
    entropy = Blob(16, entropy_buffer)
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    operation.restype = wintypes.BOOL
    if not operation(
        ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(output)
    ):
        raise unavailable()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


class OSSealedFile:
    def __init__(self, path: Path, instance_id: UUID):
        self.path, self.instance_id = Path(path), instance_id

    def create(self, content: bytes):
        if not 1 <= len(content) <= 131072:
            raise unavailable()
        private_root(self.path.parent)
        protected = os_protect(content, self.instance_id)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise CommandError(409, "OS_SEAL_ALREADY_EXISTS") from None
        except OSError:
            raise unavailable() from None
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(protected)
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            raise unavailable() from None

    def read(self) -> bytes:
        try:
            private_root(self.path.parent)
            if self.path.is_symlink() or self.path.is_junction() or not self.path.is_file():
                raise unavailable()
            if self.path.stat().st_size > 262144:
                raise unavailable()
            content = os_protect(self.path.read_bytes(), self.instance_id, decrypt=True)
            if not 1 <= len(content) <= 131072:
                raise unavailable()
            return content
        except OSError:
            raise unavailable() from None
