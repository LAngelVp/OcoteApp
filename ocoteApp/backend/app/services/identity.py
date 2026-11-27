import hashlib
import logging
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
    actor_service=None,
):
    db.add(
        AuditEvent(
            actor_id=actor,
            actor_service_id=actor_service,
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
        committed = False
        uncertain = False
        try:
            reporting = request.url.path.split("/")[3:4] in [
                ["analytics"],
                ["evaluations"],
                ["exports"],
                ["executive-reports"],
            ]
            if reporting:
                db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            operational = request.url.path.split("/")[3:4] in [
                ["annual-plans"],
                ["objectives"],
                ["tasks"],
                ["subtasks"],
                ["due-date-requests"],
                ["evidence"],
                ["kanban"],
                ["timeline"],
            ]
            if request.url.path.startswith("/api/v1/collaboration/"):
                catalog = request.url.path.split("/")[4:5] in [
                    ["custom-fields"], ["tags"], ["templates"], ["service-principals"],
                    ["recurrence-schedules"],
                ]
                operational = not catalog
            config_lock(
                db,
                exclusive=not (operational or reporting) and request.method not in {"GET", "HEAD"},
            )
            yield db
            db.commit()
            committed = True
        except CommandError as error:
            if error.persist:
                db.commit()
                committed = True
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
            uncertain = error.connection_invalidated
            db.rollback()
            if getattr(error.orig, "sqlstate", None) in {"40001", "40P01", "55P03"}:
                raise CommandError(409, "CONCURRENCY_CONFLICT") from None
            raise ServiceUnavailable() from None
        finally:
            if not committed and not uncertain:
                for path in db.info.get("rollback_files", []):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logging.getLogger("ocote.requests").error(
                            "request_id=%s code=EVIDENCE_RECONCILIATION_REQUIRED",
                            request.state.request_id,
                        )


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
        select(RefreshSession)
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
    from app.services.enterprise import policy, request_modules, require_page_size, session_policy

    configured = policy(db, required=False)
    if configured is None and (
        user.role != "admin" or not request.url.path.startswith(
            ("/api/v1/admin/", "/api/v1/auth/", "/api/v1/configuration")
        )
    ):
        raise CommandError(503, "SECURITY_CONFIGURATION_REQUIRED")
    session_policy(db, family, claims)
    if "limit" in request.query_params and request.url.path.split("/")[3] not in {
        "analytics", "kanban", "timeline"
    }:
        try:
            size = int(request.query_params["limit"])
        except ValueError:
            raise CommandError(422, "PAGE_SIZE_NOT_ALLOWED") from None
        require_page_size(db, size)
    request_modules(db, request)
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


def session_response(
    db, tokens, user, family, expires, *, external_identity_id=None,
    federated_authenticated_at=None, federated_revocation_deadline=None,
):
    from app.services.enterprise import policy

    settings = policy(db, required=False)
    seconds = settings.access_ttl_seconds if settings else 600
    jti = secrets.token_urlsafe(32)
    issued = now()
    record = RefreshSession(
        id=uuid4(),
        created_at=issued,
        user_id=user.id,
        family_id=family,
        jti_hash=jti_hash(jti),
        token_version=user.token_version,
        expires_at=expires,
        last_seen_at=issued,
        external_identity_id=external_identity_id,
        federated_authenticated_at=federated_authenticated_at,
        federated_revocation_deadline=federated_revocation_deadline,
    )
    db.add(record)
    db.flush()
    refresh = tokens.encode(user, family, "refresh", expires, jti)
    result = {
        "access_token": tokens.encode(user, family, "access", now() + timedelta(seconds=seconds),
                           secrets.token_urlsafe(32)),
        "token_type": "bearer",
        "expires_in": seconds,
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
    from app.services.enterprise import policy

    settings = policy(db, required=False)
    moment = now()
    locked = bool(user and user.locked_until and user.locked_until > moment)
    valid = verify_password(
        user.password_hash if user and not locked else DUMMY_HASH, body.password.get_secret_value()
    )
    if not valid or not user or not user.is_active or locked:
        if user and user.is_active and settings and not locked:
            window = timedelta(seconds=settings.failed_window_seconds)
            if user.failed_window_at is None or moment - user.failed_window_at >= window:
                user.failed_window_at, user.failed_attempt_count = moment, 0
            user.failed_attempt_count += 1
            if user.failed_attempt_count >= settings.failed_attempt_threshold:
                user.locked_until = moment + timedelta(seconds=settings.lockout_seconds)
            touch(user)
        audit(db, request, "login_failed", outcome="denied")
        raise CommandError(401, "INVALID_CREDENTIALS", persist=True)
    if settings is None and user.role != "admin":
        raise CommandError(503, "SECURITY_CONFIGURATION_REQUIRED")
    if user.failed_attempt_count or user.failed_window_at or user.locked_until:
        user.failed_attempt_count = 0
        user.failed_window_at = user.locked_until = None
        touch(user)
    if PASSWORDS.check_needs_rehash(user.password_hash):
        user.password_hash = PASSWORDS.hash(body.password.get_secret_value())
        touch(user)
    seconds = settings.refresh_absolute_seconds if settings else 604800
    record, refresh, result = session_response(
        db, tokens, user, uuid4(), now() + timedelta(seconds=seconds)
    )
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
    from app.services.enterprise import session_policy

    session_policy(db, record)
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
        db, tokens, user, record.family_id, record.expires_at,
        external_identity_id=record.external_identity_id,
        federated_authenticated_at=record.federated_authenticated_at,
        federated_revocation_deadline=record.federated_revocation_deadline,
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
    from app.services.enterprise import reauthenticate, validate_password

    reauthenticate(db, user, body, request)
    validate_password(db, body.new_password.get_secret_value())
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
