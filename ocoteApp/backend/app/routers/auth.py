from fastapi import APIRouter, Request, Response

from app.core.errors import CommandError
from app.core.security import COOKIE, COOKIE_PATH, now
from app.schemas.identity import ChangePassword, Login
from app.services import identity
from app.services.identity import CurrentUser, Database, TokenService

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
        "admin": ["administration:manage", "catalogs:global"],
        "gerente": ["catalogs:global"],
        "lider": ["catalogs:department"],
        "colaborador": ["catalogs:self"],
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
