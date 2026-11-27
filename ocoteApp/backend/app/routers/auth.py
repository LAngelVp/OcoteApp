from typing import Annotated
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.core.errors import CommandError
from app.core.security import COOKIE, COOKIE_PATH, now
from app.schemas.enterprise import Reauthenticated
from app.schemas.identity import ChangePassword, Login
from app.schemas.integrations import LDAPLogin, SSOFinish, SSOStart
from app.services import federation, identity
from app.services.identity import Administrator, CurrentUser, Database, TokenService

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


def set_refresh(response, encoded, tokens):
    claims = tokens.decode(encoded, "refresh")
    response.set_cookie(
        COOKIE,
        encoded,
        httponly=True,
        secure=True,
        samesite="strict",
        path=COOKIE_PATH,
        max_age=max(0, claims["exp"] - int(now().timestamp())),
    )


def clear_refresh(response):
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, secure=True, samesite="strict")


def set_sso_cookie(response, transaction_id, browser):
    response.set_cookie(
        federation.browser_cookie(transaction_id), browser,
        httponly=True, secure=True, samesite="strict", path="/api/v1/auth/sso", max_age=300,
    )


def start_sso(body, integration_id, request, response, db, tokens, actor=None):
    result, browser, state = federation.start(db, tokens, request, integration_id, body, actor)
    set_sso_cookie(response, result["transaction_id"], browser)
    if result["authorization_url"] is None:
        result["state"] = state
    return result


@router.get("/sso/providers")
def sso_providers(db: Database, limit: Annotated[int, Query(ge=1, le=50)] = 5,
                   cursor: UUID | None = None):
    return federation.providers(db, limit, cursor)


@router.get("/sso/identities")
def sso_identities(user: CurrentUser, db: Database,
                   limit: Annotated[int, Query(ge=1, le=50)] = 5, cursor: UUID | None = None):
    return federation.bindings(db, user, limit, cursor, user.id)


@router.post("/sso/identities/{binding_id}/revoke")
def sso_revoke(binding_id: UUID, body: Reauthenticated, request: Request,
                user: CurrentUser, db: Database):
    return federation.revoke_binding(db, binding_id, body, request, user)


@router.post("/sso/{integration_id}/start")
def sso_start(
    integration_id: UUID, body: SSOStart, request: Request, response: Response,
    db: Database, tokens: TokenService,
):
    if body.purpose != "login":
        raise CommandError(401, "INVALID_CREDENTIALS")
    return start_sso(body, integration_id, request, response, db, tokens)


@router.post("/sso/{integration_id}/bind")
def sso_bind_start(
    integration_id: UUID, body: SSOStart, request: Request, response: Response,
    user: CurrentUser, db: Database, tokens: TokenService,
):
    if body.purpose != "bind":
        raise CommandError(422, "SSO_BINDING_REQUIRED")
    return start_sso(body, integration_id, request, response, db, tokens, user)


def saml_form(content):
    try:
        values = parse_qs(content.decode("ascii"), keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=2)
        if set(values) != {"SAMLResponse", "RelayState"} or any(
            len(items) != 1 or not items[0] for items in values.values()
        ):
            raise ValueError
        return values["RelayState"][0], values["SAMLResponse"][0]
    except ValueError:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None


@router.get("/sso/{integration_id}/callback", name="oidc_callback")
@router.post("/sso/{integration_id}/callback", name="saml_callback")
async def sso_callback(
    integration_id: UUID, request: Request, db: Database, tokens: TokenService,
):
    if request.method == "POST":
        state, response = saml_form(await request.body())
        arguments = {"response": response}
    else:
        if len(request.scope.get("query_string", b"")) > 16384:
            raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
        values = dict(request.query_params)
        if len(values) != len(request.query_params.multi_items()) or set(values) - {
            "state", "code", "iss", "session_state", "error", "error_description", "error_uri"
        }:
            raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
        state, arguments = values.get("state"), {"code": values.get("code")}
    transaction_id = await run_in_threadpool(
        federation.callback, db, tokens, request, integration_id, state, **arguments
    )
    return RedirectResponse(
        tokens.settings.auth_origin + "/login?" + urlencode({"sso_transaction": transaction_id}),
        status_code=303,
        headers={"Referrer-Policy": "no-referrer"},
    )


@router.post("/sso/{integration_id}/ldap")
def sso_ldap(integration_id: UUID, body: LDAPLogin, request: Request, db: Database,
             tokens: TokenService):
    browser = request.cookies.get(federation.browser_cookie(body.transaction_id))
    transaction = federation.pending(db, integration_id, body.state)
    if transaction.id != body.transaction_id:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID")
    result = federation.ldap_callback(
        db, tokens, request, integration_id, body.state, browser, body
    )
    return {"transaction_id": result}


@router.get("/sso/transactions/{transaction_id}")
def sso_transaction(transaction_id: UUID, request: Request, db: Database, tokens: TokenService):
    return federation.completion_status(
        db, tokens, request, transaction_id,
        request.cookies.get(federation.browser_cookie(transaction_id)),
    )


def finish_sso(body, request, response, db, tokens, actor=None, *, purpose="login"):
    cookie = federation.browser_cookie(body.transaction_id)
    refresh, result = federation.finish(
        db, tokens, request, body.transaction_id, request.cookies.get(cookie), actor,
        purpose=purpose,
    )
    if refresh is not None:
        set_refresh(response, refresh, tokens)
    response.delete_cookie(cookie, path="/api/v1/auth/sso", httponly=True, secure=True,
                           samesite="strict")
    return result


@router.post("/sso/finish")
def sso_finish(body: SSOFinish, request: Request, response: Response, db: Database,
               tokens: TokenService):
    return finish_sso(body, request, response, db, tokens)


@router.post("/sso/bind/finish")
def sso_bind_finish(body: SSOFinish, request: Request, response: Response, user: CurrentUser,
                    db: Database, tokens: TokenService):
    return finish_sso(body, request, response, db, tokens, user, purpose="bind")


@router.post("/sso/probe/finish")
def sso_probe_finish(body: SSOFinish, request: Request, response: Response, user: Administrator,
                     db: Database, tokens: TokenService):
    return finish_sso(body, request, response, db, tokens, user, purpose="probe")


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: Database, tokens: TokenService):
    refresh, result = identity.login(db, tokens, request, body)
    set_refresh(response, refresh, tokens)
    return result


@router.get("/csrf")
def csrf(request: Request, db: Database, tokens: TokenService):
    identity.origin(request, tokens)
    _, record = identity.cookie_session(db, tokens, request)
    if record.consumed_at is not None or record.revoked_at is not None:
        raise CommandError(401, "INVALID_CREDENTIALS")
    return {"csrf_token": tokens.csrf(record.family_id, record.expires_at)}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Database, tokens: TokenService):
    encoded, result = identity.rotate(db, tokens, request)
    set_refresh(response, encoded, tokens)
    return result


@router.post("/logout", status_code=204)
def logout(request: Request, db: Database, tokens: TokenService):
    identity.logout(db, tokens, request)
    response = Response(status_code=204)
    clear_refresh(response)
    return response


@router.get("/me")
def me(user: CurrentUser):
    permissions = {
        "admin": [
            "administration:manage",
            "catalogs:global",
            "planning:manage",
            "tasks:global",
            "tasks:manage",
            "tasks:transition",
            "dates:decide",
            "date-requests:create",
            "analytics:read",
            "evaluations:read",
            "evaluations:manage",
            "exports:read",
        ],
        "gerente": [
            "catalogs:global",
            "planning:manage",
            "tasks:global",
            "dates:decide",
            "date-requests:create",
            "analytics:read",
            "evaluations:read",
            "evaluations:manage",
            "exports:read",
        ],
        "lider": [
            "catalogs:department",
            "planning:department",
            "tasks:department",
            "tasks:manage",
            "tasks:transition",
            "date-requests:create",
            "analytics:read",
            "evaluations:read",
            "exports:read",
        ],
        "colaborador": ["catalogs:self", "tasks:self", "tasks:transition"],
    }
    return {**identity.user_view(user), "permissions": permissions[user.role]}


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePassword, request: Request, user: CurrentUser, db: Database, tokens: TokenService
):
    identity.change_password(db, tokens, request, user, body)
    response = Response(status_code=204)
    clear_refresh(response)
    return response
