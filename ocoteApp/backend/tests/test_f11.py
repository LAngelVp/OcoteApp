import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.errors import CommandError
from app.core.federation import correlated, ldap_user_filter, oidc_identity, saml_identity


def test_f11_migration_preserves_audit_contract_and_adds_federation_and_service_events(monkeypatch):
    import runpy
    from pathlib import Path

    from alembic import op

    statements = []
    monkeypatch.setattr(op, "execute", lambda statement: statements.append(str(statement)))
    migration = runpy.run_path(str(
        Path(__file__).parents[1] / "alembic/versions/20261126_0010_integrations.py"
    ))
    migration["upgrade"]()
    audit_sql = next(statement for statement in statements
                     if "ADD CONSTRAINT audit_events_event_type_check" in statement)
    assert "pg_get_expr(conbin,conrelid) INTO STRICT previous_expression" in audit_sql
    assert "conrelid='public.audit_events'::regclass" in audit_sql
    assert "CHECK((%s) OR event_type IN" in audit_sql
    assert "))', previous_expression)" in audit_sql
    for event in (
        "service_authenticated", "federation_started", "federation_verified",
        "federation_failed", "federation_consumed", "external_identity_provisioned",
        "external_identity_revoked", "external_identity_bound", "external_identity_authenticated",
    ):
        assert "''" + event + "''" in audit_sql


def synthetic_endpoint(**changes):
    return {
        "url": "https://idp.example.invalid/endpoint",
        "host": "idp.example.invalid",
        "approved_addresses": ["8.8.8.8"],
        "connect_timeout_seconds": 2,
        "read_timeout_seconds": 3,
        "rate_per_minute": 10,
        "audience_approved": False,
        "allow_private_endpoint": False,
        "ca_certificates_pem": None,
        **changes,
    }


def synthetic_devops(provider):
    host = "api.github.com" if provider == "github" else "gitlab.example.invalid"
    return {
        "provider": provider,
        "api_endpoint": synthetic_endpoint(
            host=host, url="https://" + host, audience_approved=True
        ),
        "web_origin": "https://github.com" if provider == "github" else "https://" + host,
        "repositories": [{"repository_id": "123", "path": "synthetic/repository"}],
    }


def test_f11_public_sso_discovery_is_empty_when_disabled_and_only_exposes_minimal_metadata(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import federation

    database = MagicMock()
    monkeypatch.setattr(federation, "enabled", lambda *arguments: False)
    assert federation.providers(database, 5) == {"items": [], "next_cursor": None}
    database.scalars.assert_not_called()
    monkeypatch.setattr(federation, "enabled", lambda *arguments: True)
    monkeypatch.setattr(federation, "require_page_size", lambda *arguments: None)
    record = SimpleNamespace(id=uuid4(), name="Synthetic OIDC", provider="oidc",
                              config={"private": True}, secret_id=uuid4())
    database.scalars.return_value = [record]
    result = federation.providers(database, 5)
    assert result["items"] == [{"id": record.id, "name": record.name, "provider": "oidc"}]
    parameters = database.scalars.call_args.args[0].compile().params
    assert "sso" in parameters.values() and 6 in parameters.values()


def test_f11_sso_completion_needs_browser_proof_and_federated_sessions_expire_or_revoke(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.identity import User
    from app.models.integrations import ExternalIdentity
    from app.models.platform import IntegrationConfig
    from app.services import federation

    moment = datetime.now(UTC)
    browser = "b" * 43
    transaction = SimpleNamespace(
        state="verified",
        expires_at=moment + timedelta(minutes=5),
        consumed_at=None,
        browser_hash=federation.fingerprint(browser),
    )
    federation.completion_allowed(transaction, browser, moment)
    with pytest.raises(CommandError):
        federation.completion_allowed(transaction, "a" * 43, moment)
    transaction.state = "consumed"
    with pytest.raises(CommandError):
        federation.completion_allowed(transaction, browser, moment)
    database = MagicMock()
    federation.session_allowed(database, SimpleNamespace(external_identity_id=None))
    database.get.assert_not_called()
    user = SimpleNamespace(id=uuid4(), is_active=True, department_id=uuid4())
    provider = SimpleNamespace(
        id=uuid4(),
        kind="sso",
        is_active=True,
        scope_kind="department",
        department_id=user.department_id,
        config={},
    )
    link = SimpleNamespace(id=uuid4(), user_id=user.id, integration_id=provider.id, revoked_at=None)
    records = {
        (User, user.id): user,
        (IntegrationConfig, provider.id): provider,
        (ExternalIdentity, link.id): link,
    }
    database.get.side_effect = lambda model, identity: records.get((model, identity))
    monkeypatch.setattr(federation, "sso_modules", lambda db: None)
    monkeypatch.setattr(
        federation.integrations,
        "CONFIG",
        SimpleNamespace(
            validate_python=lambda value: SimpleNamespace(revocation_window_seconds=300)
        ),
    )
    session = SimpleNamespace(
        external_identity_id=link.id,
        user_id=user.id,
        federated_authenticated_at=moment,
        federated_revocation_deadline=moment + timedelta(minutes=5),
    )
    federation.session_allowed(database, session)
    link.revoked_at = moment
    with pytest.raises(CommandError) as caught:
        federation.session_allowed(database, session)
    assert caught.value.code == "FEDERATED_SESSION_REVOKED"
    link.revoked_at, provider.is_active = None, False
    with pytest.raises(CommandError):
        federation.session_allowed(database, session)
    provider.is_active = True
    session.federated_revocation_deadline = moment - timedelta(seconds=1)
    with pytest.raises(CommandError) as caught:
        federation.session_allowed(database, session)
    assert caught.value.code == "FEDERATED_SESSION_EXPIRED"


def test_f11_task_provider_discovery_scopes_before_limit_and_never_exposes_configuration(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import devops

    objective = SimpleNamespace(department_id=uuid4())
    monkeypatch.setattr(devops, "task_context", lambda *arguments: (None, None, objective))
    monkeypatch.setattr(devops, "require_page_size", lambda *arguments: None)
    record = SimpleNamespace(id=uuid4(), name="Synthetic GitHub", provider="github",
                             config={"repositories": [{"repository_id": "123", "path": "a/b"}],
                                     "api_endpoint": {"private": True}})
    database = MagicMock()
    database.scalars.return_value = [record]
    result = devops.providers(database, None, uuid4(), 5)
    assert set(result["items"][0]) == {"id", "name", "provider", "repositories"}
    query = database.scalars.call_args.args[0]
    assert objective.department_id in query.compile().params.values()
    assert "WHERE" in str(query).upper() and "LIMIT" in str(query).upper()


def test_f11_admin_inbox_is_connector_scoped_and_excludes_body_and_authentication(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import devops

    integration_id = uuid4()
    monkeypatch.setattr(devops.integrations, "administrator", lambda *arguments: None)
    monkeypatch.setattr(devops.integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(devops, "require_page_size", lambda *arguments: None)
    monkeypatch.setattr(devops.integrations, "connector_for", lambda *arguments:
                        SimpleNamespace(id=integration_id, kind="devops"))
    record = SimpleNamespace(id=uuid4(), created_at=datetime.now(UTC),
                             integration_id=integration_id, delivery_id="synthetic-delivery",
                             event_type="push", request_id=uuid4(), body_hash="private",
                             safe_projection={"private": True})
    database = MagicMock()
    database.scalars.return_value = [record]
    result = devops.inbox(database, None, integration_id, 5)
    assert set(result["items"][0]) == {
        "id", "created_at", "integration_id", "delivery_id", "event_type", "request_id"
    }
    assert integration_id in database.scalars.call_args.args[0].compile().params.values()


def test_f11_webhook_attempt_projection_never_exposes_lease_tokens():
    from types import SimpleNamespace

    from app.services.outgoing_webhooks import attempt_view

    record = SimpleNamespace(**dict.fromkeys((
        "id", "created_at", "delivery_id", "attempt_no", "signed_at", "outcome",
        "status_code", "result_code", "latency_ms", "lease_token",
    ), "synthetic"))
    assert set(attempt_view(record)) == set(vars(record)) - {"lease_token"}


def test_f11_browser_completion_metadata_never_leaks_identity_and_finish_checks_purpose(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import federation

    moment, browser = datetime.now(UTC), "b" * 43
    transaction = SimpleNamespace(id=uuid4(), integration_id=uuid4(), config_revision=2,
                                   state="verified", purpose="probe", consumed_at=None,
                                   expires_at=moment + timedelta(minutes=5),
                                   browser_hash=federation.fingerprint(browser),
                                   issuer="private-issuer", subject="private-subject")
    record = SimpleNamespace(config_revision=2, name="Synthetic OIDC")
    database = MagicMock()
    database.get.return_value = transaction
    monkeypatch.setattr(federation.identity, "origin", lambda *arguments: None)
    monkeypatch.setattr(federation, "sso_modules", lambda *arguments: None)
    monkeypatch.setattr(federation, "configured", lambda *args, **kwargs: record)
    result = federation.completion_status(database, None, None, transaction.id, browser)
    assert set(result) == {"transaction_id", "purpose", "provider_name", "expires_at"}
    assert result["purpose"] == "probe"
    with pytest.raises(CommandError):
        federation.completion_status(database, None, None, transaction.id, "c" * 43)
    with pytest.raises(CommandError) as caught:
        federation.finish(database, None, None, transaction.id, browser, purpose="login")
    assert caught.value.code == "SSO_PURPOSE_MISMATCH"
    database.scalar.assert_not_called()


def test_f11_sso_verified_transaction_is_one_use_and_carries_only_stable_identity():
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.core.federation import FederatedIdentity
    from app.services.federation import fingerprint, verified

    transaction = SimpleNamespace(
        id=uuid4(),
        integration_id=uuid4(),
        state="pending",
        version=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        initiating_user_id=None,
        __tablename__="sso_transactions",
    )
    identity = FederatedIdentity(
        "https://idp.example.invalid",
        "synthetic-stable-subject",
        "unlinked@example.invalid",
        "Untrusted role claim",
    )
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    verified(database, transaction, identity, request)
    assert transaction.state == "verified" and transaction.version == 2
    assert transaction.issuer == identity.issuer and transaction.subject == identity.subject
    assert not hasattr(transaction, "email") and not hasattr(transaction, "role")
    with pytest.raises(CommandError):
        verified(database, transaction, identity, request)
    assert fingerprint("s" * 43) != fingerprint("b" * 43)
    for value in (None, "short", "non-ascii-" + "\u00e1" * 43):
        with pytest.raises(CommandError):
            fingerprint(value)


def test_f11_jit_config_requires_explicit_profile_sources_and_verified_oidc_email():
    from urllib.parse import parse_qs, urlsplit
    from uuid import uuid4

    from pydantic import ValidationError

    from app.core.integration_http import oidc_authorization
    from app.schemas.integrations import OIDCConfig

    values = {
        "provider": "oidc",
        "emergency_admin_id": uuid4(),
        "revocation_window_seconds": 300,
        "jit_enabled": True,
        "jit_mappings": [
            {
                "attribute": "groups",
                "value": "synthetic",
                "role": "colaborador",
                "department_id": uuid4(),
            }
        ],
        "issuer": "https://idp.example.invalid",
        "client_id": "synthetic-client",
        "authorization_endpoint": synthetic_endpoint(),
        "token_endpoint": synthetic_endpoint(),
        "jwks_endpoint": synthetic_endpoint(),
        "token_auth_method": "client_secret_basic",
    }
    with pytest.raises(ValidationError):
        OIDCConfig.model_validate(values)
    values.update(jit_email_attribute="email", jit_name_attribute="name")
    assert OIDCConfig.model_validate(values).attribute_names == ("email", "groups", "name")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_endpoint"):
        values[field]["audience_approved"] = True
    url = oidc_authorization(OIDCConfig.model_validate(values),
                             redirect_uri="https://localhost:8443/callback", state="s" * 43,
                             nonce="n" * 43, verifier="v" * 43)
    assert parse_qs(urlsplit(url).query)["scope"] == ["openid profile email"]
    with pytest.raises(ValidationError):
        OIDCConfig.model_validate({**values, "jit_email_attribute": "unverified-mail"})


def test_f11_jit_profile_is_minimal_verified_and_uses_separate_aad_version(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.core.federation import FederatedIdentity
    from app.services import federation

    mapping = SimpleNamespace(
        attribute="groups", value="synthetic", role="colaborador", department_id=uuid4()
    )
    config = SimpleNamespace(
        provider="oidc",
        jit_enabled=True,
        jit_mappings=[mapping],
        attribute_names=("email", "groups", "name"),
        jit_email_attribute="email",
        jit_name_attribute="name",
    )
    result = FederatedIdentity(
        "https://idp.example.invalid",
        "stable-subject",
        "synthetic@example.invalid",
        "Synthetic user",
        verified_attributes=(
            ("email", ("synthetic@example.invalid",)),
            ("groups", ("synthetic",)),
            ("name", ("Synthetic user",)),
        ),
    )
    profile = federation.jit_profile(config, result)
    assert set(profile) == {"email", "display_name", "attributes"}
    assert profile["email"] == result.verified_email
    assert "role" not in profile and "department_id" not in profile
    database, request, crypt = MagicMock(), MagicMock(), MagicMock()
    key, owner = object(), uuid4()
    database.scalar.return_value = key
    encrypted = SimpleNamespace(key_id=uuid4(), nonce=b"n" * 12, ciphertext=b"ciphertext-only")
    crypt.encrypt.return_value = encrypted
    monkeypatch.setattr(federation.platform, "vault", lambda *arguments: crypt)
    monkeypatch.setattr(federation.platform, "wrapped", lambda value: value)
    federation.encrypt_context(database, owner, {"profile": profile}, request, secret_version=2)
    assert crypt.encrypt.call_args.args[1:3] == (owner, 2)
    secret = database.add.call_args.args[0]
    assert secret.secret_version == 2 and secret.ciphertext == b"ciphertext-only"
    from dataclasses import replace

    with pytest.raises(CommandError):
        federation.jit_profile(config, replace(result, verified_email=None))
    config.jit_enabled = False
    assert federation.jit_profile(config, result) is None


@pytest.mark.parametrize("mode", ["created", "existing", "unproved"])
def test_f11_jit_creation_requires_proof_and_never_links_existing_email(monkeypatch, mode):
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.identity import User
    from app.models.integrations import ExternalIdentity
    from app.services import federation

    moment, department = datetime.now(UTC), uuid4()
    emergency = SimpleNamespace(id=uuid4(), is_active=True, role="admin", token_version=1)
    config = SimpleNamespace(
        jit_enabled=True,
        emergency_admin_id=emergency.id,
        provider="oidc",
        jit_email_attribute="email",
        jit_name_attribute="name",
        attribute_names=("email", "groups", "name"),
        jit_mappings=[
            SimpleNamespace(
                attribute="groups", value="synthetic", role="colaborador", department_id=department
            )
        ],
        model_dump=lambda **kwargs: {"jit": True, "department": str(department)},
    )
    record = SimpleNamespace(
        id=uuid4(),
        config_revision=1,
        tested_version=1,
        tested_at=moment,
        scope_kind="department",
        department_id=department,
    )
    transaction = SimpleNamespace(
        id=uuid4(), issuer="https://idp.example.invalid", subject="stable-synthetic-id"
    )
    attributes = {
        "email": ["synthetic@example.invalid"],
        "groups": ["synthetic"],
        "name": ["Synthetic user"],
    }
    envelope = {
        "profile": {
            "email": "synthetic@example.invalid",
            "display_name": "Synthetic user",
            "attributes": attributes,
        }
    }
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.get.return_value = emergency
    database.scalar.side_effect = [
        None if mode == "unproved" else uuid4(),
        SimpleNamespace(id=uuid4()),
        uuid4() if mode == "existing" else None,
    ]
    monkeypatch.setattr(
        federation.integrations, "decrypted_secret", lambda *arguments: json.dumps(envelope)
    )
    monkeypatch.setattr(federation, "department_for_user", lambda *arguments: department)
    monkeypatch.setattr(
        federation.identity,
        "PASSWORDS",
        SimpleNamespace(hash=lambda value: "synthetic-nonrecoverable-hash"),
    )
    if mode == "created":
        link = federation.jit_user(database, record, config, transaction, request)
        assert isinstance(link, ExternalIdentity) and link.integration_id == record.id
        users = [
            call.args[0] for call in database.add.call_args_list if isinstance(call.args[0], User)
        ]
        assert len(users) == 1 and users[0].role == "colaborador"
        assert users[0].department_id == department and link.user_id == users[0].id
        assert users[0].password_hash == "synthetic-nonrecoverable-hash"
    else:
        with pytest.raises(CommandError) as caught:
            federation.jit_user(database, record, config, transaction, request)
        assert caught.value.code == (
            "SSO_JIT_PROOF_REQUIRED"
            if mode == "unproved"
            else "SSO_JIT_EXISTING_ACCOUNT_REQUIRES_BINDING"
        )
        assert not any(isinstance(call.args[0], User) for call in database.add.call_args_list)
    assert len(federation.sso_proof_code(record, config, emergency)) <= 80


@pytest.mark.parametrize("mode", ["passed", "denied", "missing", "changed"])
def test_f11_probe_start_callback_finish_is_inactive_sessionless_and_race_checked(
    monkeypatch, mode,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, create_autospec
    from uuid import uuid4

    from app.core.federation import FederatedIdentity
    from app.models.identity import RefreshSession, User
    from app.models.integrations import SSOTransaction
    from app.models.platform import IntegrationHealthCheck
    from app.schemas.integrations import ConnectorTest, OIDCConfig
    from app.services import federation

    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True, token_version=1)
    emergency = SimpleNamespace(id=uuid4(), role="admin", is_active=True, token_version=2)
    endpoint = synthetic_endpoint(audience_approved=True)
    config = OIDCConfig(
        provider="oidc", issuer="https://idp.example.invalid", client_id="synthetic-client",
        token_auth_method="client_secret_basic", authorization_endpoint=endpoint,
        token_endpoint=endpoint, jwks_endpoint=endpoint, emergency_admin_id=emergency.id,
        revocation_window_seconds=300, jit_enabled=False, jit_mappings=[],
    )
    record = SimpleNamespace(id=uuid4(), version=1, config_revision=2,
                             tested_version=2, tested_at=datetime.now(UTC), is_active=True,
                             kind="sso", config=config.model_dump(mode="json"))
    body = ConnectorTest(
        expected_version=1, current_password="synthetic-admin", confirmed=True,
        reason="Synthetic approved probe", revocation_confirmed=True,
        test_username=None, test_password=None, emergency_password="synthetic-emergency",
    )
    database, request = MagicMock(), MagicMock()
    database.scalar.return_value = 0
    database.get.return_value = emergency
    request.state.request_id = str(uuid4())
    tokens = SimpleNamespace(settings=SimpleNamespace(auth_origin="https://localhost:8443"))
    contexts, authentications = {}, []

    def encrypt(db, owner, context, incoming, *, secret_version=1):
        contexts[owner] = context
        return uuid4()

    def reauthenticate(db, user, command, incoming):
        authentications.append((user.id, command.current_password.get_secret_value()))

    monkeypatch.setattr(federation.identity, "origin", lambda *arguments: None)
    monkeypatch.setattr(federation.identity, "config_lock", lambda *arguments: None)
    monkeypatch.setattr(federation, "reauthenticate", reauthenticate)
    monkeypatch.setattr(federation, "sso_modules", lambda *arguments: None)
    monkeypatch.setattr(federation.integrations, "connector_for", lambda *args, **kwargs: record)
    monkeypatch.setattr(
        federation.integrations, "connector_material", lambda *args: (config, "key")
    )
    monkeypatch.setattr(federation.platform, "revision", lambda *arguments: uuid4())
    monkeypatch.setattr(federation, "encrypt_context", encrypt)
    monkeypatch.setattr(federation, "decrypt_context", lambda db, value, req: contexts[value.id])
    monkeypatch.setattr(federation.integrations, "connector_view", lambda entry: {
        "is_active": entry.is_active, "tested_version": entry.tested_version
    })
    result, browser = federation.start_probe(database, tokens, request, record.id, body, actor)
    assert authentications == [(actor.id, "synthetic-admin"),
                               (emergency.id, "synthetic-emergency")]
    assert not record.is_active and record.tested_version is None
    transactions = [call.args[0] for call in database.add.call_args_list
                    if isinstance(call.args[0], SSOTransaction)]
    assert len(transactions) == 1 and transactions[0].purpose == "probe"
    transaction = transactions[0]
    assert transaction.initiating_user_id == actor.id
    database.scalar.return_value = transaction
    database.get.side_effect = lambda model, key, **kwargs: (
        emergency if model is User else None if mode == "missing" else transaction
    )

    def exchange(*args, **kwargs):
        database.commit.assert_called_once()
        if mode == "denied":
            raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
        if mode == "changed":
            record.config_revision += 1
        return FederatedIdentity(config.issuer, "synthetic-subject", None, None)

    exchange_mock = create_autospec(federation.oidc_exchange, side_effect=exchange)
    monkeypatch.setattr(federation, "oidc_exchange", exchange_mock)
    if mode == "passed":
        assert federation.callback(database, tokens, request, record.id, "s" * 43,
                                   code="synthetic-code") == transaction.id
        assert transaction.state == "verified"
        database.scalar.return_value = None
        refresh, result = federation.finish(
            database, tokens, request, transaction.id, browser, actor
        )
        assert refresh is None and result["passed"] and not result["is_active"]
        assert transaction.state == "consumed" and record.tested_version == 2
    else:
        with pytest.raises(CommandError) as caught:
            federation.callback(database, tokens, request, record.id, "s" * 43,
                                code="synthetic-code")
        assert caught.value.status == 401
        assert transaction.state == ("failed" if mode == "denied" else "pending")
        assert record.tested_version is None
    checks = [call.args[0] for call in database.add.call_args_list
              if isinstance(call.args[0], IntegrationHealthCheck)]
    assert len(checks) == (1 if mode in {"passed", "denied"} else 0)
    if mode == "denied":
        assert checks[0].status == "failed" and checks[0].result_code == "F11_SSO_PROBE_FAILED"
    assert not any(isinstance(call.args[0], (User, RefreshSession))
                   for call in database.add.call_args_list)
    assert not record.is_active
    exchange_mock.assert_called_once()


@pytest.mark.parametrize("mode", ["passed", "actor_changed", "emergency_changed"])
def test_f11_sso_probe_is_revision_and_emergency_bound_and_never_activates(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.identity import RefreshSession, User
    from app.models.platform import IntegrationHealthCheck
    from app.services import federation

    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True, token_version=1)
    emergency = SimpleNamespace(id=uuid4(), role="admin", is_active=True, token_version=3)
    record = SimpleNamespace(id=uuid4(), version=1, config_revision=2,
                             tested_version=None, tested_at=None, is_active=False)
    config = SimpleNamespace(emergency_admin_id=emergency.id, jit_enabled=False,
                             model_dump=lambda **kwargs: {"revocation_window_seconds": 300})
    transaction = SimpleNamespace(initiating_user_id=actor.id)
    proof = {"proof_code": federation.sso_proof_code(record, config, emergency),
             "actor_version": actor.token_version, "reason": "Synthetic SSO test accepted"}
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.get.return_value = emergency
    monkeypatch.setattr(federation, "decrypt_context", lambda *arguments: {"probe": proof})
    monkeypatch.setattr(federation.platform, "revision", lambda *arguments: uuid4())
    monkeypatch.setattr(federation.integrations, "connector_view", lambda entry: {
        "id": entry.id, "is_active": entry.is_active, "tested_version": entry.tested_version
    })
    if mode == "actor_changed":
        actor.token_version += 1
    if mode == "emergency_changed":
        emergency.token_version += 1
    if mode == "passed":
        result = federation.probe_finished(database, None, request, record, config,
                                            transaction, actor)
        assert result["passed"] and not result["is_active"] and record.tested_version == 2
        checks = [call.args[0] for call in database.add.call_args_list
                  if isinstance(call.args[0], IntegrationHealthCheck)]
        assert len(checks) == 1 and checks[0].result_code == proof["proof_code"]
        assert not any(isinstance(call.args[0], (User, RefreshSession))
                       for call in database.add.call_args_list)
    else:
        with pytest.raises(CommandError) as caught:
            federation.probe_finished(database, None, request, record, config, transaction, actor)
        assert caught.value.code == "SSO_PROBE_CONTEXT_CHANGED"
        assert record.tested_version is None and not record.is_active
        database.add.assert_not_called()


@pytest.mark.parametrize("mode", ["claimed", "rate", "scope", "expired"])
def test_f11_webhook_claim_serializes_rate_and_cancels_invalid_current_scope(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.collaboration import OutboxEvent
    from app.models.identity import User
    from app.models.integrations import WebhookSubscription
    from app.services import webhook_worker as worker

    moment, department = datetime.now(UTC), uuid4()
    principal = SimpleNamespace(id=uuid4(), department_ids=[department])
    owner = SimpleNamespace(id=uuid4(), role="lider", department_id=department, is_active=True)
    config = SimpleNamespace(id=uuid4(), config_revision=3, secret_id=uuid4())
    subscription = SimpleNamespace(id=uuid4(), version=2, owner_user_id=owner.id,
                                    integration_id=config.id, enabled=True,
                                    department_ids=[department], event_types=["assignment"])
    event = SimpleNamespace(id=uuid4(), event_id=uuid4(), department_id=department,
                             event_type="assignment")
    record = SimpleNamespace(id=uuid4(), version=1, subscription_id=subscription.id,
                             subscription_version=2, outbox_id=event.id,
                             config_revision=3, signing_secret_id=config.secret_id,
                             state="pending", attempt_count=0, max_attempts=3,
                             retry_base_seconds=5, max_delay_seconds=300,
                             body=b'{"synthetic":true}', next_attempt_at=moment,
                             lease_token=None, lease_until=None)
    if mode == "expired":
        record.state, record.attempt_count = "sending", 1
        record.lease_token, record.lease_until = uuid4(), moment - timedelta(seconds=1)
        record.updated_at = moment - timedelta(seconds=91)
    database, request = MagicMock(), MagicMock()
    database.scalar.side_effect = [record, event.id, 2 if mode == "rate" else 0, 0]
    records = {WebhookSubscription: subscription, OutboxEvent: event, User: owner}
    database.get.side_effect = lambda model, key, **kwargs: records[model]
    endpoint = SimpleNamespace(audience_approved=True, rate_per_minute=2)
    monkeypatch.setattr(worker, "ready", lambda *arguments: True)
    monkeypatch.setattr(worker, "changed", lambda *arguments: None)
    monkeypatch.setattr(worker.outgoing_webhooks, "configuration", lambda *args, **kwargs: config)
    monkeypatch.setattr(worker.outgoing_webhooks, "department_scope", lambda *arguments: None)
    lock = MagicMock(return_value=config)
    monkeypatch.setattr(worker.integrations, "connector_for", lock)
    monkeypatch.setattr(worker.integrations, "connector_material", lambda *args: (
        SimpleNamespace(endpoint=endpoint), "s" * 43
    ))
    if mode == "scope":
        subscription.event_types = ["overdue"]
    result = worker.claim(database, principal, request)
    if mode == "claimed":
        assert result["body"] == record.body and result["event_id"] == event.event_id
        assert record.state == "sending" and record.attempt_count == 1
        assert record.lease_until > moment and result["credential"] == "s" * 43
        lock.assert_called_once_with(database, config.id, lock=True)
    elif mode == "rate":
        assert result is None and record.state == "pending" and record.attempt_count == 0
        lock.assert_called_once_with(database, config.id, lock=True)
    elif mode == "scope":
        assert result == {"cancelled": True} and record.state == "cancelled"
        assert record.attempt_count == 0
    else:
        assert result == {"recovered": True} and record.state == "pending"
        assert record.attempt_count == 1
        assert database.add.call_args.args[0].result_code == "LEASE_EXPIRED"


@pytest.mark.parametrize("status,state,result", [
    (204, "delivered", "accepted"), (302, "dead_letter", "rejected"),
    (400, "dead_letter", "rejected"), (408, "pending", "retryable"),
    (429, "pending", "retryable"), (503, "pending", "retryable"),
    (None, "pending", "ambiguous"),
])
def test_f11_webhook_attempts_are_immutable_fenced_and_retry_only_transient(
    monkeypatch, status, state, result,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.integrations import WebhookAttempt
    from app.services import webhook_worker as worker

    moment = datetime.now(UTC)
    record = SimpleNamespace(id=uuid4(), version=2, state="sending", attempt_count=1,
                             max_attempts=3, retry_base_seconds=5, max_delay_seconds=300,
                             lease_token=uuid4(), lease_until=moment + timedelta(seconds=90))
    prepared = {"attempt_id": uuid4(), "lease_token": record.lease_token, "signed_at": moment}
    database, request = MagicMock(), MagicMock()
    principal = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(worker, "changed", lambda *arguments: None)
    actual = worker.complete(database, principal, request, record, prepared, status,
                              {"retry-after": "60"}, 12)
    assert actual == result and record.state == state and record.version == 3
    assert record.lease_token is None and record.lease_until is None
    attempt = database.add.call_args.args[0]
    assert isinstance(attempt, WebhookAttempt) and attempt.outcome == result
    assert attempt.status_code == status and attempt.id == prepared["attempt_id"]
    if state == "pending":
        assert moment + timedelta(seconds=60) <= record.next_attempt_at
    database.add.reset_mock()
    assert worker.complete(database, principal, request, record, prepared, 204, {}, 0) == "fenced"
    database.add.assert_not_called()


def test_f11_webhook_expired_lease_is_ambiguous_and_final_budget_is_terminal(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import webhook_worker as worker

    moment = datetime.now(UTC)
    record = SimpleNamespace(id=uuid4(), version=2, state="sending", attempt_count=3,
                             max_attempts=3, retry_base_seconds=5, max_delay_seconds=300,
                             lease_token=uuid4(), lease_until=moment - timedelta(seconds=1))
    prepared = {"attempt_id": uuid4(), "lease_token": record.lease_token,
                "signed_at": moment - timedelta(seconds=91)}
    database = MagicMock()
    monkeypatch.setattr(worker, "changed", lambda *arguments: None)
    result = worker.complete(database, None, None, record, prepared, 200, {}, 15)
    assert result == "ambiguous" and record.state == "dead_letter"
    attempt = database.add.call_args.args[0]
    assert attempt.result_code == "LEASE_EXPIRED" and attempt.status_code is None
    assert attempt.signed_at == prepared["signed_at"]
    for hint in ("invalid", "9999999999999999999999999999999999", "Thu, 01 Jan 1970 00:00:00 GMT"):
        at = worker.retry_delay(moment, 10, 300, 300, hint)
        assert moment < at <= moment + timedelta(seconds=300)


def test_f11_webhook_tick_commits_before_signed_network_and_refuses_origin0009(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import webhook_worker as worker

    database, factory, request = MagicMock(), MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.scalar.side_effect = ["ocote_runtime", "20261126_0009"]
    monkeypatch.setattr(worker, "config_lock", lambda *args, **kwargs: None)
    with pytest.raises(CommandError) as caught:
        worker.context(database, uuid4())
    assert caught.value.code == "F11_REVISION_REQUIRED"
    database.scalar.side_effect = None
    database.scalars.return_value = []
    moment, state = datetime.now(UTC), {"open": False}
    principal = SimpleNamespace(id=uuid4(), department_ids=[uuid4()])
    record = SimpleNamespace(id=uuid4(), version=2, state="sending", attempt_count=1,
                             max_attempts=3, retry_base_seconds=5, max_delay_seconds=300,
                             lease_token=uuid4(), lease_until=moment + timedelta(seconds=90))
    prepared = {"id": record.id, "attempt_id": uuid4(), "lease_token": record.lease_token,
                "signed_at": moment, "body": b'{"synthetic":true}', "credential": "s" * 43,
                "key_id": uuid4(), "event_id": uuid4(), "config": {
                    "provider": "outgoing_webhook",
                    "endpoint": synthetic_endpoint(audience_approved=True)}}

    class Transaction:
        def __enter__(self):
            assert not state["open"]
            state["open"] = True
            return database

        def __exit__(self, *arguments):
            state["open"] = False

    def transport(config, host, port, method, target, headers, content, limit, **options):
        assert not state["open"] and content == prepared["body"]
        assert headers["x-ocote-event-id"] == str(prepared["event_id"])
        return 204, {}, b""

    factory.begin.side_effect = Transaction
    database.get.return_value = record
    monkeypatch.setattr(worker, "context", lambda *arguments: principal)
    monkeypatch.setattr(worker, "ready", lambda *arguments: True)
    monkeypatch.setattr(worker, "claim", lambda *arguments: prepared)
    monkeypatch.setattr(worker, "changed", lambda *arguments: None)
    report = worker.tick(factory, principal.id, 1, request=request, transport=transport)
    assert report["accepted"] == 1 and record.state == "delivered"
    assert "credential" not in prepared and not state["open"]
    assert set(report) == {"queued", "accepted", "retryable", "rejected", "ambiguous",
                           "fenced", "recovered", "cancelled"}


@pytest.mark.parametrize("mode", ["created", "duplicate", "collision", "removed_event", "pending"])
def test_f11_webhook_replay_creates_linked_delivery_and_never_reopens_original(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.collaboration import OutboxEvent
    from app.models.identity import User
    from app.models.integrations import WebhookDelivery, WebhookSubscription
    from app.schemas.integrations import WebhookReplay
    from app.services import outgoing_webhooks as service

    department = uuid4()
    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    subscription = SimpleNamespace(id=uuid4(), version=2, integration_id=uuid4(),
                                    owner_user_id=actor.id, department_ids=[department],
                                    event_types=["assignment"], enabled=True,
                                    max_attempts=3, retry_base_seconds=5, max_delay_seconds=300)
    event = SimpleNamespace(id=uuid4(), event_id=uuid4(), event_type="assignment",
                             department_id=department)
    original = SimpleNamespace(id=uuid4(), version=4, subscription_id=subscription.id,
                                outbox_id=event.id, body=b'{"synthetic":true}', state="dead_letter")
    config = SimpleNamespace(config_revision=3, secret_id=uuid4())
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    records = {WebhookSubscription: subscription, WebhookDelivery: original,
               OutboxEvent: event, User: actor}
    database.get.side_effect = lambda model, key, **kwargs: records[model]
    previous = service.new_delivery(subscription, event, config, original.body, "replay:synthetic",
                                     retry_of=original.id, actor=actor.id)
    database.scalar.return_value = previous if mode in {"duplicate", "collision"} else None
    monkeypatch.setattr(service.integrations, "reauthenticate", lambda *arguments: None)
    monkeypatch.setattr(service.integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(service, "department_scope", lambda *arguments: None)
    monkeypatch.setattr(service, "configuration", lambda *args, **kwargs: config)
    monkeypatch.setattr(service, "can_view", lambda *arguments: True)
    if mode == "removed_event":
        subscription.event_types = ["overdue"]
    if mode == "pending":
        original.state = "pending"
    if mode == "collision":
        previous.retry_of_id = uuid4()
    body = WebhookReplay(expected_version=4, current_password="synthetic-only-password",
                          reason="Synthetic approved replay", delivery_id=original.id,
                          idempotency_key=uuid4())
    if mode in {"created", "duplicate"}:
        result = service.replay(database, subscription.id, body, request, actor)
        assert result["retry_of_id"] == original.id and result["state"] == "pending"
        deliveries = [call.args[0] for call in database.add.call_args_list
                      if isinstance(call.args[0], WebhookDelivery)]
        assert len(deliveries) == (1 if mode == "created" else 0)
        if deliveries:
            assert deliveries[0].body == original.body and deliveries[0].attempt_count == 0
            assert deliveries[0].signing_secret_id == config.secret_id
            assert deliveries[0].max_delay_seconds == 300
    else:
        with pytest.raises(CommandError):
            service.replay(database, subscription.id, body, request, actor)
        database.add.assert_not_called()
    assert original.version == 4
    assert original.state == ("pending" if mode == "pending" else "dead_letter")
    assert "body" not in service.delivery_view(previous)
    assert "signing_secret_id" not in service.delivery_view(previous)


@pytest.mark.parametrize("provider", ["github", "gitlab", "outgoing_webhook"])
@pytest.mark.parametrize("mode", ["passed", "rejected", "changed"])
def test_f11_connector_probe_uses_no_orm_during_network_and_never_activates(
    monkeypatch, provider, mode,
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.core.integration_security import valid_webhook_signature
    from app.models.platform import IntegrationHealthCheck
    from app.schemas.integrations import ConnectorTest
    from app.services import identity, integrations

    state = {"outside": False}

    class Record(SimpleNamespace):
        def __getattribute__(self, name):
            if state["outside"] and not name.startswith("__"):
                raise AssertionError("ORM access reopens a transaction before network")
            return super().__getattribute__(name)

    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True, token_version=1)
    record = Record(id=uuid4(), version=1, config_revision=2, tested_version=2,
                    tested_at=datetime.now(UTC), is_active=True, secret_id=uuid4(),
                    kind="outgoing_webhook" if provider == "outgoing_webhook" else "devops",
                    scope_kind="organization", department_id=None)
    identity_id, secret_id = record.id, record.secret_id
    values = ({"provider": provider, "endpoint": synthetic_endpoint(audience_approved=True)}
              if provider == "outgoing_webhook" else synthetic_devops(provider))
    config = integrations.CONFIG.validate_python(values)
    credential = ("s" * 43 if provider == "outgoing_webhook" else
                  json.dumps({"access_token": "synthetic-token", "webhook_secret": "s" * 43}))
    body = ConnectorTest(expected_version=1, current_password="synthetic-admin", confirmed=True,
                         reason="Synthetic approved probe", revocation_confirmed=None,
                         test_username=None, test_password=None, emergency_password=None)
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.get.return_value = actor
    database.commit.side_effect = lambda: state.update(outside=True)
    database.expire_all.side_effect = lambda: state.update(outside=False)
    monkeypatch.setattr(identity, "config_lock", lambda *arguments: None)
    monkeypatch.setattr(integrations, "reauthenticate", lambda *arguments: None)
    monkeypatch.setattr(integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(integrations, "department_scope", lambda *arguments: None)
    monkeypatch.setattr(integrations, "connector_for", lambda *args, **kwargs: record)
    monkeypatch.setattr(integrations, "connector_material", lambda *args: (config, credential))
    monkeypatch.setattr(integrations.platform, "revision", lambda *arguments: uuid4())
    monkeypatch.setattr(integrations, "connector_view", lambda entry: {
        "is_active": entry.is_active, "tested_version": entry.tested_version
    })

    def transport(network, host, port, method, target, headers, content, limit, **options):
        assert state["outside"]
        if mode == "changed":
            object.__setattr__(record, "config_revision", 3)
        if provider == "outgoing_webhook":
            assert method == "POST" and options == {"reject_redirects": False}
            assert headers["x-ocote-key-id"] == str(secret_id)
            timestamp = int(headers["x-ocote-timestamp"])
            assert valid_webhook_signature(b"s" * 43, timestamp, content,
                                            headers["x-ocote-signature"], current_time=timestamp)
            assert json.loads(content)["synthetic"] is True
            assert json.loads(content)["event_type"] == "ocote.connection_test"
        else:
            assert method == "GET" and headers["authorization"] == "Bearer synthetic-token"
        document = {"id": 123, "full_name": "synthetic/repository",
                    "path_with_namespace": "synthetic/repository"}
        return (503 if mode == "rejected" else 200,
                {"content-type": "application/json"}, json.dumps(document).encode())

    request.app.state.integration_transport = transport
    if mode == "changed":
        with pytest.raises(CommandError) as caught:
            integrations.test_connector(database, None, identity_id, body, request, actor)
        assert caught.value.status == 409 and caught.value.persist
    else:
        result, browser = integrations.test_connector(
            database, None, identity_id, body, request, actor
        )
        assert result["passed"] == (mode == "passed") and browser is None
        assert record.tested_version == (2 if mode == "passed" else None)
    checks = [call.args[0] for call in database.add.call_args_list
              if isinstance(call.args[0], IntegrationHealthCheck)]
    assert len(checks) == 1 and checks[0].status == ("passed" if mode == "passed" else "failed")
    assert not record.is_active
    database.commit.assert_called_once()


@pytest.mark.parametrize("mode", [
    "passed", "expired", "revision", "emergency_changed", "locked", "missing_check",
])
def test_f11_activation_requires_fresh_exact_proof_and_usable_local_emergency(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import federation, integrations

    moment = datetime.now(UTC)
    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    emergency = SimpleNamespace(id=uuid4(), role="admin", is_active=True,
                                 token_version=1, locked_until=None)
    record = SimpleNamespace(id=uuid4(), version=1, config_revision=2, tested_version=2,
                             tested_at=moment - timedelta(minutes=1), is_active=False,
                             kind="sso", scope_kind="organization", department_id=None)
    endpoint = SimpleNamespace(audience_approved=True)
    config = SimpleNamespace(
        provider="oidc", jit_enabled=False, emergency_admin_id=emergency.id,
        authorization_endpoint=endpoint, token_endpoint=endpoint, jwks_endpoint=endpoint,
        model_dump=lambda **kwargs: {"revocation_window_seconds": 300},
    )
    expected = federation.sso_proof_code(record, config, emergency)
    database, request = MagicMock(), MagicMock()
    database.get.return_value = emergency
    database.scalar.side_effect = lambda query: (
        uuid4() if mode != "missing_check" and expected in query.compile().params.values() else None
    )
    monkeypatch.setattr(integrations, "reauthenticate", lambda *arguments: None)
    monkeypatch.setattr(integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(integrations, "department_scope", lambda *arguments: None)
    monkeypatch.setattr(integrations, "connector_for", lambda *arguments, **kwargs: record)
    monkeypatch.setattr(integrations, "connector_material", lambda *arguments: (config, "secret"))
    monkeypatch.setattr(integrations, "connector_view", lambda entry: {
        "is_active": entry.is_active
    })
    monkeypatch.setattr(integrations.platform, "revision", lambda *arguments: uuid4())
    if mode == "expired":
        record.tested_at = moment - timedelta(minutes=11)
    if mode == "revision":
        record.tested_version = 1
    if mode == "emergency_changed":
        emergency.token_version += 1
    if mode == "locked":
        emergency.locked_until = moment + timedelta(minutes=5)
    body = SimpleNamespace(expected_version=1, reason="Synthetic explicit activation")
    if mode == "passed":
        result = integrations.activate_connector(database, record.id, body, request, actor)
        assert result["is_active"]
        assert record.version == 2
    else:
        with pytest.raises(CommandError):
            integrations.activate_connector(database, record.id, body, request, actor)
        assert not record.is_active and record.version == 1


def test_f11_jit_target_needs_unique_explicit_verified_mapping_and_never_promotes():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.federation import jit_target

    department = uuid4()
    first = SimpleNamespace(
        attribute="groups",
        value="ocote-synthetic-team",
        role="colaborador",
        department_id=department,
    )
    config = SimpleNamespace(jit_enabled=True, jit_mappings=[first])
    assert jit_target(config, {"groups": [first.value]}) == ("colaborador", department)
    for attributes in ({}, {"groups": "not-an-array"}, {"groups": [True]}):
        with pytest.raises(CommandError):
            jit_target(config, attributes)
    config.jit_mappings.append(
        SimpleNamespace(
            attribute="groups", value="ocote-other-team", role="lider", department_id=uuid4()
        )
    )
    with pytest.raises(CommandError) as caught:
        jit_target(config, {"groups": [first.value, "ocote-other-team"]})
    assert caught.value.code == "SSO_JIT_MAPPING_AMBIGUOUS"
    config.jit_mappings = [first]
    for role in ("admin", "gerente"):
        first.role = role
        with pytest.raises(CommandError):
            jit_target(config, {"groups": [first.value]})
    first.role, config.jit_enabled = "colaborador", False
    with pytest.raises(CommandError):
        jit_target(config, {"groups": [first.value]})


def test_f11_bindings_are_owner_filtered_and_revocation_closes_only_bound_sessions(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.services import federation

    moment = datetime.now(UTC)
    actor = SimpleNamespace(id=uuid4(), role="colaborador", is_active=True)
    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        integration_id=uuid4(),
        user_id=actor.id,
        issuer="https://idp.example.invalid",
        subject="stable-synthetic-id",
        created_at=moment - timedelta(minutes=1),
        last_authenticated_at=moment,
        revoked_at=None,
        __tablename__="external_identities",
    )
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.scalars.return_value = [record]
    database.get.return_value = record
    monkeypatch.setattr(federation, "sso_modules", lambda db: None)
    monkeypatch.setattr(federation, "require_page_size", lambda db, limit: None)
    monkeypatch.setattr(federation, "reauthenticate", lambda *arguments: None)
    assert federation.bindings(database, actor, 5)["items"][0]["id"] == record.id
    query = database.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "WHERE external_identities.user_id" in str(query)
    assert actor.id in query.params.values()
    assert str(query).index("WHERE") < str(query).index("LIMIT")
    with pytest.raises(CommandError):
        federation.bindings(database, actor, 5, user_id=uuid4())
    body = SimpleNamespace(expected_version=1, reason="Synthetic explicit link revocation")
    result = federation.revoke_binding(database, record.id, body, request, actor)
    assert result["revoked_at"] is not None and record.version == 2
    command = database.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "WHERE refresh_sessions.external_identity_id" in str(command)
    assert record.id in command.params.values()
    assert "user_id" not in str(command)
    actor.id = uuid4()
    with pytest.raises(CommandError) as caught:
        federation.revoke_binding(database, record.id, body, request, actor)
    assert caught.value.status == 404


def test_f11_sso_finish_uses_bound_user_once_and_never_extends_idp_deadline(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, create_autospec
    from uuid import uuid4

    from app.models.identity import User
    from app.models.integrations import SSOTransaction
    from app.services import federation

    moment, browser = datetime.now(UTC), "b" * 43
    user = SimpleNamespace(id=uuid4(), is_active=True, department_id=uuid4())
    provider = SimpleNamespace(
        id=uuid4(),
        config_revision=2,
        scope_kind="department",
        department_id=user.department_id,
        config={},
    )
    transaction = SimpleNamespace(
        id=uuid4(),
        version=1,
        integration_id=provider.id,
        config_revision=2,
        purpose="login",
        state="verified",
        expires_at=moment + timedelta(minutes=5),
        authenticated_at=moment,
        consumed_at=None,
        browser_hash=federation.fingerprint(browser),
        initiating_user_id=None,
        issuer="https://idp.example.invalid",
        subject="stable-subject",
        __tablename__="sso_transactions",
    )
    link = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        integration_id=provider.id,
        revoked_at=None,
        version=1,
        __tablename__="external_identities",
    )
    database, request = MagicMock(), MagicMock()
    request.headers = {"origin": "https://localhost:8443"}
    request.state.request_id = str(uuid4())
    tokens = SimpleNamespace(settings=SimpleNamespace(auth_origin="https://localhost:8443"))
    records = {(SSOTransaction, transaction.id): transaction, (User, user.id): user}
    database.get.side_effect = lambda model, identity, **kwargs: records.get((model, identity))
    database.scalar.return_value = link
    monkeypatch.setattr(federation, "sso_modules", lambda db: None)
    monkeypatch.setattr(federation, "configured",
                        create_autospec(federation.configured, return_value=provider))
    monkeypatch.setattr(
        federation, "policy", lambda db: SimpleNamespace(refresh_absolute_seconds=3600)
    )
    monkeypatch.setattr(
        federation.integrations,
        "CONFIG",
        SimpleNamespace(
            validate_python=lambda value: SimpleNamespace(
                revocation_window_seconds=300, jit_enabled=False
            )
        ),
    )
    issued = []

    def session_response(db, tokens, owner, family, expires, **metadata):
        issued.append((owner, expires, metadata))
        return SimpleNamespace(family_id=family), "synthetic-refresh", {"user": owner.id}

    monkeypatch.setattr(federation.identity, "session_response", session_response)
    refresh, result = federation.finish(database, tokens, request, transaction.id, browser)
    assert refresh == "synthetic-refresh" and result == {"user": user.id}
    assert transaction.state == "consumed" and transaction.consumed_at is not None
    assert issued == [
        (
            user,
            moment + timedelta(seconds=300),
            {
                "external_identity_id": link.id,
                "federated_authenticated_at": moment,
                "federated_revocation_deadline": moment + timedelta(seconds=300),
            },
        )
    ]
    with pytest.raises(CommandError):
        federation.finish(database, tokens, request, transaction.id, browser)
    assert len(issued) == 1
    transaction.state, transaction.consumed_at = "verified", None
    database.scalar.return_value = None
    with pytest.raises(CommandError) as caught:
        federation.finish(database, tokens, request, transaction.id, browser)
    assert caught.value.code == "EXTERNAL_IDENTITY_NOT_BOUND"
    assert transaction.state == "verified" and len(issued) == 1


def test_f11_refresh_rotation_preserves_federated_deadline(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.services import enterprise, identity

    moment = datetime.now(UTC)
    user = SimpleNamespace(id=uuid4())
    previous = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        family_id=uuid4(),
        consumed_at=None,
        revoked_at=None,
        expires_at=moment + timedelta(minutes=5),
        external_identity_id=uuid4(),
        federated_authenticated_at=moment - timedelta(minutes=1),
        federated_revocation_deadline=moment + timedelta(minutes=5),
    )
    database, request, tokens = MagicMock(), MagicMock(), MagicMock()
    request.headers = {"x-csrf-token": "synthetic-csrf"}
    request.state.request_id = str(uuid4())
    monkeypatch.setattr(identity, "origin", lambda *arguments: None)
    monkeypatch.setattr(identity, "cookie_session", lambda *arguments: (user, previous))
    monkeypatch.setattr(enterprise, "session_policy", lambda *arguments: None)
    issued = []

    def successor(db, tokens, owner, family, expires, **metadata):
        issued.append((owner, family, expires, metadata))
        return SimpleNamespace(id=uuid4()), "synthetic-rotated", {"authenticated": True}

    monkeypatch.setattr(identity, "session_response", successor)
    refresh, result = identity.rotate(database, tokens, request)
    tokens.check_csrf.assert_called_once_with(
        "synthetic-csrf", previous.family_id, previous.expires_at
    )
    assert refresh == "synthetic-rotated" and result["authenticated"]
    assert issued == [
        (
            user,
            previous.family_id,
            previous.expires_at,
            {
                "external_identity_id": previous.external_identity_id,
                "federated_authenticated_at": previous.federated_authenticated_at,
                "federated_revocation_deadline": previous.federated_revocation_deadline,
            },
        )
    ]


def test_f11_sso_callback_accepts_only_bounded_exact_form_and_redacts_authorization(monkeypatch):
    import inspect
    import logging
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from urllib.parse import urlencode
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from test_foundation import settings

    from app.core.notifications import CalendarAccessFilter
    from app.main import create_app
    from app.routers.auth import saml_form
    from app.services import federation, identity

    integration, transaction = uuid4(), uuid4()
    calls = []
    signature = inspect.signature(federation.callback)

    def verified(*arguments, **keywords):
        signature.bind(*arguments, **keywords)
        calls.append((arguments, keywords))
        return transaction

    monkeypatch.setattr(federation, "callback", verified)
    application = create_app(settings())
    application.dependency_overrides[identity.database] = lambda: MagicMock()
    application.dependency_overrides[identity.token_service] = lambda: SimpleNamespace(
        settings=SimpleNamespace(auth_origin="https://localhost:8443")
    )
    path = f"/api/v1/auth/sso/{integration}/callback"
    content = urlencode({"SAMLResponse": "synthetic+signed/response=", "RelayState": "s" * 43})
    assert saml_form(content.encode()) == ("s" * 43, "synthetic+signed/response=")
    with TestClient(
        application, base_url="https://localhost:8443", follow_redirects=False
    ) as client:
        response = client.post(
            path, content=content, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 303
        assert response.headers["location"] == (
            f"https://localhost:8443/login?sso_transaction={transaction}"
        )
        assert "set-cookie" not in response.headers
        assert response.headers["referrer-policy"] == "no-referrer"
        assert calls[-1][1] == {"response": "synthetic+signed/response="}
        response = client.get(path + "?" + urlencode({"state": "s" * 43, "code": "synthetic"}))
        assert response.status_code == 303 and calls[-1][1] == {"code": "synthetic"}
        assert client.post(path, json={}).status_code == 415
        assert (
            client.post(
                "/api/v1/auth/login",
                content=content,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ).status_code
            == 415
        )
        for invalid in (content + "&RelayState=duplicate", "RelayState=only", "bad=%FF"):
            response = client.post(
                path, content=invalid, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            assert response.status_code == 401
        response = client.post(
            path,
            content=b"x" * (1048576 + 1),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 413
        assert client.get(path + "?state=one&state=two&code=secret").status_code == 401
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "%s %s %s %s %s",
        ("peer", "GET", path + "?code=secret&state=private", "1.1", 303),
        None,
    )
    assert CalendarAccessFilter().filter(record)
    assert "secret" not in record.getMessage() and "private" not in record.getMessage()


def test_f11_technical_routes_have_only_scoped_task_commands_and_reject_extra_mutations():
    from fastapi.testclient import TestClient
    from test_foundation import settings

    from app.main import create_app
    from app.schemas.integrations import ServiceTaskUpdate

    application = create_app(settings())
    routes = {
        (path, method.upper())
        for path, methods in application.openapi()["paths"].items()
        if path.startswith("/api/v1/service")
        for method in methods
    }
    assert routes == {
        ("/api/v1/service/tasks", "GET"),
        ("/api/v1/service/tasks", "POST"),
        ("/api/v1/service/tasks/{identity}", "GET"),
        ("/api/v1/service/tasks/{identity}", "PATCH"),
    }
    with TestClient(application) as client:
        for path in ("auth/refresh", "evidence", "evaluations", "tasks/close", "tasks/reprogram"):
            assert client.post("/api/v1/service/" + path, json={}).status_code in {404, 405}
    values = {
        "expected_version": 1,
        "title": "Synthetic title",
        "description": "",
        "reason": "Synthetic metadata update",
    }
    assert ServiceTaskUpdate.model_validate(values)
    from pydantic import ValidationError

    for field in ("stage_id", "due_date", "start_date", "completed_at", "assignee_id"):
        with pytest.raises(ValidationError):
            ServiceTaskUpdate.model_validate({**values, field: "forbidden"})


def test_f11_technical_query_filters_key_departments_and_current_owner_before_pagination():
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.services.integrations import technical_query

    department, owner = uuid4(), uuid4()
    actor = SimpleNamespace(
        role="colaborador", id=owner, department_id=department, service_department_ids={department}
    )
    query = technical_query(actor).limit(6)
    compiled = query.compile(dialect=postgresql.dialect())
    assert "tasks.assignee_id" in str(compiled)
    assert "objectives.department_id IN" in str(compiled)
    assert owner in compiled.params.values()
    assert [department] in compiled.params.values()


@pytest.mark.parametrize(
    "change,allowed",
    [
        ({}, True),
        ({"scopes": ["tasks:read", "tasks:create"]}, False),
        ({"allowed_networks": ["192.0.0.0/16"]}, False),
        ({"allowed_networks": None}, False),
        ({"rate_per_minute": 21}, False),
    ],
)
def test_f11_key_rotation_is_atomic_reauthenticated_and_never_expands(monkeypatch, change, allowed):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.schemas.integrations import APIKeyIssue
    from app.services import integrations

    moment, department = datetime.now(UTC), uuid4()
    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    previous = SimpleNamespace(
        id=uuid4(),
        version=1,
        service_principal_id=uuid4(),
        owner_user_id=uuid4(),
        scopes=["tasks:read"],
        department_ids=[department],
        allowed_networks=["192.0.2.0/24"],
        rate_per_minute=20,
        revoked_at=None,
        expires_at=moment + timedelta(days=1),
    )
    body = APIKeyIssue.model_validate(
        {
            "expected_version": 1,
            "current_password": "Synthetic-password-only!42",
            "reason": "Synthetic explicit rotation",
            "name": "Synthetic successor",
            "service_principal_id": previous.service_principal_id,
            "owner_user_id": previous.owner_user_id,
            "scopes": ["tasks:read"],
            "department_ids": [department],
            "allowed_networks": ["192.0.2.0/25"],
            "rate_per_minute": 20,
            "expires_at": moment + timedelta(days=2),
            **change,
        }
    )
    database, request = MagicMock(), MagicMock()
    database.get.return_value = previous
    request.state.request_id = str(uuid4())
    reauthenticate = MagicMock()
    monkeypatch.setattr(integrations, "reauthenticate", reauthenticate)
    monkeypatch.setattr(integrations, "modules", lambda *arguments: None)
    issued = []

    def successor(db, command, request, administrator, *, rotated_from):
        assert previous.revoked_at is not None and previous.version == 2
        database.flush.assert_called_once()
        assert command.expected_version == 0 and rotated_from == previous.id
        issued.append(command)
        return {"api_key": "synthetic-one-time-successor", "rotated_from_id": rotated_from}

    monkeypatch.setattr(integrations, "_new_key", successor)
    if allowed:
        result = integrations.rotate_key(database, previous.id, body, request, actor)
        assert result["api_key"] == "synthetic-one-time-successor" and len(issued) == 1
    else:
        with pytest.raises(CommandError) as caught:
            integrations.rotate_key(database, previous.id, body, request, actor)
        assert caught.value.code == "SERVICE_ROTATION_MUST_NOT_EXPAND"
        assert previous.revoked_at is None and not issued
    reauthenticate.assert_called_once_with(database, actor, body, request)


def test_f11_principal_contract_has_only_five_scopes_and_unique_explicit_departments():
    from uuid import uuid4

    from pydantic import ValidationError

    from app.schemas.integrations import PrincipalWrite

    department = uuid4()
    values = {
        "expected_version": 0,
        "current_password": "Synthetic-password-only!42",
        "reason": "Synthetic explicit principal",
        "name": "Synthetic service",
        "department_ids": [department],
        "approved_scopes": ["tasks:read"],
        "is_active": True,
    }
    assert PrincipalWrite.model_validate(values)
    for change in (
        {"approved_scopes": ["administration:manage"]},
        {"department_ids": [department, department]},
        {"approved_scopes": ["tasks:read", "tasks:read"]},
    ):
        with pytest.raises(ValidationError):
            PrincipalWrite.model_validate({**values, **change})


def test_f11_key_issue_authentication_and_revocation_never_return_stored_secrets(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.collaboration import ServicePrincipal
    from app.models.identity import User
    from app.models.integrations import APIKey
    from app.schemas.integrations import APIKeyIssue
    from app.schemas.platform import Change
    from app.services import integrations

    database = MagicMock()
    department = uuid4()
    owner = SimpleNamespace(
        id=uuid4(), role="lider", department_id=department, is_active=True, token_version=3
    )
    admin = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    principal = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        token_version=2,
        approved_scopes=["tasks:read"],
        department_ids=[department],
    )
    records = {(User, owner.id): owner, (ServicePrincipal, principal.id): principal}
    database.get.side_effect = lambda model, identity, **options: records.get((model, identity))
    database.scalars.return_value = [department]
    database.scalar.return_value = 0
    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="10.20.30.40"),
        state=SimpleNamespace(request_id=str(uuid4())),
    )
    for name in ("reauthenticate", "modules"):
        monkeypatch.setattr(integrations, name, lambda *args: None)
    material = {}

    def store(db, identity, purpose, value, reason, request, actor):
        assert purpose == "service_keys"
        material[identity] = value
        return uuid4()

    monkeypatch.setattr(integrations, "store_secret", store)
    monkeypatch.setattr(
        integrations,
        "decrypted_secret",
        lambda db, owner, identity, purpose, request: material[owner],
    )
    body = APIKeyIssue(
        expected_version=0,
        reason="Synthetic service credential test",
        current_password="synthetic-password",
        name="Synthetic key",
        owner_user_id=owner.id,
        service_principal_id=principal.id,
        scopes=["tasks:read"],
        department_ids=[department],
        allowed_networks=["10.20.0.0/16"],
        rate_per_minute=5,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    issued = integrations.issue_key(database, body, request, admin)
    record = next(
        call.args[0] for call in database.add.call_args_list if isinstance(call.args[0], APIKey)
    )
    records[(APIKey, record.id)] = record
    assert issued["api_key"].startswith("oct_svc_" + record.id.hex + ".")
    view = integrations.key_view(record)
    assert "api_key" not in view and "token_hash" not in view and "pepper_secret_id" not in view
    request.headers["authorization"] = "Bearer " + issued["api_key"]
    actor = integrations.authenticate_key(database, request, "tasks:read")
    assert actor.id == owner.id and actor.actor_service_id == principal.id
    assert actor.service_department_ids == {department}
    request.headers["authorization"] = request.headers["authorization"][:-1] + "!"
    with pytest.raises(CommandError) as caught:
        integrations.authenticate_key(database, request, "tasks:create")
    assert caught.value.status == 401
    request.headers["authorization"] = "Bearer " + issued["api_key"]
    with pytest.raises(CommandError) as caught:
        integrations.authenticate_key(database, request, "tasks:create")
    assert caught.value.status == 403
    database.scalar.return_value = 5
    with pytest.raises(CommandError) as caught:
        integrations.authenticate_key(database, request, "tasks:read")
    assert caught.value.status == 429
    revoked = integrations.revoke_key(
        database,
        record.id,
        Change(expected_version=1, reason="Synthetic credential revocation"),
        request,
        admin,
    )
    assert revoked["revoked_at"] is not None and revoked["version"] == 2
    with pytest.raises(CommandError) as caught:
        integrations.authenticate_key(database, request, "tasks:read")
    assert caught.value.status == 401


def test_f11_key_context_intersects_current_owner_principal_and_key():
    from copy import copy
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.integrations import key_context

    department, other = uuid4(), uuid4()
    principal = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        token_version=2,
        approved_scopes=["tasks:read", "tasks:create"],
        department_ids=[department],
    )
    owner = SimpleNamespace(
        id=uuid4(), is_active=True, token_version=3, role="lider", department_id=department
    )
    record = SimpleNamespace(
        id=uuid4(),
        service_principal_id=principal.id,
        owner_user_id=owner.id,
        principal_token_version=2,
        owner_token_version=3,
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        allowed_networks=["10.20.0.0/16"],
        scopes=["tasks:read", "tasks:create", "tasks:update_metadata"],
        department_ids=[department, other],
    )
    actor = key_context(record, principal, owner, "tasks:create", "10.20.30.40", datetime.now(UTC))
    assert actor.actor_service_id == principal.id and actor.id == owner.id
    assert actor.service_department_ids == frozenset({department})
    assert actor.service_scopes == {"tasks:read", "tasks:create"}
    with pytest.raises(CommandError) as caught:
        key_context(
            record, principal, owner, "tasks:update_metadata", "10.20.30.40", datetime.now(UTC)
        )
    assert caught.value.status == 403
    for field, value in (("is_active", False), ("token_version", 4)):
        changed = copy(owner)
        setattr(changed, field, value)
        with pytest.raises(CommandError) as caught:
            key_context(record, principal, changed, "tasks:read", "10.20.30.40", datetime.now(UTC))
        assert caught.value.status == 401
    for field, value in (("is_active", False), ("token_version", 3)):
        changed = copy(principal)
        setattr(changed, field, value)
        with pytest.raises(CommandError):
            key_context(record, changed, owner, "tasks:read", "10.20.30.40", datetime.now(UTC))
    changed = copy(owner)
    changed.role = "gerente"
    with pytest.raises(CommandError) as caught:
        key_context(record, principal, changed, "tasks:create", "10.20.30.40", datetime.now(UTC))
    assert caught.value.status == 403
    changed.department_id, changed.role = other, "lider"
    with pytest.raises(CommandError):
        key_context(record, principal, changed, "tasks:read", "10.20.30.40", datetime.now(UTC))
    with pytest.raises(CommandError):
        key_context(record, principal, owner, "tasks:read", "203.0.113.8", datetime.now(UTC))


def test_f11_connector_save_is_versioned_write_only_and_omission_preserves_secret(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.platform import IntegrationConfig
    from app.schemas.integrations import ConnectorWrite
    from app.services import integrations

    database, request = MagicMock(), MagicMock()
    actor = SimpleNamespace(id=uuid4(), is_active=True, role="admin")
    for name in ("reauthenticate", "modules", "department_scope"):
        monkeypatch.setattr(integrations, name, lambda *args: None)
    revision = MagicMock(return_value=uuid4())
    store = MagicMock(return_value=uuid4())
    monkeypatch.setattr(integrations.platform, "revision", revision)
    monkeypatch.setattr(integrations, "store_secret", store)
    material = json.dumps(
        {"access_token": "synthetic-token", "webhook_secret": "synthetic-webhook-secret"}
    )
    values = {
        "expected_version": 0,
        "reason": "Synthetic configuration only",
        "current_password": "synthetic-password",
        "name": "Synthetic DevOps",
        "scope_kind": "organization",
        "department_id": None,
        "config": synthetic_devops("github"),
        "credential": material,
    }
    result = integrations.save_connector(
        database, None, ConnectorWrite.model_validate(values), request, actor
    )
    record = database.add.call_args.args[0]
    assert isinstance(record, IntegrationConfig)
    assert result["secret_configured"] is True and result["is_active"] is False
    assert result["config_revision"] == 1 and result["tested_version"] is None
    assert "credential" not in result and "secret_id" not in result
    assert material not in json.dumps(result, default=str)
    database.get.return_value = record
    record.is_active, record.tested_version = True, 1
    unchanged = {**values, "expected_version": 1}
    unchanged.pop("credential")
    same = integrations.save_connector(
        database, record.id, ConnectorWrite.model_validate(unchanged), request, actor
    )
    assert same["is_active"] is True and same["config_revision"] == 1
    assert store.call_count == revision.call_count == 1
    changed = {**unchanged, "name": "Synthetic renamed"}
    updated = integrations.save_connector(
        database, record.id, ConnectorWrite.model_validate(changed), request, actor
    )
    assert updated["version"] == 2 and updated["config_revision"] == 2
    assert updated["is_active"] is False and updated["tested_version"] is None
    assert store.call_count == 1 and updated["secret_configured"] is True
    with pytest.raises(CommandError) as caught:
        integrations.save_connector(
            database, record.id, ConnectorWrite.model_validate(changed), request, actor
        )
    assert caught.value.status == 409 and store.call_count == 1
    actor.role = "gerente"
    with pytest.raises(CommandError) as caught:
        integrations.save_connector(
            database, None, ConnectorWrite.model_validate(values), request, actor
        )
    assert caught.value.status == 403


@pytest.mark.parametrize("security", ["ldaps", "starttls"])
@pytest.mark.parametrize("subject_attribute", ["entryUUID", "objectGUID"])
def test_f11_ldap_binds_only_after_pinned_verified_tls(security, subject_attribute):
    import socket
    import ssl
    from uuid import uuid4

    from app.core.federation import ldap_identity

    subject = uuid4()
    events = []
    configuration = {
        **synthetic_endpoint(audience_approved=True),
        "provider": "ldap",
        "port": 636 if security == "ldaps" else 389,
        "security": security,
        "bind_dn": "cn=synthetic-reader,dc=example,dc=invalid",
        "user_search_base": "ou=people,dc=example,dc=invalid",
        "username_attribute": "uid",
        "subject_attribute": subject_attribute,
        "emergency_admin_id": str(uuid4()),
        "revocation_window_seconds": 300,
        "jit_enabled": False,
        "jit_mappings": [],
    }
    configuration.pop("url")
    invalid_certificate = False
    ambiguous = False
    tls_available = True

    class Peer:
        def getpeercert(self):
            events.append("hostname_verified")
            return {
                "subjectAltName": (
                    ("DNS", "wrong.invalid" if invalid_certificate else "idp.example.invalid"),
                )
            }

    class Directory:
        def __init__(self, server, **options):
            assert server.host == "8.8.8.8" and server.ssl == (security == "ldaps")
            assert server.tls.validate == ssl.CERT_REQUIRED
            assert server.tls.sni == "idp.example.invalid"
            assert options["auto_referrals"] is False and options["auto_bind"] is False
            assert options["read_only"] is True
            self.closed, self.socket, self.password = True, Peer(), options["password"]
            value = str(subject).encode() if subject_attribute == "entryUUID" else subject.bytes_le
            self.response = [
                {
                    "type": "searchResEntry",
                    "dn": "uid=synthetic,dc=example,dc=invalid",
                    "raw_attributes": {subject_attribute: [value]},
                }
            ]
            if ambiguous:
                self.response *= 2

        def open(self, **options):
            events.append("open")
            self.closed = False

        def start_tls(self, **options):
            events.append("starttls")
            return tls_available

        def bind(self):
            events.append("reader_bind")
            return True

        def search(self, base, user_filter, **options):
            events.append("search")
            assert user_filter == r"(uid=synthetic\2a\29\28uid=\2a\29)"
            assert options["size_limit"] == 2 and options["attributes"] == [subject_attribute]
            return True

        def rebind(self, **options):
            events.append("user_bind")
            return options["password"] == "synthetic-user-password"

        def unbind(self):
            events.append("unbind")
            assert self.password is None

    def resolver(host, port, **options):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    arguments = {"resolver": resolver, "connection_factory": Directory}
    result = ldap_identity(
        configuration,
        "synthetic-bind-password",
        "synthetic*)(uid=*)",
        "synthetic-user-password",
        **arguments,
    )
    assert result.subject == str(subject) and result.verified_email is None
    assert events.index("hostname_verified") < events.index("reader_bind")
    assert events.index("reader_bind") < events.index("user_bind") and events[-1] == "unbind"
    events.clear()
    invalid_certificate = True
    with pytest.raises(CommandError):
        ldap_identity(
            configuration,
            "synthetic-bind-password",
            "synthetic",
            "synthetic-user-password",
            **arguments,
        )
    assert "reader_bind" not in events
    invalid_certificate, ambiguous = False, True
    events.clear()
    with pytest.raises(CommandError):
        ldap_identity(
            configuration,
            "synthetic-bind-password",
            "synthetic*)(uid=*)",
            "synthetic-user-password",
            **arguments,
        )
    assert "user_bind" not in events
    if security == "starttls":
        ambiguous, tls_available = False, False
        events.clear()
        with pytest.raises(CommandError):
            ldap_identity(
                configuration,
                "synthetic-bind-password",
                "synthetic",
                "synthetic-user-password",
                **arguments,
            )
        assert "reader_bind" not in events


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_f11_devops_links_use_verified_ids_and_derived_urls(provider):
    from app.core.devops import external_reference

    calls = []

    def transport(config, host, port, method, target, headers, content, limit):
        calls.append(target)
        if len(calls) == 1:
            document = {
                "id": 123,
                "full_name": "synthetic/repository",
                "path_with_namespace": "synthetic/repository",
            }
        else:
            document = {
                "number": 14,
                "iid": 14,
                "project_id": 123,
                "state": "opened",
                "title": "Synthetic issue",
                "url": "https://untrusted.invalid/ignored",
            }
        return 200, {"content-type": "application/json"}, json.dumps(document).encode()

    result = external_reference(
        synthetic_devops(provider),
        "synthetic-token",
        "123",
        "issue",
        "14",
        transport=transport,
    )
    expected = (
        "https://github.com/synthetic/repository/issues/14"
        if provider == "github"
        else ("https://gitlab.example.invalid/synthetic/repository/-/issues/14")
    )
    assert result["canonical_url"] == expected
    assert result["safe_projection"] == {"state": "opened", "title": "Synthetic issue"}
    assert len(calls) == 2
    with pytest.raises(CommandError):
        external_reference(
            synthetic_devops(provider),
            "synthetic-token",
            "999",
            "issue",
            "14",
            transport=transport,
        )
    assert len(calls) == 2


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_f11_branches_use_exact_provider_names_and_safe_encoded_urls(provider):
    from app.core.devops import external_reference
    from app.schemas.integrations import branch_identifier

    calls = []

    def transport(config, host, port, method, target, headers, content, limit):
        calls.append(target)
        document = ({"id": 123, "full_name": "synthetic/repository",
                     "path_with_namespace": "synthetic/repository"} if len(calls) == 1 else
                    {"name": "feature/synthetic"})
        return 200, {"content-type": "application/json"}, json.dumps(document).encode()

    result = external_reference(synthetic_devops(provider), "synthetic-token", "123",
                                "branch", "feature/synthetic", transport=transport)
    assert calls[-1].endswith("/branches/feature%2Fsynthetic")
    assert result["canonical_url"].endswith("/tree/feature%2Fsynthetic")
    assert result["safe_projection"] == {}
    for invalid in ("../main", "main..old", "main.lock", "a/.hidden", "a//b", "a.lock/b",
                    "main?token=value", "main%2Fextra", "main ", "main/", "a" * 129):
        with pytest.raises(ValueError):
            branch_identifier(invalid)


@pytest.mark.parametrize("mode", [
    "created", "duplicate", "connector_changed", "actor_revoked", "task_changed", "forbidden",
])
def test_f11_link_persistence_rechecks_scope_versions_and_actor_after_network(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, create_autospec
    from uuid import uuid4

    from app.models.integrations import TaskExternalLink
    from app.schemas.integrations import ExternalLinkWrite
    from app.services import devops

    actor = SimpleNamespace(id=uuid4(), role="colaborador", is_active=True, token_version=1)
    task = SimpleNamespace(id=uuid4(), version=1, completed_at=None, stage_id=uuid4())
    objective = SimpleNamespace(department_id=uuid4())
    record = SimpleNamespace(id=uuid4(), version=2, config_revision=3, kind="devops",
                             is_active=True, scope_kind="department",
                             department_id=objective.department_id)
    body = ExternalLinkWrite(expected_version=1, integration_id=record.id, repository_id="123",
                             kind="branch", external_id="feature/synthetic",
                             reason="Synthetic approved link")
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.get.return_value = actor
    database.scalar.return_value = uuid4() if mode == "duplicate" else None
    monkeypatch.setattr(devops.integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(devops.operation, "configuration", lambda *arguments: None)
    monkeypatch.setattr(devops.identity, "config_lock", lambda *args, **kwargs: None)
    monkeypatch.setattr(devops.integrations, "connector_for", lambda *args, **kwargs: record)
    monkeypatch.setattr(devops.integrations, "connector_material", lambda *args: (
        synthetic_devops("github"), json.dumps({"access_token": "synthetic-token"})
    ))

    def scoped(db, user, entity_type, identity, *, write=False, roles=()):
        assert write and entity_type == "task" and identity == task.id
        assert roles == ("admin", "lider", "colaborador")
        if mode == "forbidden" and database.commit.called:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        return task, object(), objective

    resource = create_autospec(devops.resource, side_effect=scoped)
    monkeypatch.setattr(devops, "resource", resource)

    def verified(*args, **kwargs):
        database.commit.assert_called_once()
        database.add.assert_not_called()
        if mode == "connector_changed":
            record.config_revision += 1
        if mode == "actor_revoked":
            actor.token_version += 1
        if mode == "task_changed":
            task.version += 1
        return {"canonical_url": "https://github.com/synthetic/repository/tree/feature%2Fsynthetic",
                "safe_projection": {}}

    verify = create_autospec(devops.external_reference, side_effect=verified)
    monkeypatch.setattr(devops, "external_reference", verify)
    if mode == "created":
        result = devops.create_link(database, actor, task.id, body, request)
        assert result["kind"] == "branch" and result["version"] == 1
        assert result["created_by"] == str(actor.id)
        assert result["canonical_url"].endswith("feature%2Fsynthetic")
        links = [call.args[0] for call in database.add.call_args_list
                 if isinstance(call.args[0], TaskExternalLink)]
        assert len(links) == 1 and links[0].task_id == task.id
    else:
        with pytest.raises(CommandError) as caught:
            devops.create_link(database, actor, task.id, body, request)
        assert caught.value.status == (
            401 if mode == "actor_revoked" else 404 if mode == "forbidden" else 409
        )
        database.add.assert_not_called()
    verify.assert_called_once()
    assert task.completed_at is None
    assert resource.call_count == (1 if mode == "actor_revoked" else 2)


def test_f11_link_deactivation_is_versioned_terminal_and_does_not_change_task(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.integrations import TaskExternalLink
    from app.schemas.integrations import ExternalLinkDeactivate
    from app.services import devops

    moment = datetime.now(UTC)
    actor, task = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4(), version=5)
    link = TaskExternalLink(
        id=uuid4(), version=1, created_at=moment, updated_at=moment, task_id=task.id,
        integration_id=uuid4(), repository_id="123", external_id="14", kind="issue",
        canonical_url="https://github.com/synthetic/repository/issues/14", safe_projection={},
        created_by=actor.id, deactivated_at=None,
    )
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    database.scalar.return_value = link
    monkeypatch.setattr(devops, "task_context", lambda *args, **kwargs: (task, None, None))
    body = ExternalLinkDeactivate(expected_version=1, reason="Synthetic explicit deactivation")
    result = devops.deactivate_link(database, actor, task.id, link.id, body, request)
    assert result["deactivated_at"] is not None and link.version == 2
    first = link.deactivated_at
    body = body.model_copy(update={"expected_version": 2})
    devops.deactivate_link(database, actor, task.id, link.id, body, request)
    assert link.deactivated_at == first and link.version == 2 and task.version == 5
    with pytest.raises(CommandError) as caught:
        devops.deactivate_link(database, actor, task.id, link.id,
                               body.model_copy(update={"expected_version": 1}), request)
    assert caught.value.status == 409


@pytest.mark.parametrize("provider", ["github", "gitlab"])
@pytest.mark.parametrize("mode", ["created", "duplicate", "collision", "invalid"])
def test_f11_inbox_persists_only_authenticated_projection_and_rejects_collisions(
    monkeypatch, provider, mode,
):
    import hashlib
    import hmac
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.models.integrations import WebhookInbox
    from app.services import devops

    record = SimpleNamespace(id=uuid4(), kind="devops", is_active=True)
    database, request = MagicMock(), MagicMock()
    request.state.request_id = str(uuid4())
    config = devops.integrations.CONFIG.validate_python(synthetic_devops(provider))
    secret = "synthetic-only-webhook-secret"
    monkeypatch.setattr(devops.integrations, "modules", lambda *arguments: None)
    monkeypatch.setattr(devops.integrations, "connector_for", lambda *args, **kwargs: record)
    monkeypatch.setattr(devops.integrations, "connector_material", lambda *args: (
        config, json.dumps({"access_token": "synthetic-only-token", "webhook_secret": secret})
    ))
    payload = {"repository": {"id": 123}, "project": {"id": 123},
               "issue": {"number": 14, "title": "Synthetic issue"},
               "object_attributes": {"iid": 14, "project_id": 123, "title": "Synthetic issue"},
               "completed_at": "untrusted", "stage": "done"}
    body = json.dumps(payload).encode()
    headers = {"x-github-event": "issues", "x-github-delivery": "synthetic-delivery",
               "x-hub-signature-256": "sha256=" + hmac.new(
                   secret.encode(), body, hashlib.sha256).hexdigest(),
               "x-gitlab-event": "Issue Hook", "x-gitlab-event-uuid": "synthetic-delivery",
               "x-gitlab-token": secret}
    previous = SimpleNamespace(id=uuid4(), body_hash=hashlib.sha256(body).hexdigest())
    if mode == "collision":
        previous.body_hash = "f" * 64
    database.scalar.side_effect = [None, 0] if mode == "created" else [previous]
    if mode == "invalid":
        headers["x-gitlab-token"], headers["x-hub-signature-256"] = "invalid", "invalid"
    if mode in {"collision", "invalid"}:
        with pytest.raises(CommandError) as caught:
            devops.receive(database, record.id, headers, body, request)
        assert caught.value.status == (409 if mode == "collision" else 401)
        database.add.assert_not_called()
    else:
        result = devops.receive(database, record.id, headers, body, request)
        assert result["accepted"] and result["duplicate"] == (mode == "duplicate")
        inboxes = [call.args[0] for call in database.add.call_args_list
                   if isinstance(call.args[0], WebhookInbox)]
        assert len(inboxes) == (1 if mode == "created" else 0)
        if inboxes:
            assert set(inboxes[0].safe_projection) == {
                "repository_id", "external_id", "kind", "title"
            }
    database.execute.assert_not_called()
    database.commit.assert_not_called()


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_f11_inbound_devops_uses_native_auth_and_safe_projection(provider):
    import hashlib
    import hmac

    from app.core.devops import inbound_event

    secret = "synthetic-provider-webhook-secret"
    payload = {
        "repository": {"id": 123},
        "project": {"id": 123},
        "issue": {"number": 14, "title": "Synthetic issue", "state": "open"},
        "object_attributes": {
            "iid": 14,
            "project_id": 123,
            "title": "Synthetic issue",
            "state": "opened",
        },
        "progress": 100,
        "stage": "done",
        "due_date": "2026-12-01",
        "url": "https://untrusted.invalid/ignored",
    }
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Delivery": "synthetic-delivery",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": "sha256="
        + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "X-Gitlab-Event-UUID": "synthetic-delivery",
        "X-Gitlab-Event": "Issue Hook",
        "X-Gitlab-Token": secret,
    }
    result = inbound_event(synthetic_devops(provider), secret, headers, body)
    assert result["delivery_id"] == "synthetic-delivery"
    assert result["body_hash"] == hashlib.sha256(body).hexdigest()
    assert set(result["safe_projection"]) == {
        "repository_id",
        "external_id",
        "kind",
        "title",
        "state",
    }
    assert result["safe_projection"]["external_id"] == "14"
    if provider == "github":
        with pytest.raises(CommandError):
            inbound_event(synthetic_devops(provider), secret, headers, body + b" ")
    else:
        assert inbound_event(synthetic_devops(provider), secret, headers, body + b" ")
    for changed in (
        {"X-Gitlab-Token": "wrong", "X-Hub-Signature-256": "wrong"},
        {"X-GitHub-Delivery": "", "X-Gitlab-Event-UUID": ""},
    ):
        with pytest.raises(CommandError) as caught:
            inbound_event(synthetic_devops(provider), secret, {**headers, **changed}, body)
        assert caught.value.code == "DEVOPS_EVENT_INVALID"


def test_f11_https_exchange_is_bounded_pinned_and_does_not_follow_redirects():
    from app.core.integration_http import exchange

    calls = []

    def transport(config, host, port, method, target, headers, content, limit, **options):
        calls.append((config, host, port, method, target, headers, content, limit, options))
        return 200, {"content-type": "application/json"}, b"{}"

    endpoint = synthetic_endpoint(audience_approved=True)
    status, _, _ = exchange(endpoint, "GET", query={"id": "synthetic/value"}, transport=transport)
    assert status == 200 and len(calls) == 1
    assert calls[0][1:5] == ("idp.example.invalid", 443, "GET", "/endpoint?id=synthetic%2Fvalue")
    assert calls[0][0]["approved_addresses"] == ["8.8.8.8"]
    assert calls[0][5]["host"] == "idp.example.invalid"
    for changes in (
        {"suffix": "/../forbidden"},
        {"suffix": "/%2e%2e/forbidden"},
        {"content": b"x" * 1048577},
    ):
        with pytest.raises(CommandError):
            exchange(endpoint, "POST", transport=transport, **changes)
    with pytest.raises(CommandError):
        exchange(synthetic_endpoint(), "GET", transport=transport)
    assert len(calls) == 1
    with pytest.raises(CommandError):
        exchange(endpoint, "GET", transport=lambda *args: (302, {"location": "unsafe"}, b""))
    assert (
        exchange(
            endpoint,
            "POST",
            return_redirect=True,
            transport=lambda *args, **kwargs: (302, {"location": "unsafe"}, b""),
        )[0]
        == 302
    )


def test_f11_oidc_exchange_uses_authlib_pkce_and_only_approved_endpoints(oidc_signer):
    import hashlib
    from urllib.parse import parse_qs, urlsplit
    from uuid import uuid4

    from app.core.integration_http import oidc_authorization, oidc_exchange

    private, public = oidc_signer
    config = {
        "provider": "oidc",
        "emergency_admin_id": str(uuid4()),
        "revocation_window_seconds": 300,
        "jit_enabled": False,
        "jit_mappings": [],
        "issuer": "https://idp.example.invalid",
        "client_id": "synthetic-client",
        "authorization_endpoint": synthetic_endpoint(
            audience_approved=True, url="https://idp.example.invalid/authorize"
        ),
        "token_endpoint": synthetic_endpoint(
            audience_approved=True, url="https://idp.example.invalid/token"
        ),
        "jwks_endpoint": synthetic_endpoint(
            audience_approved=True, url="https://idp.example.invalid/jwks"
        ),
        "token_auth_method": "client_secret_basic",
    }
    redirect = "https://localhost:8443/api/v1/auth/sso/synthetic/callback"
    verifier, nonce, state = "v" * 43, "n" * 43, "s" * 43
    url = oidc_authorization(
        config, redirect_uri=redirect, state=state, nonce=nonce, verifier=verifier
    )
    query = parse_qs(urlsplit(url).query)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == [challenge.decode()]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [state] and query["nonce"] == [nonce]
    assert query["prompt"] == ["login"] and query["max_age"] == ["0"]
    calls = []

    def transport(network, host, port, method, target, headers, content, limit):
        calls.append((host, method, target))
        if target == "/token":
            form = parse_qs(content.decode())
            assert form["code_verifier"] == [verifier] and form["code"] == ["synthetic-code"]
            assert headers["authorization"].startswith("Basic ")
            body = {
                "access_token": "synthetic-access",
                "token_type": "Bearer",
                "id_token": synthetic_token(private),
                "refresh_token": "discard-this",
            }
        else:
            assert target == "/jwks" and method == "GET"
            assert "authorization" not in headers
            body = {"keys": [public]}
        return 200, {"content-type": "application/json"}, json.dumps(body).encode()

    identity = oidc_exchange(
        config,
        "synthetic-client-secret",
        redirect_uri=redirect,
        code="synthetic-code",
        verifier=verifier,
        nonce=nonce,
        transport=transport,
    )
    assert identity.subject == "synthetic-stable-subject" and not hasattr(identity, "refresh_token")
    assert calls == [
        ("idp.example.invalid", "POST", "/token"),
        ("idp.example.invalid", "GET", "/jwks"),
    ]


def test_f11_migration_is_forward_only_additive_and_keeps_historical_guards(monkeypatch):
    import ast
    import importlib.util
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    migration_path = root / "alembic/versions/20261126_0010_integrations.py"
    spec = importlib.util.spec_from_file_location("f11_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements = []
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(statement))
    migration.upgrade()
    assert migration.revision == "20261126_0010"
    assert migration.down_revision == "20261126_0009"
    assert len(migration.TABLES) == 9
    model_tree = ast.parse((root / "app/models/integrations.py").read_text(encoding="utf-8"))
    names = {
        assignment.value.value
        for definition in model_tree.body
        if isinstance(definition, ast.ClassDef)
        for assignment in definition.body
        if isinstance(assignment, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in assignment.targets
        )
    }
    assert names == set(migration.TABLES)
    assert set(migration.IMMUTABLE) | migration.APPEND_ONLY == names
    sql = "\n".join(statements)
    assert len(re.findall(r"CREATE TABLE ", sql)) == 9
    assert not re.search(r"\b(INSERT INTO|UPDATE\s+users|DROP TABLE|TRUNCATE TABLE)\b", sql)
    assert not re.search(r"CREATE OR REPLACE FUNCTION|DROP FUNCTION|DROP TRIGGER", sql)
    assert "pg_get_expr(conbin,conrelid)" in sql
    assert "audit_f8_record()" in sql
    assert "external_identity_id UUID" in sql
    assert "F11_SSO_ONE_USE" in sql and "F11_DELIVERY_FENCED" in sql
    assert "CHECK((outcome='ambiguous')=(status_code IS NULL))" in sql
    assert "IS NOT DISTINCT FROM provider" in sql
    assert "F11_REPLAY_IDENTITY" in sql and "F11_ATTEMPT_OUTCOME" in sql
    for table in names:
        assert f"CREATE TRIGGER protect_{table}" in sql
        assert f"CREATE TRIGGER truncate_{table}" in sql
        privileges = "SELECT,INSERT" if table in migration.APPEND_ONLY else "SELECT,INSERT,UPDATE"
        assert f"GRANT {privileges} ON {table} TO ocote_runtime" in sql
        assert "ON DELETE RESTRICT" in migration.TABLES[table][1]
    with pytest.raises(RuntimeError, match="cannot be discarded"):
        migration.downgrade()


@pytest.mark.parametrize(
    "url",
    [
        "http://idp.example.invalid/endpoint",
        "https://user:password@idp.example.invalid/endpoint",
        "https://idp.example.invalid/endpoint?secret=unsafe",
        "https://idp.example.invalid/endpoint#fragment",
        "https://other.example.invalid/endpoint",
        "https://idp.example.invalid:8443/endpoint",
        "https://idp.example.invalid/%2e%2e/endpoint",
        "https://idp.example.invalid/endpoint%0d%0aHeader",
        "https://idp.example.invalid\\@other.example.invalid/endpoint",
    ],
)
def test_f11_endpoint_rejects_unsafe_urls(url):
    from pydantic import ValidationError

    from app.schemas.integrations import HTTPSEndpoint

    with pytest.raises(ValidationError):
        HTTPSEndpoint.model_validate(synthetic_endpoint(url=url))


def test_f11_network_requires_explicit_private_approval_and_never_accepts_loopback():
    from pydantic import ValidationError

    from app.schemas.integrations import HTTPSEndpoint

    assert HTTPSEndpoint.model_validate(synthetic_endpoint()).audience_approved is False
    private = synthetic_endpoint(approved_addresses=["10.20.30.40"])
    with pytest.raises(ValidationError):
        HTTPSEndpoint.model_validate(private)
    assert HTTPSEndpoint.model_validate({**private, "allow_private_endpoint": True})
    with pytest.raises(ValidationError):
        HTTPSEndpoint.model_validate(
            synthetic_endpoint(approved_addresses=["127.0.0.1"], allow_private_endpoint=True)
        )
    with pytest.raises(ValidationError):
        HTTPSEndpoint.model_validate(synthetic_endpoint(verify_tls=False))


@pytest.mark.parametrize("role", ["admin", "gerente"])
def test_f11_jit_schema_never_accepts_privileged_role_mapping(role):
    from uuid import uuid4

    from pydantic import ValidationError

    from app.schemas.integrations import JITMapping

    with pytest.raises(ValidationError):
        JITMapping(attribute="groups", value="synthetic", role=role, department_id=uuid4())


def test_f11_oidc_config_has_no_implicit_jit_or_unapproved_fields():
    from uuid import uuid4

    from pydantic import TypeAdapter, ValidationError

    from app.schemas.integrations import ConnectorConfig, OIDCConfig

    values = {
        "provider": "oidc",
        "emergency_admin_id": str(uuid4()),
        "revocation_window_seconds": 300,
        "jit_enabled": False,
        "jit_mappings": [],
        "issuer": "https://idp.example.invalid",
        "client_id": "synthetic-client",
        "authorization_endpoint": synthetic_endpoint(),
        "token_endpoint": synthetic_endpoint(),
        "jwks_endpoint": synthetic_endpoint(),
        "token_auth_method": "client_secret_basic",
    }
    assert isinstance(TypeAdapter(ConnectorConfig).validate_python(values), OIDCConfig)
    for changes in ({"jit_enabled": True}, {"client_secret": "never-plaintext-config"}):
        with pytest.raises(ValidationError):
            OIDCConfig.model_validate({**values, **changes})


def test_f11_devops_requires_verified_provider_repository_inventory():
    from pydantic import ValidationError

    from app.schemas.integrations import DevOpsConfig

    values = {
        "provider": "github",
        "api_endpoint": synthetic_endpoint(host="api.github.com", url="https://api.github.com"),
        "web_origin": "https://github.com",
        "repositories": [{"repository_id": "123", "path": "synthetic/repository"}],
    }
    assert DevOpsConfig.model_validate(values)
    for changes in (
        {"web_origin": "https://github.com/other"},
        {"api_endpoint": synthetic_endpoint()},
        {"repositories": values["repositories"] * 2},
        {"repositories": [{"repository_id": "123", "path": "synthetic/../repository"}]},
        {"provider": "bitbucket"},
    ):
        with pytest.raises(ValidationError):
            DevOpsConfig.model_validate({**values, **changes})


def test_f11_external_link_does_not_accept_urls_or_task_mutations():
    from uuid import uuid4

    from pydantic import ValidationError

    from app.schemas.integrations import ExternalLinkWrite

    values = {
        "expected_version": 1,
        "integration_id": str(uuid4()),
        "repository_id": "123",
        "external_id": "14",
        "kind": "issue",
        "reason": "Synthetic external reference",
    }
    assert ExternalLinkWrite.model_validate(values)
    for changes in (
        {"url": "https://untrusted.example.invalid"},
        {"stage_id": str(uuid4())},
        {"progress": 100},
        {"due_date": "2026-12-01"},
        {"kind": "commit", "external_id": "main"},
    ):
        with pytest.raises(ValidationError):
            ExternalLinkWrite.model_validate({**values, **changes})


@pytest.fixture(scope="module")
def oidc_signer():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="synthetic-signing-key", use="sig", alg="RS256")
    return private, public


def synthetic_token(signer, **changes):
    moment = datetime.now(UTC)
    claims = {
        "iss": "https://idp.example.invalid",
        "sub": "synthetic-stable-subject",
        "aud": "synthetic-client",
        "iat": moment,
        "auth_time": int(moment.timestamp()),
        "exp": moment + timedelta(minutes=5),
        "nonce": "n" * 43,
        "email": "synthetic@example.invalid",
        "email_verified": True,
        "name": "Synthetic identity",
        **changes,
    }
    return jwt.encode(claims, signer, algorithm="RS256", headers={"kid": "synthetic-signing-key"})


def validate_oidc(encoded, public, **changes):
    return oidc_identity(
        encoded,
        {"keys": [public]},
        **{
            "issuer": "https://idp.example.invalid",
            "client_id": "synthetic-client",
            "nonce": "n" * 43,
            **changes,
        },
    )


def test_f11_oidc_projects_only_explicit_verified_flat_bounded_attributes(oidc_signer):
    private, public = oidc_signer
    encoded = synthetic_token(
        private, groups=["synthetic-team"], role="admin", arbitrary={"secret": "must-not-project"}
    )
    result = validate_oidc(encoded, public, attribute_names=("groups",))
    assert result.verified_attributes == (("groups", ("synthetic-team",)),)
    assert not hasattr(result, "role")
    assert validate_oidc(encoded, public).verified_attributes == ()
    for value in ({"nested": "not-allowed"}, [True], ["x" * 513], ["x"] * 101):
        with pytest.raises(CommandError):
            validate_oidc(
                synthetic_token(private, groups=value), public, attribute_names=("groups",)
            )


def test_f11_oidc_validates_signature_and_returns_identity_not_authority(oidc_signer):
    private, public = oidc_signer
    result = validate_oidc(
        synthetic_token(private, role="admin", department_id="untrusted-claim"), public
    )
    assert result.subject == "synthetic-stable-subject"
    assert result.issuer == "https://idp.example.invalid"
    assert result.verified_email == "synthetic@example.invalid"
    assert not hasattr(result, "role") and not hasattr(result, "department_id")
    assert not hasattr(result, "access_token")


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://other.example.invalid"},
        {"aud": "other-client"},
        {"nonce": "different-nonce"},
        {"exp": lambda: datetime.now(UTC) - timedelta(minutes=2)},
        {"iat": lambda: datetime.now(UTC) + timedelta(minutes=2)},
        {"auth_time": None},
        {"auth_time": True},
        {"auth_time": "untrusted"},
        {"auth_time": lambda: int((datetime.now(UTC) - timedelta(minutes=2)).timestamp())},
        {"auth_time": lambda: int((datetime.now(UTC) + timedelta(minutes=2)).timestamp())},
        {"sub": ""},
        {"sub": "subject\nforged"},
        {"aud": ["synthetic-client", "other-client"], "azp": "other-client"},
    ],
)
def test_f11_oidc_rejects_invalid_claims_without_leaking_details(oidc_signer, changes):
    private, public = oidc_signer
    changes = {key: value() if callable(value) else value for key, value in changes.items()}
    with pytest.raises(CommandError) as caught:
        validate_oidc(synthetic_token(private, **changes), public)
    assert caught.value.code == "FEDERATED_IDENTITY_INVALID"


def test_f11_oidc_rejects_untrusted_signature_duplicate_keys_and_remote_keys(oidc_signer):
    private, public = oidc_signer
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(CommandError):
        validate_oidc(synthetic_token(other), public)
    with pytest.raises(CommandError):
        oidc_identity(
            synthetic_token(private),
            {"keys": [public, public]},
            issuer="https://idp.example.invalid",
            client_id="synthetic-client",
            nonce="n" * 43,
        )
    unsafe = jwt.encode(
        {"sub": "synthetic"},
        private,
        algorithm="RS256",
        headers={"kid": public["kid"], "jku": "https://attacker.example.invalid/keys"},
    )
    with pytest.raises(CommandError):
        validate_oidc(unsafe, public)


def test_f11_oidc_does_not_promote_unverified_email(oidc_signer):
    private, public = oidc_signer
    result = validate_oidc(synthetic_token(private, email_verified="true"), public)
    assert result.verified_email is None


@pytest.mark.parametrize("value", [None, "", "short", "x" * 43, "\u00e9" * 43])
def test_f11_browser_correlation_requires_exact_bounded_ascii_value(value):
    assert not correlated(value, "n" * 43)
    assert correlated("n" * 43, "n" * 43)
    assert not correlated("n" * 300, "n" * 300)


@pytest.mark.parametrize(
    "content",
    [
        b"not XML",
        b'<!DOCTYPE Response SYSTEM "https://attacker.example.invalid/entity"><Response/>',
        b'<Response InResponseTo="_synthetic"/>',
        b'<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'InResponseTo="_other"/>',
        b'<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'InResponseTo="_synthetic"/>',
    ],
)
def test_f11_saml_rejects_untrusted_xml_and_missing_signed_assertions(content):
    with pytest.raises(CommandError) as caught:
        saml_identity(
            base64.b64encode(content).decode("ascii"),
            {},
            {},
            request_id="_synthetic",
            relay_state="r" * 43,
            expected_relay="r" * 43,
        )
    assert caught.value.code == "FEDERATED_IDENTITY_INVALID"


def test_f11_ldap_uses_library_escaping_and_fixed_attribute_allowlist():
    assert ldap_user_filter("uid", "*)(uid=*)") == r"(uid=\2a\29\28uid=\2a\29)"
    assert ldap_user_filter("sAMAccountName", "synthetic") == "(sAMAccountName=synthetic)"
    with pytest.raises(CommandError):
        ldap_user_filter("uid)(objectClass=*", "synthetic")


@pytest.fixture(scope="module")
def signed_saml_response():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from lxml import etree
    from onelogin.saml2.constants import OneLogin_Saml2_Constants
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    from app.core.federation import PERSISTENT_NAME_ID

    moment = datetime.now(UTC)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-idp.example.invalid")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(moment - timedelta(minutes=5))
        .not_valid_after(moment + timedelta(days=1))
        .sign(private, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    issuer = "https://idp.example.invalid/entity"
    audience = "https://localhost:8443/saml/synthetic"
    callback = "https://localhost:8443/api/v1/auth/sso/synthetic/callback"
    instant = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    expiry = (moment + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = (moment - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assertion = (
        '<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="_synthetic_assertion" Version="2.0" IssueInstant="{instant}">'
        f"<saml:Issuer>{issuer}</saml:Issuer><saml:Subject>"
        f'<saml:NameID Format="{PERSISTENT_NAME_ID}">stable-synthetic-id</saml:NameID>'
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData InResponseTo="_synthetic" Recipient="{callback}" '
        f'NotOnOrAfter="{expiry}"/></saml:SubjectConfirmation></saml:Subject>'
        f'<saml:Conditions NotBefore="{before}" NotOnOrAfter="{expiry}">'
        f"<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience>"
        "</saml:AudienceRestriction></saml:Conditions>"
        f'<saml:AuthnStatement AuthnInstant="{instant}" SessionIndex="_synthetic_session">'
        "<saml:AuthnContext><saml:AuthnContextClassRef>"
        "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"
        "</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>"
        "</saml:Assertion>"
    )
    signature_options = {
        "sign_algorithm": OneLogin_Saml2_Constants.RSA_SHA256,
        "digest_algorithm": OneLogin_Saml2_Constants.SHA256,
    }
    signed_assertion = OneLogin_Saml2_Utils.add_sign(
        assertion, private_pem, certificate, **signature_options
    )
    response = etree.fromstring(
        (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="_synthetic_response" Version="2.0" IssueInstant="{instant}" '
            f'Destination="{callback}" InResponseTo="_synthetic">'
            f"<saml:Issuer>{issuer}</saml:Issuer><samlp:Status>"
            '<samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
            "</samlp:Status></samlp:Response>"
        ).encode()
    )
    response.append(etree.fromstring(signed_assertion))
    signed = OneLogin_Saml2_Utils.add_sign(
        etree.tostring(response), private_pem, certificate, **signature_options
    )
    settings = {
        "sp": {
            "entityId": audience,
            "assertionConsumerService": {
                "url": callback,
                "binding": OneLogin_Saml2_Constants.BINDING_HTTP_POST,
            },
            "NameIDFormat": PERSISTENT_NAME_ID,
        },
        "idp": {
            "entityId": issuer,
            "singleSignOnService": {
                "url": "https://idp.example.invalid/sso",
                "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
            },
            "x509cert": certificate,
        },
    }
    request_data = {
        "https": "on",
        "http_host": "localhost:8443",
        "server_port": "8443",
        "script_name": "/api/v1/auth/sso/synthetic/callback",
        "get_data": {},
    }
    return signed, settings, request_data


def test_f11_saml_accepts_signed_correlated_assertion_and_exposes_replay_id(signed_saml_response):
    content, settings, request_data = signed_saml_response
    result = saml_identity(
        base64.b64encode(content).decode("ascii"),
        settings,
        request_data,
        request_id="_synthetic",
        relay_state="r" * 43,
        expected_relay="r" * 43,
    )
    assert result.subject == "stable-synthetic-id"
    assert result.assertion_id == "_synthetic_assertion"
    assert result.assertion_expires_at > datetime.now(UTC)
    assert result.verified_email is None


@pytest.mark.parametrize("corrupt", [True, False])
def test_f11_saml_rejects_tampering_or_wrong_browser_correlation(signed_saml_response, corrupt):
    content, settings, request_data = signed_saml_response
    if corrupt:
        content = content.replace(b"stable-synthetic-id", b"forged-synthetic-id")
    with pytest.raises(CommandError):
        saml_identity(
            base64.b64encode(content).decode("ascii"),
            settings,
            request_data,
            request_id="_synthetic",
            relay_state="r" * 43 if corrupt else "other-browser" * 4,
            expected_relay="r" * 43,
        )


def test_f11_service_key_has_explicit_public_identity_and_256bit_secret():
    import secrets
    from uuid import uuid4

    from app.core.integration_security import (
        key_digest,
        key_identifier,
        key_matches,
        new_service_key,
    )

    identifier = uuid4()
    encoded = new_service_key(identifier)
    pepper = secrets.token_bytes(32)
    digest = key_digest(encoded, pepper)
    assert key_identifier(encoded) == identifier and len(encoded.rsplit(".", 1)[1]) == 43
    assert key_matches(encoded, pepper, digest)
    assert not key_matches(encoded, secrets.token_bytes(32), digest)
    assert not key_matches(new_service_key(identifier), pepper, digest)
    assert not key_matches(encoded + "\n", pepper, digest)
    assert encoded not in digest and pepper.hex() not in digest


@pytest.mark.parametrize("scopes", [[], ["admin"], ["tasks:read", "tasks:read"], ["tasks:create"]])
def test_f11_service_key_scopes_are_allowlisted_and_subset_of_current_principal(scopes):
    from app.core.integration_security import validated_scopes

    with pytest.raises(CommandError):
        validated_scopes(scopes, ["tasks:read"])
    assert validated_scopes(["tasks:read"], ["tasks:read"]) == ["tasks:read"]


@pytest.mark.parametrize("days", [0, 0.5, 91])
def test_f11_service_key_requires_explicit_one_to_ninety_day_expiry(days):
    from app.core.integration_security import validate_key_expiry

    moment = datetime.now(UTC)
    with pytest.raises(CommandError):
        validate_key_expiry(moment, moment + timedelta(days=days))
    validate_key_expiry(moment, moment + timedelta(days=1))
    validate_key_expiry(moment, moment + timedelta(days=90))
    with pytest.raises(CommandError):
        validate_key_expiry(moment.replace(tzinfo=None), moment + timedelta(days=1))


def test_f11_service_key_cidr_uses_peer_address_and_fails_closed():
    from app.core.integration_security import client_ip_allowed

    assert client_ip_allowed("192.0.2.10", ["192.0.2.0/24"])
    assert client_ip_allowed("2001:db8::1", ["2001:db8::/32"])
    assert not client_ip_allowed("192.0.2.10", ["198.51.100.0/24"])
    assert not client_ip_allowed("192.0.2.10", ["192.0.2.9/24"])
    assert not client_ip_allowed("192.0.2.10", [])
    assert not client_ip_allowed("untrusted-forwarded-header", None)
    assert client_ip_allowed("192.0.2.10", None)


def test_f11_webhook_signature_covers_timestamp_and_exact_body_bytes():
    import hashlib
    import hmac
    import secrets

    from app.core.integration_security import valid_webhook_signature, webhook_signature

    secret = secrets.token_bytes(32)
    content = b'{"event_id":"synthetic","schema_version":1}'
    stamp = 1800000000
    signature = webhook_signature(secret, stamp, content)
    assert (
        signature == "v1=" + hmac.new(secret, b"1800000000." + content, hashlib.sha256).hexdigest()
    )
    assert valid_webhook_signature(secret, stamp, content, signature, current_time=stamp + 300)
    for changed in (content + b" ", b'{"schema_version":1,"event_id":"synthetic"}'):
        assert not valid_webhook_signature(secret, stamp, changed, signature, current_time=stamp)
    assert not valid_webhook_signature(secret, stamp + 1, content, signature, current_time=stamp)
    assert not valid_webhook_signature(secret, stamp, content, signature, current_time=stamp + 301)
    assert not valid_webhook_signature(secret, stamp, content, signature, current_time=stamp - 301)
    assert not valid_webhook_signature(secret, stamp, content, "v1=invalid", current_time=stamp)
