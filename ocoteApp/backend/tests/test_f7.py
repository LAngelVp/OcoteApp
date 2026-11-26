import os
from dataclasses import replace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from test_identity import api as api
from test_identity import tokens as tokens

from app.core.errors import CommandError
from app.core.vault import OSSealedFile, Vault, os_protect


def test_vault_roundtrip_and_rotation():
    vault = Vault(AESGCM.generate_key(bit_length=256), uuid4(), "synthetic-root")
    owner = uuid4()
    first, second = vault.new_key("csrf", 1), vault.new_key("csrf", 2)
    old = vault.encrypt(first, owner, 1, b" exact synthetic secret ")
    new = vault.encrypt(second, owner, 2, b"rotated synthetic secret")
    assert vault.decrypt(first, old) == b" exact synthetic secret "
    assert vault.decrypt(second, new) == b"rotated synthetic secret"
    assert b"synthetic secret" not in old.ciphertext
    assert "ciphertext" not in repr(old)
    assert "wrapped_dek" not in repr(first)
    with pytest.raises(CommandError):
        vault.decrypt(second, old)


@pytest.mark.parametrize("field", ["ciphertext", "nonce", "owner_id", "version", "key_id"])
def test_vault_rejects_modified_value(field):
    vault = Vault(os.urandom(32), uuid4(), "synthetic-root")
    key = vault.new_key("csrf", 1)
    value = vault.encrypt(key, uuid4(), 1, b"synthetic value")
    original = getattr(value, field)
    replacement = (
        original[:-1] + bytes([original[-1] ^ 1])
        if isinstance(original, bytes)
        else 2
        if field == "version"
        else uuid4()
    )
    with pytest.raises(CommandError) as error:
        vault.decrypt(key, replace(value, **{field: replacement}))
    assert error.value.status == 503


@pytest.mark.parametrize(
    "field", ["wrapped_dek", "nonce", "instance_id", "purpose", "epoch", "root_key_ref"]
)
def test_vault_rejects_modified_key(field):
    vault = Vault(os.urandom(32), uuid4(), "synthetic-root")
    key = vault.new_key("csrf", 1)
    value = vault.encrypt(key, uuid4(), 1, b"synthetic value")
    original = getattr(key, field)
    replacement = (
        original[:-1] + bytes([original[-1] ^ 1])
        if isinstance(original, bytes)
        else uuid4()
        if field == "instance_id"
        else 2
        if field == "epoch"
        else "backup"
    )
    with pytest.raises(CommandError):
        vault.decrypt(replace(key, **{field: replacement}), value)


def test_vault_missing_root_never_generates_a_replacement():
    with pytest.raises(CommandError):
        Vault(b"", uuid4(), "synthetic-root")


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI platform-specific test")
def test_real_windows_seal_is_bound_to_instance_and_never_overwrites(tmp_path):
    instance = uuid4()
    path = tmp_path / "bootstrap.sealed"
    root = os.urandom(32)
    seal = OSSealedFile(path, instance)
    seal.create(root)
    assert root not in path.read_bytes()
    assert seal.read() == root
    with pytest.raises(CommandError):
        seal.create(os.urandom(32))
    assert seal.read() == root
    with pytest.raises(CommandError):
        OSSealedFile(path, uuid4()).read()
    with pytest.raises(CommandError):
        OSSealedFile(tmp_path / "missing.sealed", instance).read()
    assert not (tmp_path / "missing.sealed").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI platform-specific test")
def test_real_windows_seal_tamper_fails_closed():
    instance = uuid4()
    protected = os_protect(b"synthetic bootstrap", instance)
    tampered = protected[:-1] + bytes([protected[-1] ^ 1])
    with pytest.raises(CommandError):
        os_protect(tampered, instance, decrypt=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI platform-specific test")
def test_operator_handoff_never_stores_cleartext_or_overwrites(tmp_path):
    from tools.f7_local import authorized_password, save_authorization

    path = tmp_path / "operator" / "administrator.dpapi"
    password = " synthetic local admin authorization "
    save_authorization(password, path=path, issued_at=1000)
    assert password.encode() not in path.read_bytes()
    assert authorized_password(path=path, current_time=1001) == password
    with pytest.raises(CommandError):
        save_authorization("other synthetic value", path=path, issued_at=1002)
    assert authorized_password(path=path, current_time=1003) == password


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI platform-specific test")
@pytest.mark.parametrize("current", [999, 4600, 5000])
def test_operator_handoff_rejects_expired_or_future_authorization(tmp_path, current):
    from tools.f7_local import authorized_password, save_authorization

    path = tmp_path / "operator" / "administrator.dpapi"
    save_authorization("synthetic local authorization", path=path, issued_at=1000)
    with pytest.raises(CommandError):
        authorized_password(path=path, current_time=current)


def test_real_f7_additive_migration_and_permissions():
    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit local PG authorization required")
    from sqlalchemy import text

    from tools.f2_local import isolated_database, migration_engine, upgrade

    added = {
        "deployment_instances",
        "configuration_revisions",
        "secret_key_versions",
        "encrypted_secrets",
        "integration_configs",
        "integration_health_checks",
    }
    with isolated_database() as name:
        upgrade(name, "20261125_0005")
        engine = migration_engine(name)
        try:
            with engine.connect() as connection:
                before = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
            upgrade(name, "20261125_0006")
            upgrade(name, "20261125_0006")
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "20261125_0006"
                )
                after = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                assert after - before == added
                for table in added:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                    assert not connection.scalar(
                        text("SELECT has_table_privilege('ocote_runtime',:name,'DELETE,TRUNCATE')"),
                        {"name": table},
                    )
        finally:
            engine.dispose()


@pytest.fixture
def platform_api(api):
    from sqlalchemy import text

    from tools.f2_local import migration_engine

    client, factory = api
    root_ref = "synthetic-root"
    engine = migration_engine(factory.kw["bind"].url.database)
    try:
        with engine.begin() as connection:
            identity = connection.scalar(text("SELECT id FROM deployment_instances"))
    finally:
        engine.dispose()
    client.app.state.vault = Vault(os.urandom(32), identity, root_ref)
    return client, factory


def authenticate(client):
    from test_identity import login_admin

    result = login_admin(client)
    client.headers["authorization"] = "Bearer " + result.json()["access_token"]


def test_real_f7_vault_write_only_rotation_and_append_only(platform_api):
    from sqlalchemy import select, text
    from sqlalchemy.exc import DBAPIError

    from app.models.platform import EncryptedSecret, SecretKeyVersion
    from app.services.platform import encrypted, wrapped

    client, factory = platform_api
    assert client.get("/api/v1/admin/vault").status_code == 401
    authenticate(client)
    owner = uuid4()
    secret = " exact synthetic F7 value "
    path = f"/api/v1/admin/vault/{owner}/backup"
    body = {"expected_version": 0, "reason": "Synthetic vault verification", "value": secret}
    response = client.put(path, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1
    assert secret not in response.text
    assert client.put(path, json=body).status_code == 409
    for forbidden in ("ciphertext", "wrapped_dek", "nonce", "root_key_ref", "value"):
        assert forbidden not in client.get("/api/v1/admin/vault").json()["items"][0]
    assert (
        client.post(
            "/api/v1/admin/vault/rotate",
            json={
                "purpose": "backup",
                "expected_version": 1,
                "reason": "Synthetic key rotation",
            },
        ).status_code
        == 200
    )
    with factory() as db:
        values = list(db.scalars(select(EncryptedSecret).order_by(EncryptedSecret.secret_version)))
        assert len(values) == 2
        for value in values:
            key = db.get(SecretKeyVersion, value.key_id)
            assert client.app.state.vault.decrypt(wrapped(key), encrypted(value)) == secret.encode()
            assert secret.encode() not in value.ciphertext
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE encrypted_secrets SET secret_version=3"))
        db.rollback()
    assert client.get("/api/v1/admin/vault").json()["items"][0]["version"] == 2


def test_real_f7_custody_and_missing_root_fail_closed(platform_api):
    client, _ = platform_api
    authenticate(client)
    health = client.get("/api/v1/admin/health").json()
    assert health["custody"]["custody_complete"] is False
    body = {
        "expected_version": 1,
        "reason": "Synthetic client custody",
        "primary_name": "Synthetic primary",
        "primary_contact": "primary@example.invalid",
        "backup_name": "Synthetic backup",
        "backup_contact": "backup@example.invalid",
    }
    duplicate = {**body, "backup_name": " SYNTHETIC   primary "}
    assert client.patch("/api/v1/admin/custody", json=duplicate).status_code == 422
    response = client.patch("/api/v1/admin/custody", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["custody_complete"] is True
    assert client.patch("/api/v1/admin/custody", json=body).status_code == 409
    del client.app.state.vault
    assert client.get("/api/v1/admin/health").json()["vault_available"] is False
    assert (
        client.put(
            f"/api/v1/admin/vault/{uuid4()}/backup",
            json={
                "expected_version": 0,
                "reason": "Synthetic missing root",
                "value": "synthetic",
            },
        ).status_code
        == 503
    )


def test_real_f7_local_verification_activation_and_invalidation(
    platform_api, tmp_path, monkeypatch
):
    from app.core.evidence import configured_store
    from tools.f1_local import private_directory

    client, factory = platform_api
    authenticate(client)
    for directory in (tmp_path, tmp_path / "objects", tmp_path / "quarantine"):
        private_directory(directory)
    reason = "Synthetic local provider verification"
    base = "/api/v1/admin/integrations/local_storage"
    response = client.put(
        base, json={"config": {"root": str(tmp_path)}, "expected_version": 0, "reason": reason}
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert (
        client.post(
            base + "/activation", json={"is_active": True, "expected_version": 1, "reason": reason}
        ).status_code
        == 409
    )
    tested = client.post(base + "/test", json={"expected_version": 1, "reason": reason})
    assert tested.status_code == 200, tested.text
    assert tested.json()["passed"] is True
    assert not list(tmp_path.glob(".ocote-probe-*"))
    assert (
        client.post(
            base + "/activation", json={"is_active": True, "expected_version": 2, "reason": reason}
        ).status_code
        == 200
    )
    monkeypatch.setenv("EVIDENCE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVIDENCE_CLAMAV_PORT", "3310")
    with factory() as db, pytest.raises(CommandError):
        configured_store(db)
    assert (
        client.put(
            base,
            json={
                "config": {"root": str(tmp_path / "missing")},
                "expected_version": 3,
                "reason": reason,
            },
        ).json()["is_active"]
        is False
    )
    failed = client.post(base + "/test", json={"expected_version": 4, "reason": reason})
    assert failed.json()["passed"] is False
    assert (
        client.post(
            base + "/activation", json={"is_active": True, "expected_version": 5, "reason": reason}
        ).status_code
        == 409
    )


def test_real_f7_clamav_failure_is_persisted_and_never_activated(platform_api, monkeypatch):
    from sqlalchemy import func, select

    from app.models.platform import IntegrationHealthCheck
    from app.services import platform

    client, factory = platform_api
    authenticate(client)

    def unavailable(config):
        raise CommandError(503, "SYNTHETIC_SCANNER_UNAVAILABLE")

    monkeypatch.setattr(platform, "probe_clamav", unavailable)
    base = "/api/v1/admin/integrations/clamav"
    reason = "Synthetic ClamAV failure verification"
    saved = client.put(
        base, json={"config": {"port": 3310, "timeout": 1}, "expected_version": 0, "reason": reason}
    )
    assert saved.status_code == 200, saved.text
    tested = client.post(base + "/test", json={"expected_version": 1, "reason": reason})
    assert tested.json()["passed"] is False
    assert tested.json()["is_active"] is False
    assert (
        client.post(
            base + "/activation", json={"is_active": True, "expected_version": 2, "reason": reason}
        ).status_code
        == 409
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(IntegrationHealthCheck)) == 1
    last = client.get("/api/v1/admin/health").json()["integrations"][0]["last_check"]
    assert last["status"] == "failed"
    assert last["config_version"] == 1


def test_real_f7_database_store_rescans_every_publication(platform_api, tmp_path, monkeypatch):
    from app.core.evidence import ClamAV, configured_store
    from tools.f1_local import private_directory

    client, factory = platform_api
    authenticate(client)
    for directory in (tmp_path, tmp_path / "objects", tmp_path / "quarantine"):
        private_directory(directory)
    calls = []
    offline = False

    def scan(self, content):
        calls.append(content)
        if offline:
            raise CommandError(503, "SYNTHETIC_OFFLINE")
        if b"EICAR-STANDARD" in content:
            raise CommandError(422, "MALWARE_DETECTED")
        return "ClamAV synthetic successful scan"

    monkeypatch.setattr(ClamAV, "__call__", scan)
    reason = "Synthetic DB-only provider activation"
    for kind, config in (
        ("local_storage", {"root": str(tmp_path)}),
        ("clamav", {"port": 3310, "timeout": 1}),
    ):
        base = "/api/v1/admin/integrations/" + kind
        assert (
            client.put(
                base, json={"config": config, "expected_version": 0, "reason": reason}
            ).status_code
            == 200
        )
        assert (
            client.post(base + "/test", json={"expected_version": 1, "reason": reason}).json()[
                "passed"
            ]
            is True
        )
        assert (
            client.post(
                base + "/activation",
                json={"expected_version": 2, "is_active": True, "reason": reason},
            ).status_code
            == 200
        )
    assert len(calls) == 2
    with factory() as db:
        storage = configured_store(db)
        key, digest, _ = storage.publish(b"synthetic evidence bytes")
        assert storage.available(key, 24, digest).read_bytes() == b"synthetic evidence bytes"
        assert len(calls) == 3
        offline = True
        with pytest.raises(CommandError):
            storage.publish(b"synthetic rejected bytes")
        assert len(calls) == 4
        assert not list((tmp_path / "quarantine").iterdir())
        assert len(list((tmp_path / "objects").iterdir())) == 1


@pytest.mark.parametrize("role", ["gerente", "lider", "colaborador"])
def test_real_f7_non_admin_cannot_read_or_change_platform(platform_api, role):
    from sqlalchemy import select

    from app.models.identity import Department, User
    from app.services.identity import touch

    client, factory = platform_api
    authenticate(client)
    with factory.begin() as db:
        user = db.scalar(select(User))
        if role in {"lider", "colaborador"}:
            department = Department(code="synthetic", name="Synthetic F7 department")
            db.add(department)
            db.flush()
            user.department_id = department.id
        user.role = role
        touch(user)
    for path in ("/api/v1/admin/health", "/api/v1/admin/vault"):
        assert client.get(path).status_code == 403
    assert (
        client.put(
            f"/api/v1/admin/vault/{uuid4()}/backup",
            json={
                "expected_version": 0,
                "reason": "Synthetic denied write",
                "value": "synthetic",
            },
        ).status_code
        == 403
    )
