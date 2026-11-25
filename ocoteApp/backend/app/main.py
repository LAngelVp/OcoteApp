from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import JsonLimitMiddleware, RequestContextMiddleware, install_error_handlers
from app.db.engine import create_database_engine
from app.routers.administration import router as administration_router
from app.routers.auth import router as auth_router
from app.routers.health import router
from app.routers.operations import router as operations_router
from app.services.identity import LoginLimiter


def create_app(settings: Settings | None = None, *, tokens=None) -> FastAPI:
    settings = settings or Settings()
    engine = create_database_engine(settings)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("The application artifact must contain exactly one Alembic head")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await run_in_threadpool(engine.dispose)

    app = FastAPI(
        title="OCOTE technical API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.tokens = tokens
    app.state.login_limiter = LoginLimiter()
    app.state.expected_heads = heads
    app.state.session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.add_middleware(JsonLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(administration_router)
    app.include_router(operations_router)
    return app
