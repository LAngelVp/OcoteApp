import hashlib
import secrets
from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock
from time import monotonic
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR
from app.core.errors import CommandError, ServiceUnavailable
from app.core.security import (
    CONFIG_LOCK,
    COOKIE,
    DUMMY_HASH,
    PASSWORDS,
    AuthSettings,
    Tokens,
    check_origin,
    jti_hash,
    now,
    verify_password,
)
from app.models.identity import AuditEvent, RefreshSession, User


def audit(
    db,
    request,
    event,
    actor=None,
    entity="session",
    entity_id=None,
    before=None,
    after=None,
    outcome="success",
):
    db.add(
        AuditEvent(
            actor_id=actor,
            event_type=event,
            entity_type=entity,
            entity_id=entity_id,
            before_data=before or {},
            after_data=after or {},
            request_id=UUID(request.state.request_id),
            outcome=outcome,
        )
    )


def config_lock(db, *, exclusive=True):
    operation = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    db.execute(text(f"SELECT {operation}(:key)"), {"key": CONFIG_LOCK})


def database(request: Request):
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise ServiceUnavailable()
    with request.app.state.session_factory() as db:
        db.autoflush = False
        try:
            operational = request.url.path.split("/")[3:4] in [
                ["annual-plans"],
                ["objectives"],
                ["tasks"],
                ["subtasks"],
                ["due-date-requests"],
            ]
            config_lock(db, exclusive=not operational and request.method not in {"GET", "HEAD"})
            yield db
            db.commit()
        except CommandError as error:
            if error.persist:
                db.commit()
            else:
                db.rollback()
                if error.status in {401, 403}:
                    with request.app.state.session_factory.begin() as security_db:
                        audit(security_db, request, "security_denied", outcome="denied")
            raise
        except IntegrityError:
            db.rollback()
            raise CommandError(409, "DEPENDENCY_OR_DUPLICATE_CONFLICT") from None
        except DBAPIError as error:
            db.rollback()
            if getattr(error.orig, "sqlstate", None) in {"40001", "40P01", "55P03"}:
                raise CommandError(409, "CONCURRENCY_CONFLICT") from None
            raise ServiceUnavailable() from None


Database = Annotated[Session, Depends(database, scope="function")]


def token_service(request: Request) -> Tokens:
    if request.app.state.tokens is None:
        try:
            request.app.state.tokens = Tokens(AuthSettings())
        except (ValueError, OSError):
            raise ServiceUnavailable() from None
    return request.app.state.tokens


TokenService = Annotated[Tokens, Depends(token_service)]


def origin(request, tokens):
    check_origin(
        request.headers.get("origin"), request.headers.get("referer"), tokens.settings.auth_origin
    )


def revoke(db, *, user_id=None, family=None):
    predicate = RefreshSession.user_id == user_id if user_id else RefreshSession.family_id == family
    db.execute(
        update(RefreshSession)
        .where(predicate, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def touch(record):
    record.version += 1
    record.updated_at = now()


def user_view(user):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "department_id": user.department_id,
        "is_active": user.is_active,
        "version": user.version,
    }


def current_user(request: Request, db: Database, tokens: TokenService) -> User:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise CommandError(401, "INVALID_CREDENTIALS")
    claims = tokens.decode(authorization[7:], "access")
    user = db.get(User, UUID(claims["sub"]))
    family = db.scalar(
        select(RefreshSession.id)
        .where(
            RefreshSession.user_id == UUID(claims["sub"]),
            RefreshSession.family_id == UUID(claims["sid"]),
            RefreshSession.token_version == claims["ver"],
            RefreshSession.revoked_at.is_(None),
            RefreshSession.consumed_at.is_(None),
            RefreshSession.expires_at > now(),
        )
        .limit(1)
    )
    if not user or not user.is_active or user.token_version != claims["ver"] or family is None:
        raise CommandError(401, "INVALID_CREDENTIALS")
    request.state.actor = user.id
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def administrator(user: CurrentUser) -> User:
    if user.role != "admin":
        raise CommandError(403, "FORBIDDEN")
    return user


Administrator = Annotated[User, Depends(administrator)]


class LoginLimiter:
    def __init__(self):
        self.lock = Lock()
        self.key = secrets.token_bytes(32)
        self.attempts = defaultdict(deque)

    def check(self, account, client):
        moment = monotonic()
        with self.lock:
            for key in list(self.attempts):
                if not self.attempts[key] or self.attempts[key][-1] <= moment - 60:
                    del self.attempts[key]
            if len(self.attempts) >= 4096:
                raise CommandError(429, "RATE_LIMITED")
            for label, value, limit in (("account", account, 10), ("client", client, 50)):
                key = hashlib.blake2b((label + value).encode(), key=self.key).hexdigest()
                entries = self.attempts[key]
                while entries and entries[0] <= moment - 60:
                    entries.popleft()
                if len(entries) >= limit:
                    raise CommandError(429, "RATE_LIMITED")
                entries.append(moment)


def session_response(db, tokens, user, family, expires):
    jti = secrets.token_urlsafe(32)
    record = RefreshSession(
        id=uuid4(),
        user_id=user.id,
        family_id=family,
        jti_hash=jti_hash(jti),
        token_version=user.token_version,
        expires_at=expires,
    )
    db.add(record)
    db.flush()
    refresh = tokens.encode(user, family, "refresh", expires, jti)
    result = {
        "access_token": tokens.access(user, family),
        "token_type": "bearer",
        "expires_in": 600,
        "csrf_token": tokens.csrf(family, expires),
        "user": user_view(user),
    }
    return record, refresh, result


def login(db, tokens, request, body):
    origin(request, tokens)
    request.app.state.login_limiter.check(
        body.email, request.client.host if request.client else "local"
    )
    user = db.scalar(select(User).where(User.email == body.email).with_for_update())
    valid = verify_password(
        user.password_hash if user else DUMMY_HASH, body.password.get_secret_value()
    )
    if not valid or not user or not user.is_active:
        audit(db, request, "login_failed", outcome="denied")
        raise CommandError(401, "INVALID_CREDENTIALS", persist=True)
    if PASSWORDS.check_needs_rehash(user.password_hash):
        user.password_hash = PASSWORDS.hash(body.password.get_secret_value())
        touch(user)
    record, refresh, result = session_response(db, tokens, user, uuid4(), now() + timedelta(days=7))
    audit(db, request, "login_success", actor=user.id, entity_id=record.family_id)
    return refresh, result


def cookie_session(db, tokens, request):
    encoded = request.cookies.get(COOKIE)
    if not encoded:
        raise CommandError(401, "INVALID_CREDENTIALS")
    claims = tokens.decode(encoded, "refresh")
    user = db.scalar(select(User).where(User.id == UUID(claims["sub"])).with_for_update())
    record = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.jti_hash == jti_hash(claims["jti"]))
        .with_for_update()
    )
    if (
        not user
        or not record
        or record.user_id != user.id
        or record.family_id != UUID(claims["sid"])
        or int(record.expires_at.timestamp()) != claims["exp"]
        or record.token_version != claims["ver"]
        or user.token_version != claims["ver"]
        or not user.is_active
        or record.expires_at <= now()
    ):
        raise CommandError(401, "INVALID_CREDENTIALS")
    return user, record


def rotate(db, tokens, request):
    origin(request, tokens)
    user, record = cookie_session(db, tokens, request)
    tokens.check_csrf(request.headers.get("x-csrf-token", ""), record.family_id, record.expires_at)
    if record.consumed_at is not None or record.revoked_at is not None:
        revoke(db, family=record.family_id)
        audit(
            db,
            request,
            "refresh_reuse",
            actor=user.id,
            entity_id=record.family_id,
            outcome="denied",
        )
        raise CommandError(401, "INVALID_CREDENTIALS", persist=True)
    request.app.state.login_limiter.check(
        "refresh:" + str(user.id), request.client.host if request.client else "local"
    )
    successor, refresh, result = session_response(
        db, tokens, user, record.family_id, record.expires_at
    )
    record.consumed_at = now()
    record.replaced_by_id = successor.id
    audit(db, request, "session_refreshed", actor=user.id, entity_id=record.family_id)
    return refresh, result


def logout(db, tokens, request):
    origin(request, tokens)
    try:
        user, record = cookie_session(db, tokens, request)
    except CommandError as error:
        if error.status == 401:
            return
        raise
    tokens.check_csrf(request.headers.get("x-csrf-token", ""), record.family_id, record.expires_at)
    revoke(db, family=record.family_id)
    audit(db, request, "logout", actor=user.id, entity_id=record.family_id)


def change_password(db, tokens, request, user, body):
    origin(request, tokens)
    db.refresh(user, with_for_update=True)
    if not verify_password(user.password_hash, body.current_password.get_secret_value()):
        raise CommandError(401, "INVALID_CREDENTIALS")
    user.password_hash = PASSWORDS.hash(body.new_password.get_secret_value())
    user.token_version += 1
    touch(user)
    revoke(db, user_id=user.id)
    audit(db, request, "password_changed", actor=user.id, entity_id=user.id)


def bootstrap_admin(db, *, email, display_name, password, request):
    config_lock(db)
    if db.scalar(select(func.count()).select_from(User)):
        raise CommandError(409, "BOOTSTRAP_ALREADY_COMPLETED")
    user = User(
        email=email,
        display_name=display_name,
        role="admin",
        department_id=None,
        password_hash=PASSWORDS.hash(password),
        token_version=1,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(db, request, "bootstrap_admin", actor=user.id, entity="users", entity_id=user.id)
    return user
