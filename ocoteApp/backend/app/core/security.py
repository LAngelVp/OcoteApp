import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from app.core.config import BACKEND_DIR, EnvironmentSettings
from app.core.errors import CommandError

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
CONFIG_LOCK = 726_018_242
COOKIE = "ocote_refresh"
COOKIE_PATH = "/api/v1/auth"


def now() -> datetime:
    return datetime.now(UTC)


class AuthSettings(EnvironmentSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR / ".local" / "auth.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    auth_origin: str
    jwt_private_key_file: Path
    csrf_secret_file: Path
    jwt_issuer: str = "ocote-local"
    jwt_audience: str = "ocote-spa"

    @model_validator(mode="after")
    def local_https_only(self):
        origin = urlsplit(self.auth_origin)
        if (
            self.app_env == "production"
            or self.deployment_mode != "local"
            or origin.scheme != "https"
            or origin.hostname not in {"localhost", "127.0.0.1", "::1"}
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or self.auth_origin != f"https://{origin.netloc}"
        ):
            raise ValueError("F2 requires an explicit loopback HTTPS origin without a path")
        try:
            _port = origin.port
        except ValueError:
            raise ValueError("Invalid HTTPS origin port") from None
        return self


def verify_password(encoded: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def jti_hash(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class Tokens:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        private_key = serialization.load_pem_private_key(
            settings.jwt_private_key_file.read_bytes(), password=None
        )
        if not isinstance(private_key, RSAPrivateKey) or private_key.key_size < 3072:
            raise ValueError("RS256 requires an operator-owned RSA key of at least 3072 bits")
        self.private_key = private_key
        self.public_key = private_key.public_key()
        self.kid = hashlib.sha256(
            self.public_key.public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).hexdigest()[:24]
        self.csrf_secret = settings.csrf_secret_file.read_bytes()
        if len(self.csrf_secret) < 32:
            raise ValueError("CSRF requires a separate secret of at least 256 bits")

    def encode(self, user, family: UUID, kind: str, expires: datetime, jti: str) -> str:
        issued = now()
        return jwt.encode(
            {
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
                "sub": str(user.id),
                "iat": issued,
                "nbf": issued,
                "exp": expires,
                "jti": jti,
                "typ": kind,
                "ver": user.token_version,
                "sid": str(family),
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid, "typ": "JWT"},
        )

    def decode(self, encoded: str, kind: str) -> dict:
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get("kid") != self.kid or header.get("typ") != "JWT":
                raise ValueError("Invalid key")
            claims = jwt.decode(
                encoded,
                self.public_key,
                algorithms=["RS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                leeway=30,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "iat",
                        "nbf",
                        "exp",
                        "jti",
                        "typ",
                        "ver",
                        "sid",
                    ]
                },
            )
            if (
                claims["typ"] != kind
                or type(claims["ver"]) is not int
                or claims["ver"] < 1
                or not isinstance(claims["jti"], str)
                or len(claims["jti"]) != 43
                or any(type(claims[name]) is not int for name in ("iat", "nbf", "exp"))
                or claims["exp"] <= claims["iat"]
                or claims["exp"] - claims["iat"] > (600 if kind == "access" else 604800)
            ):
                raise ValueError("Invalid claims")
            UUID(claims["sub"])
            UUID(claims["sid"])
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise CommandError(401, "INVALID_CREDENTIALS") from None

    def csrf(self, family: UUID, expires: datetime) -> str:
        expiration = str(int(expires.timestamp()))
        signature = hmac.new(
            self.csrf_secret, f"{family}:{expiration}".encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"{expiration}.{signature}"

    def check_csrf(self, token: str, family: UUID, expires: datetime) -> None:
        if expires <= now() or not hmac.compare_digest(
            token.encode("utf-8"), self.csrf(family, expires).encode("ascii")
        ):
            raise CommandError(403, "CSRF_REJECTED")

    def access(self, user, family: UUID) -> str:
        return self.encode(
            user, family, "access", now() + timedelta(minutes=10), secrets.token_urlsafe(32)
        )


def check_origin(origin: str | None, referer: str | None, allowed: str) -> None:
    if origin is not None:
        valid = origin == allowed
    else:
        try:
            parsed = urlsplit(referer or "")
        except ValueError:
            raise CommandError(403, "ORIGIN_REJECTED") from None
        valid = (
            not parsed.username
            and not parsed.password
            and f"{parsed.scheme}://{parsed.netloc}" == allowed
        )
    if not valid:
        raise CommandError(403, "ORIGIN_REJECTED")
