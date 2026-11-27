import base64
import binascii
import hmac
import ssl
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import jwt
from authlib.oidc.core import CodeIDToken
from cryptography import x509
from ldap3 import NONE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.tls import check_hostname
from ldap3.utils.conv import escape_filter_chars
from lxml import etree
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from app.core.errors import CommandError
from app.core.object_storage import checked_addresses

PERSISTENT_NAME_ID = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
SAML_RESPONSE = "{urn:oasis:names:tc:SAML:2.0:protocol}Response"


@dataclass(frozen=True)
class FederatedIdentity:
    issuer: str
    subject: str
    verified_email: str | None
    display_name: str | None
    assertion_id: str | None = None
    assertion_expires_at: datetime | None = None
    verified_attributes: tuple[tuple[str, tuple[str, ...]], ...] = ()


def identity_text(value, maximum=512):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("Invalid identity attribute")
    return value


def correlated(received, expected):
    return (
        isinstance(received, str)
        and isinstance(expected, str)
        and 32 <= len(expected) <= 256
        and received.isascii()
        and expected.isascii()
        and hmac.compare_digest(received, expected)
    )


def fresh_authentication(value, moment):
    if type(value) not in {int, float} or not (
        moment.timestamp() - 30 <= value <= moment.timestamp() + 30
    ):
        raise ValueError("A fresh signed authentication instant is required")


def mapped_attributes(values, names):
    if not isinstance(values, dict) or not isinstance(names, (list, tuple)) or len(names) > 22:
        raise ValueError("Invalid verified attribute projection")
    selected = []
    for name in sorted(set(names)):
        identity_text(name, 120)
        if name not in values:
            continue
        items = [values[name]] if isinstance(values[name], str) else values[name]
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 100:
            raise ValueError("Invalid verified attribute values")
        selected.append((name, tuple(identity_text(value, 512) for value in items)))
    return tuple(selected)


def oidc_identity(
    encoded, jwks, *, issuer, client_id, nonce, access_token=None, attribute_names=(),
):
    try:
        if not isinstance(encoded, str) or not 1 <= len(encoded) <= 16384:
            raise ValueError("Invalid token size")
        identity_text(nonce, 256)
        header = jwt.get_unverified_header(encoded)
        if (
            header.get("alg") not in {"RS256", "PS256", "ES256"}
            or header.get("typ", "JWT") != "JWT"
            or any(name in header for name in ("jku", "jwk", "x5u", "crit"))
            or not isinstance(jwks, dict)
            or not isinstance(jwks.get("keys"), list)
            or not 1 <= len(jwks["keys"]) <= 32
        ):
            raise ValueError("Invalid token metadata")
        key_id = identity_text(header.get("kid"), 200)
        matches = [
            key for key in jwks["keys"] if isinstance(key, dict) and key.get("kid") == key_id
        ]
        if len(matches) != 1:
            raise ValueError("Ambiguous signing key")
        selected = matches[0]
        if (
            selected.get("use", "sig") != "sig"
            or "d" in selected
            or selected.get("alg", header["alg"]) != header["alg"]
            or "verify" not in selected.get("key_ops", ["verify"])
        ):
            raise ValueError("Invalid signing key")
        key = jwt.PyJWK.from_dict(selected, algorithm=header["alg"])
        if selected.get("kty") == "RSA" and key.key.key_size < 2048:
            raise ValueError("Insufficient signing key strength")
        claims = jwt.decode(
            encoded,
            key.key,
            algorithms=[header["alg"]],
            issuer=issuer,
            audience=client_id,
            leeway=30,
            options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce", "auth_time"]},
        )
        if not correlated(claims.get("nonce"), nonce):
            raise ValueError("Invalid nonce")
        fresh_authentication(claims.get("auth_time"), datetime.now(UTC))
        validated = CodeIDToken(
            claims,
            header,
            params={"nonce": nonce, "client_id": client_id, "access_token": access_token},
        )
        validated.validate(leeway=30)
        return FederatedIdentity(
            issuer=identity_text(claims["iss"], 2048),
            subject=identity_text(claims["sub"]),
            verified_email=(
                identity_text(claims["email"], 254)
                if claims.get("email_verified") is True and claims.get("email")
                else None
            ),
            display_name=identity_text(claims["name"], 160) if claims.get("name") else None,
            verified_attributes=mapped_attributes(claims, attribute_names),
        )
    except Exception:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None


def saml_identity(
    encoded, settings, request_data, *, request_id, relay_state, expected_relay,
    attribute_names=(),
):
    try:
        if not correlated(relay_state, expected_relay):
            raise ValueError("Invalid correlation")
        identity_text(request_id, 256)
        if not isinstance(encoded, str) or not 1 <= len(encoded) <= 1048576:
            raise ValueError("Invalid response size")
        content = base64.b64decode(encoded, validate=True)
        document = etree.fromstring(
            content,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
        )
        if (
            document.getroottree().docinfo.doctype
            or document.tag != SAML_RESPONSE
            or document.get("InResponseTo") != request_id
        ):
            raise ValueError("Invalid correlated response")
        certificate = x509.load_pem_x509_certificate(
            OneLogin_Saml2_Utils.format_cert(settings["idp"]["x509cert"]).encode("ascii")
        )
        moment = datetime.now(UTC)
        if not certificate.not_valid_before_utc <= moment < certificate.not_valid_after_utc:
            raise ValueError("Signing certificate is not current")
        hardened = {
            **settings,
            "strict": True,
            "debug": False,
            "security": {
                **settings.get("security", {}),
                "wantAssertionsSigned": True,
                "wantMessagesSigned": True,
                "wantAttributeStatement": False,
                "wantXMLValidation": True,
                "rejectDeprecatedAlgorithm": True,
                "destinationStrictlyMatches": True,
                "relaxDestinationValidation": False,
            },
        }
        authentication = OneLogin_Saml2_Auth(
            {**request_data, "post_data": {"SAMLResponse": encoded, "RelayState": relay_state}},
            old_settings=hardened,
        )
        authentication.process_response(request_id=request_id)
        if (
            authentication.get_errors()
            or not authentication.is_authenticated()
            or authentication.get_nameid_format() != PERSISTENT_NAME_ID
        ):
            raise ValueError("Invalid signed assertion")
        expires = authentication.get_last_assertion_not_on_or_after()
        if not isinstance(expires, (int, float)) or expires <= moment.timestamp():
            raise ValueError("Assertion has expired")
        statements = document.findall(
            "{urn:oasis:names:tc:SAML:2.0:assertion}Assertion/"
            "{urn:oasis:names:tc:SAML:2.0:assertion}AuthnStatement"
        )
        if len(statements) != 1:
            raise ValueError("A unique signed authentication instant is required")
        instant = datetime.fromisoformat(statements[0].get("AuthnInstant", ""))
        if instant.tzinfo is None:
            raise ValueError("An aware signed authentication instant is required")
        fresh_authentication(instant.timestamp(), moment)
        return FederatedIdentity(
            issuer=identity_text(settings["idp"]["entityId"], 2048),
            subject=identity_text(authentication.get_nameid()),
            verified_email=None,
            display_name=None,
            assertion_id=identity_text(authentication.get_last_assertion_id(), 256),
            assertion_expires_at=datetime.fromtimestamp(expires, UTC),
            verified_attributes=mapped_attributes(authentication.get_attributes(), attribute_names),
        )
    except (Exception, binascii.Error):
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None


def ldap_user_filter(attribute, username):
    if attribute not in {"uid", "sAMAccountName", "userPrincipalName"}:
        raise CommandError(422, "LDAP_ATTRIBUTE_NOT_ALLOWED")
    try:
        return "(" + attribute + "=" + escape_filter_chars(identity_text(username, 254)) + ")"
    except ValueError:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None


def ldap_identity(
    config, bind_password, username, password, *, resolver=None, connection_factory=None,
):
    from app.schemas.integrations import LDAPConfig

    connection = None
    try:
        config = LDAPConfig.model_validate(config)
        if not config.audience_approved or not all(
            isinstance(value, str) and 1 <= len(value) <= 16384
            for value in (bind_password, password)
        ):
            raise ValueError
        user_filter = ldap_user_filter(config.username_attribute, username)
        addresses = checked_addresses(
            config.host, config.port, config.approved_addresses, config.allow_private_endpoint,
            **({"resolver": resolver} if resolver else {}),
        )
        tls = Tls(
            validate=ssl.CERT_REQUIRED, valid_names=[config.host], sni=config.host,
            ca_certs_data=config.ca_certificates_pem,
        )
        server = Server(
            addresses[0], port=config.port, use_ssl=config.security == "ldaps", tls=tls,
            get_info=NONE, connect_timeout=config.connect_timeout_seconds,
        )
        connection = (connection_factory or Connection)(
            server, user=config.bind_dn, password=bind_password, authentication=SIMPLE,
            auto_bind=False, auto_referrals=False, raise_exceptions=True, read_only=True,
            receive_timeout=config.read_timeout_seconds,
        )
        connection.open(read_server_info=False)
        if connection.closed:
            raise ValueError
        if config.security == "starttls" and not connection.start_tls(read_server_info=False):
            raise ValueError
        check_hostname(connection.socket, config.host, [config.host])
        if not connection.bind():
            raise ValueError
        if not connection.search(
            config.user_search_base, user_filter, search_scope=SUBTREE,
            attributes=[config.subject_attribute, *config.attribute_names], size_limit=2,
            time_limit=config.read_timeout_seconds,
        ):
            raise ValueError
        entries = connection.response
        if len(entries) != 1 or entries[0].get("type") != "searchResEntry":
            raise ValueError
        entry = entries[0]
        distinguished_name = identity_text(entry["dn"], 1000)
        values = entry["raw_attributes"][config.subject_attribute]
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], bytes):
            raise ValueError
        if config.subject_attribute == "objectGUID":
            subject = str(UUID(bytes_le=values[0]))
        else:
            subject = str(UUID(values[0].decode("ascii")))
        if not connection.rebind(
            user=distinguished_name, password=password, authentication=SIMPLE,
            read_server_info=False,
        ):
            raise ValueError
        scheme = "ldaps" if config.security == "ldaps" else "ldap+starttls"
        return FederatedIdentity(
            issuer=scheme + "://" + config.host + ":" + str(config.port), subject=subject,
            verified_email=None, display_name=None,
            verified_attributes=mapped_attributes(
                entry.get("attributes", {}), config.attribute_names
            ),
        )
    except Exception:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None
    finally:
        if connection is not None:
            connection.password = None
            with suppress(Exception):
                connection.unbind()