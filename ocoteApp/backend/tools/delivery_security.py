import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.core.evidence import private_root
from app.services.installation import canonical, private_directory, write_private


def repository():
    root = Path(__file__).resolve().parents[2]
    return next((path for path in (root, *root.parents) if (path / ".git").exists()), root)


def private_location(path):
    path = Path(path).absolute()
    if path.resolve().is_relative_to(repository().resolve()) or path.is_symlink():
        raise ValueError("Signing secrets must remain outside the repository")
    return path


def keygen(directory):
    directory = private_location(directory)
    if directory.exists():
        raise ValueError("Key generation requires a new private directory")
    private_directory(directory)
    key = Ed25519PrivateKey.generate()
    write_private(
        directory / "signing-private.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    write_private(
        directory / "signing-public.pem",
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    return directory / "signing-private.pem", directory / "signing-public.pem"


def public_fingerprint(key):
    return hashlib.sha256(
        key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).hexdigest()


def signature_payload(artifact, key):
    from tools.delivery import sha, verify

    manifest = verify(artifact)
    return {
        "format": "ocote-ed25519-v1",
        "algorithm": "Ed25519",
        "key_id": public_fingerprint(key),
        "zip_sha256": sha(Path(artifact).read_bytes()),
        "manifest_sha256": sha(canonical(manifest)),
    }


def sign(artifact, private_key, destination):
    private_key = private_location(private_key)
    private_root(private_key.parent)
    key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 signing key required")
    payload = signature_payload(artifact, key.public_key())
    envelope = {
        "payload": payload,
        "signature": base64.b64encode(key.sign(canonical(payload))).decode("ascii"),
    }
    with Path(destination).open("xb") as stream:
        stream.write(canonical(envelope))
    return payload


def verify_signature(artifact, signature, public_key):
    key = serialization.load_pem_public_key(Path(public_key).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("An explicit Ed25519 trust anchor is required")
    envelope = json.loads(Path(signature).read_text(encoding="utf-8"))
    if set(envelope) != {"payload", "signature"}:
        raise ValueError("Invalid detached signature envelope")
    expected = signature_payload(artifact, key)
    if envelope["payload"] != expected:
        raise ValueError("Signature payload does not match package or trust anchor")
    key.verify(base64.b64decode(envelope["signature"], validate=True), canonical(expected))
    return expected
