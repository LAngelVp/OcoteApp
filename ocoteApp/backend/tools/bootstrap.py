"""Operator-only local F2 keys and one-time admin provisioning; no business seeds."""

import argparse
import getpass
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.core.security import AuthSettings, Tokens  # noqa: E402
from app.db.engine import create_database_engine  # noqa: E402
from app.models.identity import User  # noqa: E402
from app.schemas.identity import UserCreate  # noqa: E402
from app.services.identity import bootstrap_admin  # noqa: E402
from tools import f1_local as local  # noqa: E402


def init_auth(origin):
    private = local.LOCAL / "auth-signing.pem"
    secret = local.LOCAL / "auth-csrf.key"
    configuration = local.LOCAL / "auth.env"
    AuthSettings(auth_origin=origin, jwt_private_key_file=private, csrf_secret_file=secret)
    if private.exists() or secret.exists() or configuration.exists():
        raise RuntimeError("Existing keys or missing protected environment; no overwrite allowed")
    local.private_directory(local.LOCAL)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    local.write_private(
        private,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    local.write_private(secret, secrets.token_bytes(32))
    values = {
        "AUTH_ORIGIN": origin,
        "JWT_PRIVATE_KEY_FILE": str(private),
        "CSRF_SECRET_FILE": str(secret),
    }
    local.write_private(
        configuration,
        "".join(
            f"{name}='{value.replace(chr(92), '/')}'\n" for name, value in values.items()
        ).encode("utf-8"),
    )
    print("Local authentication keys initialized; no users or catalogs created.")


def provision():
    if local.MARKER.exists():
        raise RuntimeError("Maintenance must be investigated before provisioning")
    Tokens(AuthSettings())
    email = input("First admin email: ")
    display_name = input("First admin display name: ")
    password = getpass.getpass("First admin password (minimum 12 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise ValueError("Passwords do not match")
    command = UserCreate(
        email=email,
        display_name=display_name,
        password=password,
        role="admin",
        reason="Explicit operator first-admin provisioning",
    )
    engine = create_database_engine(Settings())
    try:
        with sessionmaker(bind=engine).begin() as db:
            user = bootstrap_admin(
                db,
                email=command.email,
                display_name=command.display_name,
                password=command.password.get_secret_value(),
                request=SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4()))),
            )
            assert db.scalar(select(User.id).where(User.id == user.id)) is not None
        print("First admin provisioned and audited; no business configuration was inserted.")
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init-auth", "bootstrap-admin"])
    parser.add_argument("--origin")
    parser.add_argument("--execute", action="store_true", required=True)
    arguments = parser.parse_args()
    if arguments.action == "init-auth":
        if not arguments.origin:
            raise ValueError("Explicit HTTPS loopback origin required")
        init_auth(arguments.origin)
    else:
        provision()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Provisioning stopped safely ({type(error).__name__}); no secrets printed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
