import os
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from app.core import evidence
from app.core.errors import CommandError

PDF = b"%PDF-1.7\nSynthetic local test only\n%%EOF\n"


def test_content_validates_size_extension_mime_signature_and_names():
    evidence.validate_content(PDF, "synthetic.pdf", "application/pdf", 1000)
    for content, name, media, limit, status in [
        (PDF, "synthetic.pdf", "application/pdf", 1, 413),
        (b"", "synthetic.pdf", "application/pdf", 1000, 413),
        (PDF, "../../unsafe.pdf", "application/pdf", 1000, 422),
        (PDF, "unsafe\r\n.pdf", "application/pdf", 1000, 422),
        (b"<svg></svg>", "synthetic.svg", "image/svg+xml", 1000, 415),
        (b"<html></html>", "synthetic.pdf", "application/pdf", 1000, 415),
        (PDF, "synthetic.png", "image/png", 1000, 415),
    ]:
        with pytest.raises(CommandError) as error:
            evidence.validate_content(content, name, media, limit)
        assert error.value.status == status


def version(age=timedelta()):
    return "ClamAV 1.4.3/99999/" + (datetime.now(UTC) - age).strftime("%a %b %d %H:%M:%S %Y")


@pytest.mark.parametrize(
    "reply,status", [("stream: OK", None), ("stream: Test FOUND", 422), ("ERROR", 503)]
)
def test_scanner_requires_exact_clean_response(monkeypatch, reply, status):
    scanner = evidence.ClamAV(3310)
    monkeypatch.setattr(
        scanner,
        "exchange",
        lambda command, content=None: version() if command == b"zVERSION\0" else reply,
    )
    if status:
        with pytest.raises(CommandError) as error:
            scanner(PDF)
        assert error.value.status == status
    else:
        assert scanner(PDF).startswith("ClamAV ")


def test_old_definitions_and_missing_scanner_fail_closed(monkeypatch):
    scanner = evidence.ClamAV(3310)
    monkeypatch.setattr(scanner, "exchange", lambda *arguments: version(timedelta(days=2)))
    with pytest.raises(CommandError):
        scanner(PDF)

    def unavailable(*arguments):
        raise OSError()

    monkeypatch.setattr(evidence.socket, "create_connection", unavailable)
    with pytest.raises(CommandError):
        evidence.ClamAV(3310)(PDF)


def test_quarantine_publication_and_rejection_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "private_root", lambda root: None)
    for name in ("quarantine", "objects"):
        (tmp_path / name).mkdir()
    store = evidence.EvidenceStore(tmp_path, lambda content: version())
    key, digest, _version = store.publish(PDF)
    assert store.available(key, len(PDF), digest).read_bytes() == PDF
    assert list((tmp_path / "quarantine").iterdir()) == []
    store.scanner = lambda content: (_ for _ in ()).throw(CommandError(422, "MALWARE_DETECTED"))
    with pytest.raises(CommandError):
        store.publish(PDF)
    assert len(list((tmp_path / "objects").iterdir())) == 1
    assert list((tmp_path / "quarantine").iterdir()) == []
    with pytest.raises(CommandError):
        store.available("../unsafe", 1, digest)


def test_store_detects_tampered_content(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "private_root", lambda root: None)
    for name in ("quarantine", "objects"):
        (tmp_path / name).mkdir()
    store = evidence.EvidenceStore(tmp_path, lambda content: version())
    key, digest, _version = store.publish(PDF)
    store.path(key).write_bytes(b"!" * len(PDF))
    with pytest.raises(CommandError):
        store.available(key, len(PDF), digest)


def test_native_private_acl_rejects_shared_access(tmp_path):
    from tools.f1_local import private_directory

    private_directory(tmp_path)
    evidence.private_root(tmp_path)
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(tmp_path), "/grant", "*S-1-1-0:(OI)(CI)R"],
            check=True,
            capture_output=True,
        )
    else:
        tmp_path.chmod(0o755)
    try:
        with pytest.raises(CommandError):
            evidence.private_root(tmp_path)
    finally:
        if os.name == "nt":
            subprocess.run(
                ["icacls", str(tmp_path), "/remove:g", "*S-1-1-0"], check=True, capture_output=True
            )
        else:
            tmp_path.chmod(0o700)


def test_storage_under_checkout_is_not_private():
    with pytest.raises(CommandError):
        evidence.private_root(evidence.BACKEND_DIR)
