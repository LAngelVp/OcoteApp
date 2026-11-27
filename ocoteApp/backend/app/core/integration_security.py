import hashlib
import hmac
import ipaddress
import re
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from app.core.errors import CommandError

API_SCOPES = frozenset({"tasks:read", "tasks:create", "tasks:update_metadata"})
KEY_PATTERN = re.compile(r"oct_svc_([0-9a-f]{32})\.([A-Za-z0-9_-]{43})", re.ASCII)


def key_identifier(encoded):
    match = KEY_PATTERN.fullmatch(encoded) if isinstance(encoded, str) else None
    if match is None:
        raise CommandError(401, "SERVICE_CREDENTIAL_INVALID")
    return UUID(hex=match.group(1))


def new_service_key(identifier):
    if not isinstance(identifier, UUID):
        raise ValueError("An explicit key identifier is required")
    return "oct_svc_" + identifier.hex + "." + secrets.token_urlsafe(32)


def key_digest(encoded, pepper):
    key_identifier(encoded)
    if not isinstance(pepper, bytes) or len(pepper) < 32:
        raise ValueError("A protected 256-bit pepper is required")
    return hmac.new(pepper, encoded.encode("ascii"), hashlib.sha256).hexdigest()


def key_matches(encoded, pepper, expected):
    try:
        return (
            isinstance(expected, str)
            and len(expected) == 64
            and hmac.compare_digest(key_digest(encoded, pepper), expected)
        )
    except (CommandError, ValueError, TypeError):
        return False


def validated_scopes(requested, approved):
    if (
        not requested
        or len(requested) != len(set(requested))
        or set(requested) - API_SCOPES
        or set(requested) - set(approved)
    ):
        raise CommandError(422, "SERVICE_SCOPES_NOT_APPROVED")
    return sorted(requested)


def validate_key_expiry(issued_at, expires_at):
    if (
        not isinstance(issued_at, datetime)
        or not isinstance(expires_at, datetime)
        or issued_at.utcoffset() is None
        or expires_at.utcoffset() is None
        or not timedelta(days=1) <= expires_at - issued_at <= timedelta(days=90)
    ):
        raise CommandError(422, "SERVICE_KEY_EXPIRY_INVALID")


def client_ip_allowed(address, networks):
    try:
        parsed = ipaddress.ip_address(address)
        if networks is None:
            return True
        if not isinstance(networks, list) or not networks:
            return False
        allowed = [ipaddress.ip_network(value, strict=True) for value in networks]
        return any(parsed.version == network.version and parsed in network for network in allowed)
    except (ValueError, TypeError):
        return False


def webhook_signature(secret, timestamp, content):
    if (
        not isinstance(secret, bytes)
        or len(secret) < 32
        or type(timestamp) is not int
        or timestamp < 0
        or not isinstance(content, bytes)
        or len(content) > 1048576
    ):
        raise ValueError("Invalid signed webhook input")
    return "v1=" + hmac.new(
        secret, str(timestamp).encode("ascii") + b"." + content, hashlib.sha256
    ).hexdigest()


def valid_webhook_signature(secret, timestamp, content, signature, *, current_time):
    if (
        type(current_time) is not int
        or type(timestamp) is not int
        or abs(current_time - timestamp) > 300
        or not isinstance(signature, str)
        or re.fullmatch(r"v1=[0-9a-f]{64}", signature, re.ASCII) is None
    ):
        return False
    try:
        return hmac.compare_digest(webhook_signature(secret, timestamp, content), signature)
    except (TypeError, ValueError):
        return False