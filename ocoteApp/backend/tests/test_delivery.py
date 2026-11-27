import json
import zipfile
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tools.delivery import ROOT, allowed, package, sha, verify


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
