import logging
from http import HTTPStatus
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ocote.requests")


class ServiceUnavailable(Exception):
    pass


class CommandError(Exception):
    def __init__(self, status: int, code: str, *, persist: bool = False):
        self.status = status
        self.code = code
        self.persist = persist


def sso_callback_path(path):
    parts = path.strip("/").split("/")
    if len(parts) != 6 or parts[:4] != ["api", "v1", "auth", "sso"] or parts[5] != "callback":
        return False
    try:
        return str(UUID(parts[4])) == parts[4]
    except ValueError:
        return False


class JsonLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        path = scope["path"]
        parts = path.strip("/").split("/")
        upload = (
            scope["method"] == "POST"
            and len(parts) == 5
            and parts[:3] == ["api", "v1", "tasks"]
            and parts[4] == "evidence"
        )
        callback = scope["method"] == "POST" and sso_callback_path(path)
        content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        if callback and content_type != b"application/x-www-form-urlencoded":
            await problem(Request(scope), 415, "SSO_FORM_REQUIRED", "SSO form required.")(
                scope, receive, send
            )
            return
        if (
            not upload
            and not callback
            and path not in {"/api/v1/auth/refresh", "/api/v1/auth/logout"}
            and content_type != b"application/json"
        ):
            await problem(Request(scope), 415, "JSON_REQUIRED", "JSON commands required.")(
                scope, receive, send
            )
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            maximum = (13992000 if path == "/api/v1/imports" and scope["method"] == "POST" else
                       10485760 if upload else
                       1410000 if path == "/api/v1/admin/branding/logo" else 1048576)
            if len(body) > maximum:
                await problem(Request(scope), 413, "PAYLOAD_TOO_LARGE", "Request body too large.")(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break

        async def replay():
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        status = 500
        response_started = False

        async def send_with_context(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = list(message.get("headers", []))
                headers = [(key, value) for key, value in headers if key not in {
                    b"x-request-id", b"cache-control", b"x-content-type-options"
                }]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                headers.append((b"cache-control", b"no-store"))
                headers.append((b"x-content-type-options", b"nosniff"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            if response_started:
                raise RuntimeError("Response transport failed") from None
            response = problem(Request(scope), 500, "INTERNAL_ERROR", "An internal error occurred.")
            await response(scope, receive, send_with_context)
        finally:
            logger.info(
                "request_id=%s method=%s status=%s duration_ms=%.2f",
                request_id,
                scope["method"],
                status,
                (perf_counter() - started) * 1000,
            )


def problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    headers = {
        "X-Request-ID": request_id,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if status == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
        content={
            "type": f"urn:ocote:problem:{code.lower().replace('_', '-')}",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "code": code,
            "detail": detail,
            "instance": request.url.path,
            "request_id": request_id,
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CommandError)
    async def command_error(request: Request, exc: CommandError) -> JSONResponse:
        return problem(request, exc.status, exc.code, "The request could not be completed.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {401: "INVALID_CREDENTIALS", 403: "FORBIDDEN", 404: "RESOURCE_NOT_FOUND"}
        response = problem(
            request,
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            "The request could not be completed.",
        )
        for header in ("Allow", "Retry-After"):
            if exc.headers and header in exc.headers:
                response.headers[header] = exc.headers[header]
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(request, 422, "VALIDATION_ERROR", "Invalid request parameters.")

    @app.exception_handler(ServiceUnavailable)
    async def unavailable(request: Request, exc: ServiceUnavailable) -> JSONResponse:
        return problem(request, 503, "SERVICE_UNAVAILABLE", "Service is not ready.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return problem(request, 500, "INTERNAL_ERROR", "An internal error occurred.")
