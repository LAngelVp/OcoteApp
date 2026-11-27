from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request

from app.core.errors import (
    CommandError,
    JsonLimitMiddleware,
    RequestContextMiddleware,
    install_error_handlers,
)
from app.schemas.installation import Connection, Install
from app.services.installation import Setup

closed_router = APIRouter()


@closed_router.api_route(
    "/api/v1/setup/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False
)
def sealed_runtime(path: str):
    raise CommandError(403, "SETUP_SEALED")


class RuntimeDispatch:
    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        target = (
            self.state.runtime
            if (
                scope["type"] == "http"
                and scope["path"].startswith("/api/")
                and self.state.runtime is not None
            )
            else self.app
        )
        await target(scope, receive, send)


def create_setup_app(setup: Setup) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = None
    app.add_middleware(JsonLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RuntimeDispatch, state=app.state)
    install_error_handlers(app)

    def authorize(request, *, require_pair=True):
        if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
            raise CommandError(403, "SETUP_LOOPBACK_REQUIRED")
        origin = request.headers.get("Origin")
        if not origin and request.method == "GET":
            referer = urlsplit(request.headers.get("Referer", ""))
            origin = f"{referer.scheme}://{referer.netloc}"
        setup.authorize(request.headers.get("X-Setup-Code"), origin, require_pair=require_pair)

    @app.get("/api/v1/setup/status")
    def status(request: Request):
        authorize(request, require_pair=False)
        return {"state": "prepared", "head": "20261126_0011"}

    @app.post("/api/v1/setup/pair")
    def pair(request: Request):
        authorize(request, require_pair=False)
        with setup.lock:
            return setup.pair()

    @app.post("/api/v1/setup/connection-tests")
    def test(body: Connection, request: Request):
        authorize(request)
        with setup.lock:
            return setup.test(body)

    @app.post("/api/v1/setup/install")
    def install(body: Install, request: Request):
        authorize(request)
        result = setup.install(body, request)
        activate = getattr(app.state, "activate_runtime", None)
        if activate is not None:
            app.state.runtime = activate()
        return result

    return app
