import json
import zipfile
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tools.delivery import ROOT, allowed, package, sha, verify


@pytest.fixture
def portable_binaries(tmp_path):
    from tools.delivery import POSTGRES_EXECUTABLES
    root = tmp_path / "portable-input"
    for folder in ("bin", "lib", "share"):
        (root / folder).mkdir(parents=True)
    for name in POSTGRES_EXECUTABLES:
        (root / "bin" / name).write_bytes(b"synthetic executable fixture; never run")
    (root / "lib/runtime.dll").write_bytes(b"synthetic library")
    (root / "share/postgresql.conf.sample").write_text("synthetic template")
    return root


def test_optional_portable_package_is_deterministic_signed_inventory(
    build, tmp_path, portable_binaries,
):
    first, second = tmp_path / "portable1.zip", tmp_path / "portable2.zip"
    manifest = package(ROOT, build, first, portable_binaries)
    package(ROOT, build, second, portable_binaries)
    assert first.read_bytes() == second.read_bytes()
    assert verify(first) == manifest
    assert manifest["portable_postgres"]["included"]
    assert "postgres/bin/initdb.exe" in manifest["files"]
    assert not any(name.startswith("database/") for name in manifest["files"])
    with zipfile.ZipFile(first) as archive:
        sbom = json.loads(archive.read("sbom.cdx.json"))
    native = {component["name"]: component["hashes"][0]["content"]
              for component in sbom["components"] if component["type"] == "file"}
    assert native == {name: metadata["sha256"] for name, metadata in manifest["files"].items()
                      if name.startswith("postgres/")}


@pytest.mark.parametrize("name", ["PG_VERSION", "postmaster.pid", "postgresql.conf",
                                 "postmaster.opts", "backup.dump", "postgres.log"])
def test_portable_package_rejects_live_files(build, tmp_path, portable_binaries, name):
    (portable_binaries / "share" / name).write_text("synthetic live input must be rejected")
    with pytest.raises(ValueError):
        package(ROOT, build, tmp_path / "forbidden.zip", portable_binaries)
    assert not (tmp_path / "forbidden.zip").exists()


def test_portable_package_requires_all_executables(build, tmp_path, portable_binaries):
    (portable_binaries / "bin/initdb.exe").unlink()
    with pytest.raises(ValueError):
        package(ROOT, build, tmp_path / "missing.zip", portable_binaries)


@pytest.mark.parametrize("portable,trusted", [(True, True), (False, True), (True, False)])
def test_upgrade_defaults_only_to_exact_signed_portable_tree(
    build, tmp_path, portable_binaries, monkeypatch, portable, trusted,
):
    from tools import delivery, delivery_security, delivery_upgrade

    artifact = tmp_path / "release.zip"
    manifest = package(ROOT, build, artifact, portable_binaries if portable else None)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(extracted)
    monkeypatch.setattr(delivery, "ROOT", extracted)
    monkeypatch.setattr(delivery_security, "verify_signature", lambda *_args: {
        "manifest_sha256": sha(delivery.canonical(manifest)) if trusted else "0" * 64,
    })
    command = MagicMock()
    monkeypatch.setattr(delivery_upgrade, "interactive_upgrade", command)
    monkeypatch.setattr("sys.argv", ["delivery", "upgrade", "--artifact", str(artifact),
        "--evidence", str(tmp_path / "evidence"), "--maintenance", str(tmp_path / "maintenance"),
        "--trusted-sha256", "0" * 64, "--restore-database", "synthetic_restore",
        "--operator", "synthetic", "--writers-stopped", "--execute",
        "--signature", "synthetic.sig", "--public-key", "synthetic.pub"])
    if portable and trusted:
        delivery.main()
        assert command.call_args.args[0].pg_bin == extracted / "postgres/bin"
    else:
        with pytest.raises(ValueError, match="explicit pg-bin"):
            delivery.main()
        command.assert_not_called()


@pytest.mark.parametrize("mutation", ["none", "zip", "manifest", "signature", "wrong-key"])
def test_ed25519_detached_signature_fail_closed(build, tmp_path, mutation):
    import base64

    from cryptography.exceptions import InvalidSignature

    from tools.delivery_security import keygen, sign, verify_signature

    artifact = tmp_path / "signed.zip"
    package(ROOT, build, artifact)
    private, public = keygen(tmp_path / "ephemeral-keys")
    signature = tmp_path / "signed.zip.sig"
    sign(artifact, private, signature)
    if mutation == "none":
        assert verify_signature(artifact, signature, public)["algorithm"] == "Ed25519"
        return
    if mutation == "zip":
        with artifact.open("ab") as stream:
            stream.write(b"tampered trailing bytes")
    elif mutation == "manifest":
        with zipfile.ZipFile(artifact, "a") as archive:
            archive.writestr("manifest.json", '{"format":1}')
    elif mutation == "signature":
        envelope = json.loads(signature.read_text())
        content = bytearray(base64.b64decode(envelope["signature"]))
        content[0] ^= 1
        envelope["signature"] = base64.b64encode(content).decode()
        signature.write_text(json.dumps(envelope))
    else:
        _, public = keygen(tmp_path / "different-ephemeral-keys")
    with pytest.raises((ValueError, InvalidSignature, KeyError)):
        verify_signature(artifact, signature, public)


def test_ed25519_keys_cannot_be_created_inside_repository():
    from tools.delivery_security import keygen

    with pytest.raises(ValueError):
        keygen(ROOT / "forbidden-signing-keys")


def test_cyclonedx_sbom_is_deterministic_exact_and_packaged(build, tmp_path):
    from app.services.installation import canonical
    from tools.delivery_sbom import generate, validate

    first, second = generate(ROOT), generate(ROOT)
    assert canonical(first) == canonical(second)
    validate(first)
    assert first["bomFormat"] == "CycloneDX" and first["specVersion"] == "1.6"
    assert "timestamp" not in first["metadata"] and "serialNumber" not in first
    assert any(
        component["purl"].startswith("pkg:pypi/psycopg@") for component in first["components"]
    )
    assert any(
        component["purl"].startswith("pkg:npm/%40angular/core@")
        for component in first["components"]
    )
    assert all(
        component.get("hashes")
        for component in first["components"]
        if component["purl"].startswith("pkg:pypi/")
    )
    artifact = tmp_path / "sbom.zip"
    manifest = package(ROOT, build, artifact)
    assert "sbom.cdx.json" in manifest["files"]
    with zipfile.ZipFile(artifact) as archive:
        assert archive.read("sbom.cdx.json") == canonical(first)


def test_python_audit_uses_exact_versions_and_reports_unknown_severity(tmp_path):
    import httpx

    from app.services.installation import private_directory
    from tools.delivery_audit import python_audit

    private_directory(tmp_path)

    def respond(request):
        if request.method == "POST":
            assert json.loads(request.content)["queries"][0]["version"] == "1.2.3"
            return httpx.Response(200, json={"results": [{"vulns": [{"id": "SYNTHETIC-1"}]}]})
        return httpx.Response(200, json={"id": "SYNTHETIC-1", "affected": []})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = python_audit(client, [{"name": "synthetic", "version": "1.2.3"}], tmp_path)
    assert report["affected_components_by_max_severity"]["unknown"] == 1
    assert report["status"] == "complete"


def test_python_advisory_alias_inherits_known_severity_without_double_count():
    from tools.delivery_audit import advisory_groups

    result = advisory_groups(
        [
            {
                "id": "GHSA-synthetic",
                "aliases": ["CVE-synthetic"],
                "database_specific": {"severity": "MODERATE"},
            },
            {"id": "PYSEC-synthetic", "aliases": ["CVE-synthetic"], "database_specific": None},
            {"id": "GHSA-other", "database_specific": {"severity": "LOW"}},
        ]
    )
    assert len(result) == 2
    assert sorted(group["severity"] for group in result) == ["low", "moderate"]


@pytest.mark.parametrize(
    "mutation",
    ["none", "instance", "receipt", "marker", "health", "runtime-identity", "tls", "receipt-write"],
)
def test_reopen_requires_signed_verified_instance_and_health(
    build, tmp_path, monkeypatch, mutation
):
    import hmac
    from datetime import UTC, datetime, timedelta

    import httpx
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    from app.services.installation import HEAD, canonical, private_directory, write_private
    from tools import delivery_operations as operations
    from tools.delivery_security import keygen, sign, verify_signature

    private_directory(tmp_path)
    artifact = tmp_path / "release.zip"
    package(ROOT, build, artifact)
    private, public = keygen(tmp_path / "ephemeral-keys")
    signature = tmp_path / "release.zip.sig"
    sign(artifact, private, signature)
    trusted = verify_signature(artifact, signature, public)
    state, evidence = tmp_path / "state", tmp_path / "upgrade"
    private_directory(state)
    private_directory(evidence)
    instance, release, request = str(uuid4()), str(uuid4()), str(uuid4())
    marker = state / "maintenance.json"
    marker_bytes = canonical(
        {
            "state": "maintenance",
            "head": HEAD,
            "instance": instance,
            "release": release,
            "request_id": request,
        }
    )
    write_private(marker, marker_bytes)
    completed = {
        "state": "verified_pending_reopening",
        "head": HEAD,
        "instance": instance,
        "release": release,
        "request_id": request,
        "backup": {
            "head": HEAD,
            "verified_at": "2026-11-27T00:00:00+00:00",
            "restore_input": "authenticated-decryption-of-encrypted-backup",
        },
        "artifact_sha256": trusted["zip_sha256"],
        "manifest_sha256": trusted["manifest_sha256"],
        "maintenance_sha256": sha(marker_bytes),
    }
    root = bytes(range(32))
    completed["receipt_mac"] = hmac.digest(root, canonical(completed), "sha256").hex()
    receipt = evidence / "complete.json"
    write_private(receipt, canonical(completed))
    monkeypatch.setattr(
        operations,
        "read_bootstrap",
        lambda _path: {
            "instance": instance,
            "auth_origin": "https://customer.example.invalid",
            "health_token": "synthetic-health-token-for-tests-only",
        },
    )
    monkeypatch.setattr(operations.OSSealedFile, "read", lambda _self: root)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-only")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    ca = tmp_path / "synthetic-ca.crt"
    ca.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))

    def respond(http_request):
        if http_request.url.path.endswith("/live"):
            return httpx.Response(200, json={"status": "alive"})
        assert http_request.headers["X-Health-Token"] == "synthetic-health-token-for-tests-only"
        return httpx.Response(
            503 if mutation == "health" else 200,
            json={"status": "ready"},
            headers={
                "X-OCOTE-Instance": str(uuid4()) if mutation == "runtime-identity" else instance,
                "X-OCOTE-Head": HEAD,
                "X-OCOTE-Manifest": trusted["manifest_sha256"],
            },
        )

    if mutation == "receipt":
        completed["state"] = "running"
        receipt.write_bytes(canonical(completed))
    if mutation == "marker":
        marker.write_bytes(marker_bytes + b" ")
    if mutation == "tls":
        ca.write_text("invalid CA fixture")
    if mutation == "receipt-write":
        original = operations.write_private

        def fail_final(path, content):
            if path.name == "reopen.json":
                raise OSError("synthetic receipt disk failure")
            return original(path, content)

        monkeypatch.setattr(operations, "write_private", fail_final)
    values = {
        "state": state,
        "receipt": receipt,
        "maintenance": marker,
        "expected_instance": str(uuid4()) if mutation == "instance" else instance,
        "origin": "https://customer.example.invalid",
        "ca_file": ca,
        "artifact": artifact,
        "signature": signature,
        "public_key": public,
        "operator": "Synthetic operator",
        "client_factory": lambda **options: httpx.Client(
            **options, transport=httpx.MockTransport(respond)
        ),
    }
    if mutation != "none":
        with pytest.raises((ValueError, OSError)):
            operations.reopen(**values)
        assert marker.exists()
    else:
        result = operations.reopen(**values)
        assert result["state"] == "reopened" and result["sql_connections_opened"] == 0
        assert not marker.exists() and (evidence / "reopened-maintenance.json").exists()
        assert json.loads((evidence / "reopen.json").read_text())["instance"] == instance


def test_operations_templates_are_deterministic_unregistered_and_without_credentials():
    from defusedxml.ElementTree import fromstring

    from tools.delivery_templates import templates
    from tools.delivery_worker import build_worker

    first, second = templates(), templates()
    assert first == second
    assert len([name for name in first if name.endswith(".task.xml.template")]) == 6
    for name, content in first.items():
        if ".xml." in name:
            fromstring(content)
        assert b"powershell.exe" not in content.lower()
        assert b"<Password>" not in content
        assert b"__" in content or name.endswith("README.md")
    assert b"--public-key" in first["operations/api.task.xml.template"]
    assert b"__APPROVED_OFF_HOST_UNC__" in first["operations/backup.task.xml.template"]
    worker = build_worker(ROOT)
    compile(worker, "<generated-worker>", "exec")
    assert b"WORKER_SOURCE_SHA256" in worker
    assert b"def main(" not in worker


def test_restore_measurement_requires_verified_uuid_and_measures_goals(tmp_path):
    from tools.delivery_templates import record_restore

    identity = uuid4()
    proof = tmp_path / "proof.json"
    values = {
        "instance": str(uuid4()),
        "isolated_target_uuid": str(identity),
        "target_database": "ocote_f2_restore_" + identity.hex,
        "restore_verified": True,
        "backup_sha256": "a" * 64,
        "encrypted_backup_sha256": "b" * 64,
        "recoverable_data_at": "2026-11-27T00:00:00+00:00",
        "incident_at": "2026-11-27T01:00:00+00:00",
        "restore_started_at": "2026-11-27T01:00:00+00:00",
        "restore_finished_at": "2026-11-27T01:10:00+00:00",
    }
    proof.write_text(json.dumps(values))
    report = record_restore(proof, tmp_path / "measurement.json", 86400, 14400)
    assert report["rpo_seconds"] == 3600 and report["rto_seconds"] == 600
    assert report["goals_met"]
    values["target_database"] = "ocoteAppDatabase"
    proof.write_text(json.dumps(values))
    with pytest.raises(ValueError):
        record_restore(proof, tmp_path / "forbidden.json", 86400, 14400)


def test_technical_log_rotation_is_bounded_and_private(tmp_path):
    from app.services.installation import private_directory
    from tools.delivery import logging_profile

    private_directory(tmp_path)
    profile = logging_profile(tmp_path / "api.log", 1048576, 8)
    assert profile["handlers"]["technical"]["backupCount"] == 8
    assert profile["handlers"]["technical"]["class"] == "logging.handlers.RotatingFileHandler"
    with pytest.raises(ValueError):
        logging_profile(tmp_path / "api.log", 1, 0)


def test_distributed_runtime_fences_writes_but_exposes_authenticated_health_identity(
    tmp_path,
    monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.services.installation import HEAD, canonical, private_directory
    from tools import delivery, delivery_runtime

    state, release = tmp_path / "state", tmp_path / "release"
    private_directory(state)
    release.mkdir()
    manifest = canonical({"head": HEAD, "files": {}})
    (release / "manifest.json").write_bytes(manifest)
    identity = str(uuid4())
    monkeypatch.setattr(delivery, "ROOT", release)
    monkeypatch.setattr(
        delivery_runtime,
        "read_bootstrap",
        lambda _path: {
            "instance": identity,
            "state": "sealed",
            "auth_origin": "https://localhost:8443",
            "organization_timezone": "America/Mexico_City",
            "health_token": "synthetic-health-token-for-tests-only",
            "signing_key": "synthetic-only",
            "csrf": "a" * 64,
            "connection": {
                "mode": "local",
                "sslmode": "disable",
                "approved_address": "127.0.0.1",
                "host": "127.0.0.1",
                "port": 5432,
                "database": "ocoteAppDatabase",
                "runtime_password": "synthetic-only",
            },
        },
    )
    monkeypatch.setattr(delivery_runtime, "Tokens", lambda _auth: object())
    fake = FastAPI()
    calls = []

    @fake.post("/api/v1/synthetic-write")
    def write():
        calls.append("write")
        return {"ok": True}

    @fake.get("/api/v1/health/ready")
    def ready():
        return {"status": "ready"}

    monkeypatch.setattr(delivery_runtime, "create_app", lambda *_args, **_kwargs: fake)
    app = delivery_runtime.runtime_app(state)
    (state / "maintenance.json").write_text('{"state":"maintenance"}')
    with TestClient(app) as client:
        assert client.post("/api/v1/synthetic-write").status_code == 503
        assert not calls
        response = client.get("/api/v1/health/ready")
        assert response.headers["X-OCOTE-Instance"] == identity
        assert response.headers["X-OCOTE-Manifest"] == sha(manifest)
        (state / "maintenance.json").unlink()
        assert client.post("/api/v1/synthetic-write").status_code == 200
    assert calls == ["write"]


def test_vault_verification_uses_persisted_secret_version():
    from app.core.vault import Vault
    from tools.delivery_upgrade import verify_vault

    instance, owner = uuid4(), uuid4()
    root = bytes(range(32))
    vault = Vault(root, instance, "windows-dpapi-v1")
    key = vault.new_key("local_storage", 1)
    value = vault.encrypt(key, owner, 7, b"synthetic-private-value")
    database = MagicMock()
    database.execute.return_value.fetchall.return_value = [
        (
            key.id,
            key.instance_id,
            key.purpose,
            key.epoch,
            key.root_key_ref,
            key.nonce,
            key.wrapped_dek,
            value.owner_id,
            value.version,
            value.nonce,
            value.ciphertext,
            key.id,
        )
    ]
    verify_vault(database, root, instance)
    query = database.execute.call_args.args[0]
    assert "e.secret_version" in query and "e.version" not in query


def test_packaged_harness_fails_before_sql_for_non_distribution(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    harness = Path(__file__).with_name("test_delivery_postgres.py")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment["PYTHONPATH"] = str(ROOT / "backend")
    result = subprocess.run(
        [sys.executable, "-u", str(harness)],
        input="{}",
        text=True,
        capture_output=True,
        env=environment,
        cwd=ROOT,
        timeout=30,
    )
    assert result.returncode == 1
    reports = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
    assert reports[-1]["stage"] == "package-integrity"
    assert reports[-1]["error_type"] == "FileNotFoundError"


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "backend/.env",
        "backend/.local/auth.env",
        "../secret",
        "/secret",
        "C:/secret",
        "database/data/PG_VERSION",
        "node_modules/library.js",
        "logs/server.log",
        "keys/master.dpapi",
        "backend/tests/test_data.py",
        "backend/.venv/python.exe",
    ],
)
def test_exclusions(name):
    assert not allowed(name)


@pytest.fixture
def build(tmp_path):
    directory = tmp_path / "dist/browser"
    directory.mkdir(parents=True)
    (directory / "index.html").write_text("<main>OCOTE synthetic fixture</main>")
    (directory.parent / "3rdpartylicenses.txt").write_text("Synthetic license fixture only")
    (directory.parent / "architect-result.json").write_text(
        json.dumps(
            {
                "success": True,
                "configuration": "production",
                "files": {"index.html": sha((directory / "index.html").read_bytes())},
            }
        )
    )
    return directory


def test_reproducible_complete_manifest_and_no_secrets(build, tmp_path):
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    manifest = package(ROOT, build, first)
    package(ROOT, build, second)
    assert first.read_bytes() == second.read_bytes()
    assert verify(first) == manifest
    assert all(allowed(name) for name in manifest["files"])
    assert ".env.example" in manifest["files"]
    assert not any(name.startswith("database/") for name in manifest["files"])
    assert not any("delivery_cut2" in name or "/tools/f" in name for name in manifest["files"])
    with zipfile.ZipFile(first) as archive:
        assert b"holamundo" not in archive.read(".env.example")
        assert (
            sha(archive.read("frontend/index.html"))
            == manifest["files"]["frontend/index.html"]["sha256"]
        )


def test_manifest_rejects_tampering_and_extra_files(build, tmp_path):
    artifact = tmp_path / "clean.zip"
    package(ROOT, build, artifact)
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr("injected.txt", "not covered")
    with pytest.raises(ValueError):
        verify(artifact)


def test_requires_successful_architect_build(build, tmp_path):
    (build.parent / "architect-result.json").write_text('{"success":false}')
    with pytest.raises(ValueError):
        package(ROOT, build, tmp_path / "blocked.zip")
    assert not (tmp_path / "blocked.zip").exists()


def test_stale_frontend_receipt_is_rejected(build, tmp_path):
    (build / "index.html").write_text("changed after successful build")
    with pytest.raises(ValueError):
        package(ROOT, build, tmp_path / "stale.zip")
    assert not (tmp_path / "stale.zip").exists()


def test_backup_ciphertext_roundtrip_is_authenticated(tmp_path):
    from uuid import uuid4

    from app.services.installation import private_directory, write_private
    from tools.delivery_upgrade import encrypt_backup

    private_directory(tmp_path)
    dump = tmp_path / "synthetic.dump"
    plaintext = b"PGDMP synthetic only no business data" * 100
    write_private(dump, plaintext)
    encrypted = encrypt_backup(dump, bytes(range(32)), uuid4())
    assert plaintext not in encrypted.read_bytes()
    metadata = json.loads(encrypted.with_suffix(".json").read_text())
    assert metadata["plaintext_sha256"] == sha(plaintext)
    assert metadata["algorithm"] == "AES-256-GCM"


def test_restore_uses_ciphertext_and_cleans_plaintext_on_consumer_failure(tmp_path):
    from app.services.installation import private_directory, write_private
    from tools.delivery_upgrade import encrypt_backup, restore_payload

    private_directory(tmp_path)
    dump = tmp_path / "source.dump"
    content = b"PGDMP synthetic encrypted recovery fixture"
    write_private(dump, content)
    instance, root = uuid4(), bytes(range(32))
    encrypted = encrypt_backup(dump, root, instance)
    dump.unlink()
    with pytest.raises(RuntimeError, match="SYNTHETIC_RESTORE_FAILURE"):
        with restore_payload(encrypted, root, instance) as restored:
            assert restored.read_bytes() == content
            raise RuntimeError("SYNTHETIC_RESTORE_FAILURE")
    assert not restored.exists()
    assert encrypted.exists()


def test_restore_rejects_tampered_ciphertext_before_exposing_payload(tmp_path):
    from app.core.errors import CommandError
    from app.services.installation import private_directory, write_private
    from tools.delivery_upgrade import encrypt_backup, restore_payload

    private_directory(tmp_path)
    dump = tmp_path / "source.dump"
    write_private(dump, b"PGDMP synthetic tamper fixture")
    instance, root = uuid4(), bytes(range(32))
    encrypted = encrypt_backup(dump, root, instance)
    content = bytearray(encrypted.read_bytes())
    content[0] ^= 1
    encrypted.write_bytes(content)
    with pytest.raises(CommandError) as error:
        with restore_payload(encrypted, root, instance):
            pytest.fail("Unauthenticated plaintext exposed")
    assert error.value.code == "DELIVERY_BACKUP_AUTHENTICATION_FAILED"
    assert not list(tmp_path.glob("*.restore.dump"))


def test_changed_approval_revokes_cut2_capture(tmp_path, monkeypatch):
    from tools import delivery_cut2

    capture = tmp_path / "synthetic.dpapi"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    capture.write_bytes(b"synthetic authorization marker only")
    monkeypatch.setattr(delivery_cut2, "authorization_path", lambda: capture)
    monkeypatch.setattr(
        "sys.argv",
        ["delivery_cut2", "final-gates", "--execute", "--approval", str(tmp_path / "missing.json")],
    )
    with pytest.raises(FileNotFoundError):
        delivery_cut2.main()
    assert not capture.exists()


@pytest.mark.parametrize("outcome", ["skipped", "timeout"])
def test_uuid_gate_cannot_pass_by_skipping_and_revokes_all_synthetic_seals(
    tmp_path,
    monkeypatch,
    outcome,
):
    import time
    from pathlib import Path

    from app.core.errors import CommandError
    from app.services.installation import canonical
    from tools import delivery_cut2 as driver

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    capture = tmp_path / "administrator.dpapi"
    capture.write_bytes(b"synthetic-only")
    other = tmp_path / "OCOTE/f8-operator/administrator.dpapi"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"synthetic-only")
    monkeypatch.setattr(driver, "authorization_path", lambda: capture)
    monkeypatch.setattr(driver, "validate_approval", lambda _path: "synthetic-approval")
    (tmp_path / "manifest.json").write_text('{"pending_uuid_cleanup":[]}')
    monkeypatch.setattr(driver, "uuid_databases", lambda _password: set())
    monkeypatch.setattr(driver, "cleanup_uuids", lambda *_arguments: None)
    monkeypatch.setattr(
        driver.OSSealedFile,
        "read",
        lambda _self: canonical(
            {
                "approval": "synthetic-approval",
                "purpose": "f7-delivery-uuid-and-pg1-only",
                "expires": time.time() + 3600,
                "password": "synthetic-not-an-operative-credential",
            }
        ),
    )

    def skipped_command(arguments, **options):
        options["log"].write_bytes(b"synthetic progress before completion or timeout")
        assert options["timeout"] <= 600
        if outcome == "timeout":
            return 124
        junit = Path(
            next(value.split("=", 1)[1] for value in arguments if value.startswith("--junitxml="))
        )
        junit.write_text(
            '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="1"/></testsuites>'
        )
        return 0

    monkeypatch.setattr(driver, "run_gate", skipped_command)
    monkeypatch.setattr(driver, "private_directory", lambda path: path.mkdir(parents=True))
    monkeypatch.setattr("app.services.installation.private_root", lambda _path: None)
    artifacts = tmp_path / "gates"
    monkeypatch.setattr(
        "sys.argv",
        [
            "driver",
            "final-gates",
            "--execute",
            "--approval",
            str(tmp_path / "manifest.json"),
            "--artifacts",
            str(artifacts),
        ],
    )
    with pytest.raises(CommandError) as error:
        driver.main()
    assert error.value.code == (
        "DELIVERY_GATE_TIMEOUT" if outcome == "timeout" else "DELIVERY_GATE_NOT_FULLY_EXECUTED"
    )
    assert not capture.exists() and not other.exists()
    assert not (artifacts / "complete.json").exists()
    assert (
        (artifacts / "isolated-install-upgrade.txt").read_bytes().startswith(b"synthetic progress")
    )


def test_windows_job_runs_only_new_benign_process_and_keeps_log(tmp_path):
    import os
    import sys

    from app.services.installation import private_directory
    from tools.delivery_cut2 import run_gate

    if os.name != "nt":
        pytest.skip("Windows distribution target only")
    private_directory(tmp_path)
    log = tmp_path / "job.txt"
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    result = run_gate(
        [sys.executable, "-u", "-c", 'print("synthetic-owned-process")'],
        cwd=tmp_path,
        env=environment,
        log=log,
        timeout=30,
    )
    assert result == 0
    assert log.read_text().strip() == "synthetic-owned-process"


@pytest.mark.parametrize("name", ["ocoteAppDatabase", "postgres", "ocote_f2_test_not_uuid"])
def test_uuid_cleanup_never_accepts_origin_or_unapproved_names(tmp_path, monkeypatch, name):
    from app.core.errors import CommandError
    from tools import delivery_cut2 as driver

    connect = MagicMock(side_effect=AssertionError("No SQL allowed for invalid destination"))
    monkeypatch.setattr(driver.psycopg, "connect", connect)
    with pytest.raises(CommandError) as error:
        driver.cleanup_uuids([name], "synthetic", tmp_path, "cleanup")
    assert error.value.code == "DELIVERY_CLEANUP_DESTINATION_REJECTED"
    connect.assert_not_called()


@pytest.mark.parametrize("owner,sessions", [("ocote_runtime", 0), ("ocote_migrador", 1)])
def test_uuid_cleanup_requires_migrator_owner_and_zero_sessions(
    tmp_path,
    monkeypatch,
    owner,
    sessions,
):
    from app.core.errors import CommandError
    from tools import delivery_cut2 as driver

    database = MagicMock()
    database.execute.side_effect = [
        MagicMock(fetchone=lambda: ("postgres", "180004", str(ROOT / "database/data"))),
        MagicMock(fetchone=lambda: (owner, sessions)),
    ]
    monkeypatch.setattr(
        driver.psycopg,
        "connect",
        MagicMock(
            return_value=MagicMock(
                __enter__=lambda _self: database,
                __exit__=lambda *_values: None,
            )
        ),
    )
    with pytest.raises(CommandError) as error:
        driver.cleanup_uuids(["ocote_f2_test_" + "a" * 32], "synthetic", tmp_path, "cleanup")
    assert error.value.code == "DELIVERY_CLEANUP_OWNERSHIP_OR_SESSIONS"
    assert not any("DROP DATABASE" in str(call.args[0]) for call in database.execute.call_args_list)


def test_uuid_cleanup_drops_only_exact_validated_database_without_force(tmp_path, monkeypatch):
    from tools import delivery_cut2 as driver

    name = "ocote_f2_test_" + "b" * 32
    database = MagicMock()
    database.execute.side_effect = [
        MagicMock(fetchone=lambda: ("postgres", "180004", str(ROOT / "database/data"))),
        MagicMock(fetchone=lambda: ("ocote_migrador", 0)),
        MagicMock(),
    ]
    monkeypatch.setattr(
        driver.psycopg,
        "connect",
        MagicMock(
            return_value=MagicMock(
                __enter__=lambda _self: database,
                __exit__=lambda *_values: None,
            )
        ),
    )
    monkeypatch.setattr(driver, "write_private", lambda path, content: path.write_bytes(content))
    driver.cleanup_uuids([name], "synthetic", tmp_path, "cleanup")
    statement = database.execute.call_args.args[0].as_string()
    assert statement == 'DROP DATABASE "' + name + '"'
    assert "FORCE" not in statement and "ocoteAppDatabase" not in statement
    assert json.loads((tmp_path / "cleanup-complete.json").read_text()) == {"removed": [name]}


def test_pure_support_keeps_only_approved_predicate_equivalences():
    from tools.delivery_support import SOURCES, build_support, load_support

    module = load_support()
    assert set(module.SUPPORT_SOURCE_SHA256) == set(SOURCES)
    source = build_support(ROOT).decode()
    assert "def apply(" not in source and "def admin_connection(" not in source
    first = "kind = ANY (ARRAY['sso'::text, 'devops'::text, 'outgoing_webhook'::text])"
    second = "kind = ANY ((ARRAY['sso'::character varying, 'devops'::character varying, "
    second += "'outgoing_webhook'::character varying])::text[])"
    assert module.canonical_kind_predicate(
        first, module.PROVIDER_KINDS
    ) == module.canonical_kind_predicate(second, module.PROVIDER_KINDS)
