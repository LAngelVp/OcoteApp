import json
import os
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_identity import api as api
from test_identity import tokens as tokens
from test_operations import core as core


@pytest.fixture
def f11_api(core):
    from sqlalchemy import select

    from app.core.vault import Vault
    from app.models.platform import DeploymentInstance

    client, factory, *_rest = core
    with factory() as database:
        instance = database.scalar(select(DeploymentInstance))
        client.app.state.vault = Vault(os.urandom(32), instance.id, instance.root_key_ref)
    return core


def command(**changes):
    return {
        "current_password": "Synthetic-password-123!", "expected_version": 0,
        "reason": "Explicit synthetic UUID-only F11 operation", **changes,
    }


def principal_and_key(client, objective):
    owner = client.get("/api/v1/auth/me").json()["id"]
    response = client.post(
        "/api/v1/integrations/service-principals",
        json=command(
            name="Synthetic F11 service", department_ids=[objective["department_id"]],
            approved_scopes=["tasks:read", "tasks:update_metadata", "notifications:dispatch"],
            is_active=True,
        ),
    )
    assert response.status_code == 201, response.text
    principal = response.json()
    body = command(
        name="Synthetic F11 key", service_principal_id=principal["id"], owner_user_id=owner,
        rate_per_minute=100, scopes=["tasks:read", "tasks:update_metadata"],
        department_ids=[objective["department_id"]], allowed_networks=None,
        expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat(),
    )
    response = client.post("/api/v1/integrations/api-keys", json=body)
    assert response.status_code == 201, response.text
    return principal, response.json(), body


def endpoint(url):
    from urllib.parse import urlsplit

    return {
        "url": url, "host": urlsplit(url).hostname, "approved_addresses": ["93.184.216.34"],
        "allow_private_endpoint": False, "ca_certificates_pem": None,
        "connect_timeout_seconds": 2, "read_timeout_seconds": 3,
        "rate_per_minute": 100, "audience_approved": True,
    }


def connector_body(client, provider):
    credential = "synthetic-f11-private-signing-secret-1234567890"
    if provider == "outgoing_webhook":
        config = {"provider": provider, "endpoint": endpoint("https://receiver.example.invalid/")}
    elif provider == "github":
        config = {
            "provider": provider, "api_endpoint": endpoint("https://api.github.com"),
            "web_origin": "https://github.com",
            "repositories": [{"repository_id": "123", "path": "synthetic/repository"}],
        }
        credential = json.dumps({"access_token": "synthetic-token", "webhook_secret": credential})
    else:
        config = {
            "provider": "oidc", "issuer": "https://idp.example.invalid",
            "client_id": "synthetic-client", "token_auth_method": "none",
            "authorization_endpoint": endpoint("https://idp.example.invalid/authorize"),
            "token_endpoint": endpoint("https://idp.example.invalid/token"),
            "jwks_endpoint": endpoint("https://idp.example.invalid/jwks"),
            "emergency_admin_id": client.get("/api/v1/auth/me").json()["id"],
            "revocation_window_seconds": 300, "jit_enabled": False, "jit_mappings": [],
        }
        credential = None
    return command(
        name="Synthetic F11 " + provider, scope_kind="organization", department_id=None,
        config=config, credential=credential,
    )


def create_connector(client, provider):
    body = connector_body(client, provider)
    response = client.post("/api/v1/integrations/configs", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_real_f11_additive_migration_noop_preservation_and_privileges():
    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit F11 isolated PostgreSQL authorization required")
    from tools import f11_release
    from tools.f2_local import isolated_database, migration_engine, upgrade

    revision = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic/versions/20261126_0010_integrations.py")
    )
    with isolated_database() as name:
        upgrade(name, "20261126_0009")
        engine = migration_engine(name)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO deployment_instances(id,root_key_ref) "
                         "VALUES(:id,'synthetic-f11-preserved-root')"),
                    {"id": uuid4()},
                )
                tables = set(connection.scalars(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                ))
                assert len(tables) == 58
                before = {
                    table: connection.execute(text(
                        f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY to_jsonb(t)::text"
                    )).all()
                    for table in tables - {"alembic_version"}
                }
            upgrade(name, f11_release.HEAD)
            upgrade(name, f11_release.HEAD)
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    f11_release.HEAD
                )
                after = set(connection.scalars(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                ))
                assert len(after) == 67 and after - tables == set(revision["TABLES"])
                for table in revision["TABLES"]:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                for table, rows in before.items():
                    projection = (
                        "to_jsonb(t)-ARRAY['external_identity_id','federated_authenticated_at',"
                        "'federated_revocation_deadline']"
                        if table == "refresh_sessions" else "to_jsonb(t)"
                    )
                    assert connection.execute(text(
                        f"SELECT ({projection})::text FROM {table} t "
                        f"ORDER BY ({projection})::text"
                    )).all() == rows
            f11_release.verify_runtime(name)
        finally:
            engine.dispose()


def test_real_f11_version_audit_and_runtime_protections(f11_api):
    from types import SimpleNamespace

    from app.services.identity import audit

    client, factory, _task, _plan, objective, *_rest = f11_api
    _principal, key, _body = principal_and_key(client, objective)
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    with factory.begin() as database:
        for event in (
            "login_success", "administration_changed", "service_authenticated",
            "federation_started", "federation_verified", "federation_failed", "federation_consumed",
            "external_identity_provisioned", "external_identity_revoked", "external_identity_bound",
            "external_identity_authenticated",
        ):
            audit(database, request, event, entity="f11_synthetic_check", entity_id=uuid4())
    with pytest.raises(DBAPIError), factory.begin() as database:
        audit(database, request, "unknown_f11_event", entity="f11_synthetic_check")
    attempts = [
        "UPDATE api_keys SET name='forbidden'",
        "UPDATE api_keys SET name='forbidden',version=version+1,updated_at=clock_timestamp()",
        "UPDATE api_keys SET revoked_at=clock_timestamp()",
        "UPDATE service_principals SET approved_scopes=ARRAY['admin'],"
        "version=version+1,updated_at=clock_timestamp()",
        "DELETE FROM api_keys",
        "TRUNCATE api_keys CASCADE",
    ]
    for statement in attempts:
        with pytest.raises(DBAPIError), factory.begin() as database:
            database.execute(text(statement))
    response = client.get("/api/v1/integrations/api-keys")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["id"] == key["id"]
    assert key["api_key"] not in response.text
    with factory() as database:
        assert database.scalar(text("SELECT count(*) FROM api_keys")) == 1
        assert database.scalar(text(
            "SELECT count(*) FROM audit_events WHERE entity_type='api_keys'"
        )) >= 1


def test_real_f11_key_rotation_revokes_previous_and_separates_human_access(f11_api):
    client, _factory, task, _plan, objective, *_rest = f11_api
    _principal, key, body = principal_and_key(client, objective)
    old_headers = {"authorization": "Bearer " + key["api_key"]}
    response = client.get("/api/v1/service/tasks", headers=old_headers)
    assert response.status_code == 200, response.text
    assert task["id"] in {row["id"] for row in response.json()["items"]}
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    assert client.get("/api/v1/integrations/api-keys", headers=old_headers).status_code == 401
    path = "/api/v1/integrations/api-keys/" + key["id"]
    expanded = {**body, "expected_version": key["version"], "rate_per_minute": 101}
    assert client.post(path + "/rotate", json=expanded).status_code == 422
    rotated = client.post(
        path + "/rotate",
        json={**body, "expected_version": key["version"], "scopes": ["tasks:read"]},
    )
    assert rotated.status_code == 201, rotated.text
    replacement = rotated.json()
    assert replacement["rotated_from_id"] == key["id"]
    assert client.get("/api/v1/service/tasks", headers=old_headers).status_code == 401
    headers = {"authorization": "Bearer " + replacement["api_key"]}
    assert client.get("/api/v1/service/tasks", headers=headers).status_code == 200
    revoked = client.post(
        "/api/v1/integrations/api-keys/" + replacement["id"] + "/revoke",
        json=command(expected_version=replacement["version"]),
    )
    assert revoked.status_code == 200, revoked.text
    assert client.get("/api/v1/service/tasks", headers=headers).status_code == 401


def test_real_f11_principal_changes_invalidate_bound_key(f11_api):
    client, _factory, _task, _plan, objective, *_rest = f11_api
    principal, key, _body = principal_and_key(client, objective)
    headers = {"authorization": "Bearer " + key["api_key"]}
    assert client.get("/api/v1/service/tasks", headers=headers).status_code == 200
    response = client.patch(
        "/api/v1/integrations/service-principals/" + principal["id"],
        json=command(
            name=principal["name"], department_ids=principal["department_ids"],
            approved_scopes=principal["approved_scopes"], is_active=False,
            expected_version=principal["version"],
        ),
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/service/tasks", headers=headers).status_code in {401, 403}


@pytest.mark.parametrize("provider", ["oidc", "github", "outgoing_webhook"])
def test_real_f11_connector_secrets_versions_and_activation_are_separate(f11_api, provider):
    client, _factory, *_rest = f11_api
    connector, body = create_connector(client, provider)
    path = "/api/v1/integrations/configs/" + connector["id"]
    assert not connector["is_active"]
    assert client.post(
        path + "/activate", json=command(expected_version=connector["version"])
    ).status_code == 409
    credential = body.pop("credential")
    body.update(name="Synthetic F11 renamed " + provider, expected_version=connector["version"])
    response = client.patch(path, json=body)
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["secret_configured"] == (credential is not None)
    assert not edited["is_active"] and edited["tested_at"] is None
    assert client.patch(path, json=body).status_code == 409
    listing = client.get("/api/v1/integrations/configs")
    assert listing.status_code == 200, listing.text
    assert credential is None or credential not in listing.text
    assert "ciphertext" not in listing.text and "secret_id" not in listing.text


def test_real_f11_sso_probe_is_browser_bound_pending_and_cannot_emit_session(f11_api):
    client, factory, *_rest = f11_api
    connector, _body = create_connector(client, "oidc")
    response = client.post(
        "/api/v1/integrations/configs/" + connector["id"] + "/test",
        json=command(
            expected_version=connector["version"], confirmed=True, revocation_confirmed=True,
            test_username=None, test_password=None, emergency_password="Synthetic-password-123!",
        ),
    )
    assert response.status_code == 200, response.text
    transaction = response.json()
    assert transaction["authorization_url"].startswith("https://idp.example.invalid/authorize?")
    assert "access_token" not in response.text and "csrf_token" not in response.text
    cookie = response.headers["set-cookie"]
    assert all(value in cookie for value in ("HttpOnly", "Secure", "SameSite=strict"))
    assert client.post(
        "/api/v1/auth/sso/finish", json={"transaction_id": transaction["transaction_id"]}
    ).status_code == 401
    with factory() as database:
        row = database.execute(text(
            "SELECT purpose,state,issuer,context_secret_id FROM sso_transactions WHERE id=:id"
        ), {"id": transaction["transaction_id"]}).one()
        assert row[0:3] == ("probe", "pending", None) and row[3] is not None
    with pytest.raises(DBAPIError), factory.begin() as database:
        database.execute(text(
            "UPDATE sso_transactions SET state='consumed',consumed_at=clock_timestamp(),"
            "version=version+1,updated_at=clock_timestamp()"
        ))


def test_real_f11_webhook_delivery_attempt_and_linked_replay(f11_api):
    from types import SimpleNamespace
    from uuid import UUID

    from app.core.integration_security import webhook_signature
    from app.services.webhook_worker import tick

    client, factory, _task, _plan, objective, person, *_rest = f11_api
    principal, _key, _key_body = principal_and_key(client, objective)
    connector, body = create_connector(client, "outgoing_webhook")
    calls = []

    def transport(_network, _host, _port, method, _target, headers, content, _limit, **_options):
        assert method == "POST"
        assert headers["x-ocote-signature"] == webhook_signature(
            body["credential"].encode(), int(headers["x-ocote-timestamp"]), content
        )
        with factory() as database:
            assert database.scalar(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND usename=current_user AND state='idle in transaction'"
            )) == 0
        calls.append(content)
        return 202, {}, b"ok"

    client.app.state.integration_transport = transport
    path = "/api/v1/integrations/configs/" + connector["id"]
    tested = client.post(path + "/test", json=command(
        expected_version=connector["version"], confirmed=True, revocation_confirmed=None,
        test_username=None, test_password=None, emergency_password=None,
    ))
    assert tested.status_code == 200 and tested.json()["passed"], tested.text
    assert not tested.json()["is_active"]
    activated = client.post(
        path + "/activate", json=command(expected_version=tested.json()["version"])
    )
    assert activated.status_code == 200 and activated.json()["is_active"], activated.text
    owner = client.get("/api/v1/auth/me").json()["id"]
    response = client.post("/api/v1/integrations/webhook-subscriptions", json=command(
        integration_id=connector["id"], owner_user_id=owner, event_types=["assignment"],
        department_ids=[objective["department_id"]], max_attempts=3,
        retry_base_seconds=5, max_delay_seconds=300, enabled=True,
    ))
    assert response.status_code == 201, response.text
    subscription = response.json()
    created = client.post("/api/v1/tasks", json={
        "objective_id": objective["id"], "assignee_id": person["id"],
        "title": "Synthetic F11 assignment after webhook subscription",
        "start_date": "2027-12-10", "due_date": "2028-02-20",
    })
    assert created.status_code == 201, created.text
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())), app=client.app)
    report = tick(factory, UUID(principal["id"]), 1, request=request, transport=transport)
    assert report["queued"] == 1 and report["accepted"] == 1, report
    response = client.get("/api/v1/integrations/webhook-deliveries")
    assert response.status_code == 200, response.text
    delivery = response.json()["items"][0]
    assert delivery["state"] == "delivered" and "body" not in delivery
    attempts = client.get("/api/v1/integrations/webhook-deliveries/" + delivery["id"] + "/attempts")
    assert attempts.status_code == 200, attempts.text
    assert json.loads(calls[-1])["resource"]["id"] == created.json()["id"]
    attempt = attempts.json()["items"][0]
    assert attempt["outcome"] == "accepted" and "lease_token" not in attempt
    replay_path = "/api/v1/integrations/webhook-subscriptions/" + subscription["id"] + "/replay"
    replay_body = command(
        delivery_id=delivery["id"], expected_version=delivery["version"],
        idempotency_key=str(uuid4()),
    )
    replayed = client.post(replay_path, json=replay_body)
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["retry_of_id"] == delivery["id"]
    assert client.post(replay_path, json=replay_body).json()["id"] == replayed.json()["id"]
    with pytest.raises(DBAPIError), factory.begin() as database:
        database.execute(text("UPDATE webhook_attempts SET latency_ms=0"))
    assert len(calls) == 2