import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils
from sqlalchemy import func, select

from app.core.errors import CommandError
from app.core.federation import (
    PERSISTENT_NAME_ID,
    FederatedIdentity,
    correlated,
    identity_text,
    ldap_identity,
    saml_identity,
)
from app.core.integration_http import oidc_authorization, oidc_exchange
from app.core.security import now
from app.models.identity import RefreshSession, User
from app.models.integrations import ExternalIdentity, SSOAssertionUse, SSOTransaction
from app.models.platform import (
    EncryptedSecret,
    IntegrationConfig,
    IntegrationHealthCheck,
    SecretKeyVersion,
)
from app.schemas.identity import Email
from app.schemas.integrations import SSOStart
from app.services import identity, integrations, platform
from app.services.administration import check_version, department_for_user
from app.services.enterprise import (
    enabled,
    policy,
    reauthenticate,
    require_module,
    require_page_size,
)

COOKIE_PATH = "/api/v1/auth/sso"


def browser_cookie(transaction_id):
    return "ocote_sso_" + transaction_id.hex


def fingerprint(value):
    if not isinstance(value, str) or not correlated(value, value):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def sso_modules(db):
    require_module(db, "integrations")
    require_module(db, "sso")
    policy(db)


def providers(db, limit, cursor=None):
    if not all(enabled(db, code) for code in ("integrations", "sso")):
        return {"items": [], "next_cursor": None}
    require_page_size(db, limit)
    query = select(IntegrationConfig).where(IntegrationConfig.kind == "sso",
                                             IntegrationConfig.is_active)
    if cursor:
        query = query.where(IntegrationConfig.id > cursor)
    rows = list(db.scalars(query.order_by(IntegrationConfig.id).limit(limit + 1)))
    return {"items": [{key: getattr(record, key) for key in ("id", "name", "provider")}
                       for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def configured(db, identity, *, lock=False, allow_inactive=False):
    record = integrations.connector_for(db, identity, lock=lock)
    if record.kind != "sso" or (not allow_inactive and not record.is_active):
        raise CommandError(404, "SSO_PROVIDER_UNAVAILABLE")
    return record


def changed(db, record, request, event, actor=None):
    db.add(record)
    identity.audit(
        db,
        request,
        event,
        actor=actor,
        entity=record.__tablename__,
        entity_id=record.id,
        after={"version": record.version},
    )
    db.flush()


def encrypt_context(db, owner, context, request, *, secret_version=1):
    crypt = platform.vault(db, request)
    key = db.scalar(
        select(SecretKeyVersion)
        .where(SecretKeyVersion.purpose == "sso_context")
        .order_by(SecretKeyVersion.epoch.desc())
        .limit(1)
    )
    if key is None:
        key = platform.new_key(db, crypt, "sso_context", 1)
    plaintext = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    if len(plaintext) > 16384:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    encrypted = crypt.encrypt(platform.wrapped(key), owner, secret_version, plaintext)
    secret = EncryptedSecret(
        id=uuid4(),
        owner_id=owner,
        purpose="sso_context",
        secret_version=secret_version,
        key_id=encrypted.key_id,
        nonce=encrypted.nonce,
        ciphertext=encrypted.ciphertext,
    )
    db.add(secret)
    db.flush([secret])
    return secret.id


def decrypt_context(db, transaction, request):
    value = integrations.decrypted_secret(
        db, transaction.id, transaction.context_secret_id, "sso_context", request
    )
    try:
        context = json.loads(value)
        if not isinstance(context, dict) or set(context) - {
            "nonce", "verifier", "request_id", "probe"
        }:
            raise ValueError
        return context
    except (ValueError, TypeError):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None


def callback_url(tokens, integration_id):
    return tokens.settings.auth_origin + "/api/v1/auth/sso/" + str(integration_id) + "/callback"


def saml_settings(config, credential, tokens, integration_id):
    callback = callback_url(tokens, integration_id)
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": tokens.settings.auth_origin + "/saml/" + str(integration_id),
            "assertionConsumerService": {
                "url": callback,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": PERSISTENT_NAME_ID,
            "x509cert": config.sp_certificate_pem,
            "privateKey": credential,
        },
        "idp": {
            "entityId": config.entity_id,
            "singleSignOnService": {
                "url": config.sso_endpoint.url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config.idp_certificate_pem,
        },
        "security": {
            "authnRequestsSigned": True,
            "wantAssertionsSigned": True,
            "wantMessagesSigned": True,
            "wantNameId": True,
            "wantAttributeStatement": False,
            "signatureAlgorithm": OneLogin_Saml2_Utils.RSA_SHA256,
            "digestAlgorithm": OneLogin_Saml2_Utils.SHA256,
        },
    }


def saml_request(tokens, integration_id):
    callback = urlsplit(callback_url(tokens, integration_id))
    return {
        "https": "on",
        "http_host": callback.netloc,
        "script_name": callback.path,
        "get_data": {},
    }


def start(db, tokens, request, integration_id, body, actor=None, *, probe=None):
    identity.origin(request, tokens)
    sso_modules(db)
    if body.purpose == "probe":
        integrations.administrator(actor)
        if probe is None:
            raise CommandError(401, "SSO_PROBE_REAUTHENTICATION_REQUIRED")
    record = configured(db, integration_id, allow_inactive=body.purpose == "probe")
    config, credential = integrations.connector_material(db, record, request)
    request.app.state.login_limiter.check(
        "sso:" + str(integration_id), request.client.host if request.client else "local"
    )
    if body.purpose == "bind":
        if actor is None or not actor.is_active:
            raise CommandError(401, "INVALID_CREDENTIALS")
        reauthenticate(db, actor, body, request)
    endpoints = integrations.connector_endpoints(config)
    if not all(endpoint.audience_approved for endpoint in endpoints):
        raise CommandError(422, "EXPLICIT_AUDIENCE_AND_DESTINATION_REQUIRED")
    rate = min(endpoint.rate_per_minute for endpoint in endpoints)
    recent = db.scalar(
        select(func.count())
        .select_from(SSOTransaction)
        .where(
            SSOTransaction.integration_id == record.id,
            SSOTransaction.created_at >= now() - timedelta(minutes=1),
        )
    )
    if recent >= rate:
        raise CommandError(429, "SSO_RATE_LIMIT")
    identity_id, issued = uuid4(), now()
    state, nonce, verifier, browser = (secrets.token_urlsafe(32) for _ in range(4))
    context = {"nonce": nonce, "verifier": verifier}
    if probe is not None:
        context["probe"] = probe
    url = None
    if config.provider == "oidc":
        url = oidc_authorization(
            config,
            redirect_uri=callback_url(tokens, record.id),
            state=state,
            nonce=nonce,
            verifier=verifier,
        )
    elif config.provider == "saml":
        authentication = OneLogin_Saml2_Auth(
            saml_request(tokens, record.id),
            old_settings=saml_settings(config, credential, tokens, record.id),
        )
        url = authentication.login(return_to=state, force_authn=True, set_nameid_policy=True)
        context["request_id"] = authentication.get_last_request_id()
    transaction = SSOTransaction(
        id=identity_id,
        version=1,
        created_at=issued,
        updated_at=issued,
        integration_id=record.id,
        config_revision=record.config_revision,
        purpose=body.purpose,
        initiating_user_id=actor.id if body.purpose in {"bind", "probe"} else None,
        state_hash=fingerprint(state),
        browser_hash=fingerprint(browser),
        context_secret_id=encrypt_context(db, identity_id, context, request),
        state="pending",
        expires_at=issued + timedelta(minutes=5),
        issuer=None,
        subject=None,
        authenticated_at=None,
        consumed_at=None,
    )
    changed(db, transaction, request, "federation_started", actor.id if actor else None)
    return (
        {
            "transaction_id": transaction.id,
            "authorization_url": url,
            "expires_at": transaction.expires_at,
        },
        browser,
        state,
    )


def pending(db, integration_id, state, *, lock=False):
    transaction = db.scalar(
        select(SSOTransaction)
        .where(
            SSOTransaction.integration_id == integration_id,
            SSOTransaction.state_hash == fingerprint(state),
        )
        .with_for_update()
        if lock
        else select(SSOTransaction).where(
            SSOTransaction.integration_id == integration_id,
            SSOTransaction.state_hash == fingerprint(state),
        )
    )
    if transaction is None or transaction.state != "pending" or transaction.expires_at <= now():
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    return transaction


def verified(db, transaction, identity_result, request, *, profile=None):
    if transaction.state != "pending" or transaction.expires_at <= now():
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    if identity_result.assertion_id is not None:
        db.add(
            SSOAssertionUse(
                id=uuid4(),
                integration_id=transaction.integration_id,
                transaction_id=transaction.id,
                assertion_id=identity_result.assertion_id,
                expires_at=identity_result.assertion_expires_at,
            )
        )
        db.flush()
    if profile is not None:
        encrypt_context(db, transaction.id, {"profile": profile}, request, secret_version=2)
    transaction.state, transaction.issuer, transaction.subject = (
        "verified",
        identity_result.issuer,
        identity_result.subject,
    )
    transaction.authenticated_at = now()
    identity.touch(transaction)
    changed(db, transaction, request, "federation_verified", transaction.initiating_user_id)


def failed(db, transaction, request):
    transaction.state = "failed"
    identity.touch(transaction)
    if transaction.purpose == "probe":
        db.add(IntegrationHealthCheck(
            id=uuid4(), created_at=now(), integration_id=transaction.integration_id,
            config_version=transaction.config_revision, status="failed",
            result_code="F11_SSO_PROBE_FAILED", actor_id=transaction.initiating_user_id,
            request_id=UUID(request.state.request_id),
        ))
    changed(db, transaction, request, "federation_failed", transaction.initiating_user_id)
    raise CommandError(401, "FEDERATED_IDENTITY_INVALID", persist=True)


def callback(db, tokens, request, integration_id, state, *, code=None, response=None):
    sso_modules(db)
    transaction = pending(db, integration_id, state, lock=True)
    record = configured(db, integration_id, allow_inactive=transaction.purpose == "probe")
    if record.config_revision != transaction.config_revision:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    config, credential = integrations.connector_material(db, record, request)
    context = decrypt_context(db, transaction, request)
    transaction_id, prepared_version = transaction.id, transaction.version
    db.commit()
    valid, result = False, None
    try:
        if config.provider == "oidc":
            result = oidc_exchange(
                config,
                credential,
                redirect_uri=callback_url(tokens, integration_id),
                code=code,
                verifier=context["verifier"],
                nonce=context["nonce"],
                transport=getattr(request.app.state, "integration_transport", None),
            )
        elif config.provider == "saml":
            result = saml_identity(
                response,
                saml_settings(config, credential, tokens, integration_id),
                saml_request(tokens, integration_id),
                request_id=context["request_id"],
                relay_state=state,
                expected_relay=state,
                attribute_names=config.attribute_names,
            )
        else:
            raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
        profile = jit_profile(config, result)
        valid = True
    except (CommandError, ValueError, TypeError, KeyError):
        pass
    finally:
        credential = None
    db.expire_all()
    db.info.pop("f8_flags", None)
    db.info.pop("f8_policy", None)
    identity.config_lock(db)
    sso_modules(db)
    transaction = db.get(
        SSOTransaction, transaction_id, with_for_update=True, populate_existing=True
    )
    if transaction is None:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    current = configured(db, integration_id, allow_inactive=transaction.purpose == "probe")
    if (
        transaction.state != "pending"
        or transaction.version != prepared_version
        or transaction.expires_at <= now()
        or current.config_revision != transaction.config_revision
    ):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    if not valid:
        failed(db, transaction, request)
    verified(db, transaction, result, request, profile=profile)
    return transaction.id


def ldap_callback(db, tokens, request, integration_id, state, browser, body):
    identity.origin(request, tokens)
    sso_modules(db)
    transaction = pending(db, integration_id, state, lock=True)
    if not hmac.compare_digest(transaction.browser_hash, fingerprint(browser)):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    record = configured(db, integration_id, allow_inactive=transaction.purpose == "probe")
    config, credential = integrations.connector_material(db, record, request)
    if config.provider != "ldap" or record.config_revision != transaction.config_revision:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    request.app.state.login_limiter.check(
        "ldap:" + str(integration_id) + ":" + body.username,
        request.client.host if request.client else "local",
    )
    transaction_id, prepared_version = transaction.id, transaction.version
    db.commit()
    result = None
    try:
        result = ldap_identity(
            config,
            credential,
            body.username,
            body.password.get_secret_value(),
            connection_factory=getattr(request.app.state, "ldap_connection_factory", None),
        )
        profile = jit_profile(config, result)
    except CommandError:
        result = None
    finally:
        credential = None
    db.expire_all()
    db.info.pop("f8_flags", None)
    db.info.pop("f8_policy", None)
    identity.config_lock(db)
    sso_modules(db)
    transaction = db.get(
        SSOTransaction, transaction_id, with_for_update=True, populate_existing=True
    )
    if transaction is None:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    current = configured(db, integration_id, allow_inactive=transaction.purpose == "probe")
    if (
        transaction.state != "pending"
        or transaction.version != prepared_version
        or transaction.expires_at <= now()
        or current.config_revision != transaction.config_revision
    ):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    if result is None:
        failed(db, transaction, request)
    verified(db, transaction, result, request, profile=profile)
    return transaction.id


def jit_profile(config, result):
    if not config.jit_enabled:
        return None
    try:
        from pydantic import TypeAdapter

        attributes = dict(result.verified_attributes)
        if set(attributes) - set(config.attribute_names):
            raise ValueError
        jit_target(config, attributes)
        emails, names = (
            attributes.get(config.jit_email_attribute),
            attributes.get(config.jit_name_attribute),
        )
        if emails is None or names is None or len(emails) != 1 or len(names) != 1:
            raise ValueError
        if config.provider == "oidc" and (
            result.verified_email is None or emails[0].lower() != result.verified_email.lower()
        ):
            raise ValueError
        profile = {
            "email": TypeAdapter(Email).validate_python(emails[0]).lower(),
            "display_name": identity_text(names[0], 120),
            "attributes": attributes,
        }
        if len(json.dumps({"profile": profile}).encode()) > 16384:
            raise ValueError
        return profile
    except (ValueError, TypeError):
        raise CommandError(401, "SSO_JIT_PROFILE_INVALID") from None


def jit_target(config, verified_attributes):
    if not config.jit_enabled or not isinstance(verified_attributes, dict):
        raise CommandError(401, "SSO_JIT_MAPPING_REQUIRED")
    targets = set()
    for mapping in config.jit_mappings:
        values = verified_attributes.get(mapping.attribute, ())
        if not isinstance(values, (tuple, list)) or not all(
            isinstance(value, str) and 1 <= len(value) <= 512 for value in values
        ):
            raise CommandError(401, "SSO_JIT_MAPPING_INVALID")
        if mapping.value in values:
            if mapping.role not in {"lider", "colaborador"} or mapping.department_id is None:
                raise CommandError(401, "SSO_JIT_MAPPING_INVALID")
            targets.add((mapping.role, mapping.department_id))
    if len(targets) != 1:
        raise CommandError(401, "SSO_JIT_MAPPING_AMBIGUOUS")
    return next(iter(targets))


def sso_proof_code(record, config, emergency):
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "integration_id": str(record.id),
                "revision": record.config_revision,
                "config": config.model_dump(mode="json"),
                "emergency_id": str(emergency.id),
                "emergency_token_version": emergency.token_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return ("F11_SSO_JIT_OK:" if config.jit_enabled else "F11_SSO_OK:") + fingerprint


def transaction_profile(db, config, transaction, request):
    secret = db.scalar(select(EncryptedSecret).where(
        EncryptedSecret.owner_id == transaction.id, EncryptedSecret.purpose == "sso_context",
        EncryptedSecret.secret_version == 2,
    ))
    if secret is None:
        raise CommandError(401, "SSO_JIT_PROFILE_INVALID")
    try:
        envelope = json.loads(integrations.decrypted_secret(
            db, transaction.id, secret.id, "sso_context", request
        ))
        if not isinstance(envelope, dict) or set(envelope) != {"profile"}:
            raise ValueError
        stored = envelope["profile"]
        result = FederatedIdentity(
            transaction.issuer, transaction.subject, stored["email"], stored["display_name"],
            verified_attributes=tuple(stored["attributes"].items()),
        )
        profile = jit_profile(config, result)
        if json.dumps(profile, sort_keys=True) != json.dumps(stored, sort_keys=True):
            raise ValueError
        return profile
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CommandError(401, "SSO_JIT_PROFILE_INVALID") from None


def jit_user(db, record, config, transaction, request):
    emergency = db.get(User, config.emergency_admin_id)
    if (
        not config.jit_enabled
        or record.tested_version != record.config_revision
        or record.tested_at is None
        or emergency is None
        or not emergency.is_active
        or emergency.role != "admin"
        or (getattr(emergency, "locked_until", None) is not None and emergency.locked_until > now())
    ):
        raise CommandError(401, "SSO_JIT_PROOF_REQUIRED")
    proof = db.scalar(
        select(IntegrationHealthCheck.id)
        .where(
            IntegrationHealthCheck.integration_id == record.id,
            IntegrationHealthCheck.config_version == record.config_revision,
            IntegrationHealthCheck.status == "passed",
            IntegrationHealthCheck.result_code == sso_proof_code(record, config, emergency),
        )
        .limit(1)
    )
    if proof is None:
        raise CommandError(401, "SSO_JIT_PROOF_REQUIRED")
    profile = transaction_profile(db, config, transaction, request)
    role, department = jit_target(config, profile["attributes"])
    if record.scope_kind == "department" and record.department_id != department:
        raise CommandError(403, "SSO_DEPARTMENT_SCOPE_DENIED")
    department_for_user(db, role, department)
    if db.scalar(select(User.id).where(User.email == profile["email"])) is not None:
        raise CommandError(409, "SSO_JIT_EXISTING_ACCOUNT_REQUIRES_BINDING")
    moment = now()
    user = User(
        id=uuid4(),
        version=1,
        created_at=moment,
        updated_at=moment,
        email=profile["email"],
        display_name=profile["display_name"],
        role=role,
        department_id=department,
        is_active=True,
        token_version=1,
        password_hash=identity.PASSWORDS.hash(secrets.token_urlsafe(64)),
    )
    db.add(user)
    db.flush()
    identity.audit(
        db,
        request,
        "user_created",
        actor=user.id,
        entity="users",
        entity_id=user.id,
        after={"version": 1, "role": role, "department_id": str(department), "jit": True},
    )
    link = ExternalIdentity(
        id=uuid4(),
        version=1,
        created_at=moment,
        updated_at=moment,
        integration_id=record.id,
        user_id=user.id,
        created_by=user.id,
        issuer=transaction.issuer,
        subject=transaction.subject,
        last_authenticated_at=moment,
        revoked_at=None,
    )
    changed(db, link, request, "external_identity_provisioned", user.id)
    return link


def start_probe(db, tokens, request, integration_id, body, actor):
    identity.origin(request, tokens)
    integrations.administrator(actor)
    reauthenticate(db, actor, body, request)
    integrations.administrator(actor)
    sso_modules(db)
    record = configured(db, integration_id, lock=True, allow_inactive=True)
    check_version(record, body.expected_version)
    config = integrations.CONFIG.validate_python(record.config)
    if body.revocation_confirmed is not True or body.emergency_password is None:
        raise CommandError(422, "SSO_EMERGENCY_AND_REVOCATION_CONFIRMATION_REQUIRED")
    if config.provider == "ldap":
        if body.test_username is None or body.test_password is None:
            raise CommandError(422, "SSO_EXPLICIT_TEST_IDENTITY_REQUIRED")
    elif body.test_username is not None or body.test_password is not None:
        raise CommandError(422, "SSO_BROWSER_IDENTITY_REQUIRED")
    emergency = db.get(User, config.emergency_admin_id, with_for_update=True,
                       populate_existing=True)
    integrations.administrator(emergency)
    reauthenticate(db, emergency, body.model_copy(update={
        "current_password": body.emergency_password
    }), request)
    integrations.administrator(emergency)
    context = {"proof_code": sso_proof_code(record, config, emergency),
               "actor_version": actor.token_version, "reason": body.reason}
    record.is_active = False
    record.tested_version = record.tested_at = None
    identity.touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, body.reason, ["probe_started"]
    )
    db.flush()
    command = SSOStart(purpose="probe", current_password=body.current_password)
    result, browser, state = start(
        db, tokens, request, integration_id, command, actor, probe=context
    )
    if config.provider == "ldap":
        from app.schemas.integrations import LDAPLogin

        ldap_callback(db, tokens, request, integration_id, state, browser, LDAPLogin(
            transaction_id=result["transaction_id"], state=state,
            username=body.test_username, password=body.test_password,
        ))
        result["ready"] = True
    return result, browser


def probe_finished(db, tokens, request, record, config, transaction, actor):
    integrations.administrator(actor)
    if actor.id != transaction.initiating_user_id:
        raise CommandError(403, "SSO_PROBE_ACTOR_REQUIRED")
    context = decrypt_context(db, transaction, request).get("probe")
    emergency = db.get(User, config.emergency_admin_id, populate_existing=True)
    integrations.administrator(emergency)
    if getattr(emergency, "locked_until", None) is not None and emergency.locked_until > now():
        raise CommandError(409, "SSO_LOCAL_EMERGENCY_UNAVAILABLE")
    code = sso_proof_code(record, config, emergency)
    if (
        not isinstance(context, dict) or context.get("proof_code") != code
        or context.get("actor_version") != actor.token_version
    ):
        raise CommandError(409, "SSO_PROBE_CONTEXT_CHANGED")
    if config.jit_enabled:
        profile = transaction_profile(db, config, transaction, request)
        role, department = jit_target(config, profile["attributes"])
        if record.scope_kind == "department" and record.department_id != department:
            raise CommandError(403, "SSO_DEPARTMENT_SCOPE_DENIED")
        department_for_user(db, role, department)
    check = IntegrationHealthCheck(
        id=uuid4(), created_at=now(), integration_id=record.id,
        config_version=record.config_revision, status="passed", result_code=code,
        actor_id=actor.id, request_id=UUID(request.state.request_id),
    )
    db.add(check)
    db.flush([check])
    record.tested_version, record.tested_at = record.config_revision, now()
    record.is_active = False
    identity.touch(record)
    record.configuration_revision_id = platform.revision(
        db, request, actor, record, context["reason"], ["probe_passed"]
    )
    db.flush()
    return integrations.connector_view(record) | {"passed": True, "result_code": code}


def binding_view(record):
    return {
        name: getattr(record, name)
        for name in (
            "id",
            "version",
            "integration_id",
            "user_id",
            "issuer",
            "subject",
            "created_at",
            "last_authenticated_at",
            "revoked_at",
        )
    }


def bindings(db, actor, limit, cursor=None, user_id=None):
    sso_modules(db)
    require_page_size(db, limit)
    if not actor.is_active:
        raise CommandError(401, "INVALID_CREDENTIALS")
    if actor.role != "admin":
        if user_id is not None and user_id != actor.id:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        user_id = actor.id
    query = select(ExternalIdentity)
    if user_id is not None:
        query = query.where(ExternalIdentity.user_id == user_id)
    if cursor:
        query = query.where(ExternalIdentity.id > cursor)
    rows = list(db.scalars(query.order_by(ExternalIdentity.id).limit(limit + 1)))
    return {
        "items": [binding_view(record) for record in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


def revoke_binding(db, binding_id, body, request, actor):
    reauthenticate(db, actor, body, request)
    sso_modules(db)
    record = db.get(ExternalIdentity, binding_id, with_for_update=True, populate_existing=True)
    if record is None or (record.user_id != actor.id and actor.role != "admin"):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.revoked_at is None:
        record.revoked_at = now()
        identity.touch(record)
        changed(db, record, request, "external_identity_revoked", actor.id)
        db.execute(
            RefreshSession.__table__.update()
            .where(
                RefreshSession.external_identity_id == record.id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=record.revoked_at)
        )
    return binding_view(record)


def completion_allowed(transaction, browser, moment):
    if (
        transaction is None
        or transaction.state != "verified"
        or transaction.expires_at <= moment
        or transaction.consumed_at is not None
        or not hmac.compare_digest(transaction.browser_hash, fingerprint(browser))
    ):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")


def completion_status(db, tokens, request, transaction_id, browser):
    identity.origin(request, tokens)
    sso_modules(db)
    transaction = db.get(SSOTransaction, transaction_id, populate_existing=True)
    completion_allowed(transaction, browser, now())
    record = configured(db, transaction.integration_id,
                        allow_inactive=transaction.purpose == "probe")
    if record.config_revision != transaction.config_revision:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    return {"transaction_id": transaction.id, "purpose": transaction.purpose,
            "provider_name": record.name, "expires_at": transaction.expires_at}


def finish(db, tokens, request, transaction_id, browser, actor=None, *, purpose=None):
    identity.origin(request, tokens)
    sso_modules(db)
    transaction = db.get(
        SSOTransaction, transaction_id, with_for_update=True, populate_existing=True
    )
    completion_allowed(transaction, browser, now())
    if purpose is not None and transaction.purpose != purpose:
        raise CommandError(401, "SSO_PURPOSE_MISMATCH")
    record = configured(db, transaction.integration_id,
                        allow_inactive=transaction.purpose == "probe")
    config = integrations.CONFIG.validate_python(record.config)
    if record.config_revision != transaction.config_revision:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    link = db.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.issuer == transaction.issuer,
            ExternalIdentity.subject == transaction.subject,
        )
        .with_for_update()
    )
    if transaction.purpose == "probe":
        refresh, result = None, probe_finished(
            db, tokens, request, record, config, transaction, actor
        )
    elif transaction.purpose == "bind":
        if actor is None or not actor.is_active or actor.id != transaction.initiating_user_id:
            raise CommandError(401, "INVALID_CREDENTIALS")
        if record.scope_kind == "department" and actor.department_id != record.department_id:
            raise CommandError(403, "SSO_DEPARTMENT_SCOPE_DENIED")
        if link is not None and (
            link.user_id != actor.id
            or link.integration_id != record.id
            or link.revoked_at is not None
        ):
            raise CommandError(409, "EXTERNAL_IDENTITY_ALREADY_BOUND")
        if link is None:
            moment = now()
            link = ExternalIdentity(
                id=uuid4(),
                version=1,
                created_at=moment,
                updated_at=moment,
                integration_id=record.id,
                user_id=actor.id,
                created_by=actor.id,
                issuer=transaction.issuer,
                subject=transaction.subject,
                last_authenticated_at=moment,
                revoked_at=None,
            )
            changed(db, link, request, "external_identity_bound", actor.id)
        refresh, result = None, {"bound": True, "identity_id": link.id}
    elif transaction.purpose == "login":
        if link is None and config.jit_enabled:
            link = jit_user(db, record, config, transaction, request)
        if link is None or link.integration_id != record.id or link.revoked_at is not None:
            raise CommandError(401, "EXTERNAL_IDENTITY_NOT_BOUND")
        user = db.get(User, link.user_id, with_for_update=True, populate_existing=True)
        if user is None or not user.is_active:
            raise CommandError(401, "INVALID_CREDENTIALS")
        if record.scope_kind == "department" and user.department_id != record.department_id:
            raise CommandError(403, "SSO_DEPARTMENT_SCOPE_DENIED")
        settings = policy(db)
        deadline = transaction.authenticated_at + timedelta(
            seconds=config.revocation_window_seconds
        )
        if deadline <= now():
            raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
        family = uuid4()
        session, refresh, result = identity.session_response(
            db,
            tokens,
            user,
            family,
            min(deadline, now() + timedelta(seconds=settings.refresh_absolute_seconds)),
            external_identity_id=link.id,
            federated_authenticated_at=transaction.authenticated_at,
            federated_revocation_deadline=deadline,
        )
        link.last_authenticated_at = now()
        identity.touch(link)
        changed(db, link, request, "external_identity_authenticated", user.id)
        identity.audit(db, request, "login_success", actor=user.id, entity_id=session.family_id)
    else:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    transaction.state, transaction.consumed_at = "consumed", now()
    identity.touch(transaction)
    changed(db, transaction, request, "federation_consumed", transaction.initiating_user_id)
    return refresh, result


def session_allowed(db, session):
    external_id = getattr(session, "external_identity_id", None)
    if external_id is None:
        return
    moment = now()
    if (
        session.federated_authenticated_at is None
        or session.federated_revocation_deadline is None
        or session.federated_revocation_deadline <= moment
    ):
        raise CommandError(401, "FEDERATED_SESSION_EXPIRED")
    sso_modules(db)
    link = db.get(ExternalIdentity, external_id)
    if link is None or link.revoked_at is not None or link.user_id != session.user_id:
        raise CommandError(401, "FEDERATED_SESSION_REVOKED")
    provider = db.get(IntegrationConfig, link.integration_id)
    if provider is None or provider.kind != "sso" or not provider.is_active:
        raise CommandError(401, "FEDERATED_SESSION_REVOKED")
    config = integrations.CONFIG.validate_python(provider.config)
    if moment >= session.federated_authenticated_at + timedelta(
        seconds=config.revocation_window_seconds
    ):
        raise CommandError(401, "FEDERATED_SESSION_EXPIRED")
    owner = db.get(User, session.user_id)
    if (
        owner is None
        or not owner.is_active
        or (provider.scope_kind == "department" and provider.department_id != owner.department_id)
    ):
        raise CommandError(401, "FEDERATED_SESSION_REVOKED")
