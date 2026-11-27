import logging
from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import JsonLimitMiddleware, RequestContextMiddleware, install_error_handlers
from app.core.notifications import CalendarAccessFilter
from app.db.engine import create_database_engine
from app.routers.administration import router as administration_router
from app.routers.analytics import router as analytics_router
from app.routers.auth import router as auth_router
from app.routers.bulk import router as bulk_router
from app.routers.collaboration import router as collaboration_router
from app.routers.enterprise import router as enterprise_router
from app.routers.execution import router as execution_router
from app.routers.health import router
from app.routers.integrations import router as integrations_router
from app.routers.notifications import router as notifications_router
from app.routers.operations import router as operations_router
from app.routers.platform import router as platform_router
from app.routers.setup import closed_router as setup_closed_router
from app.services.identity import LoginLimiter


def create_app(settings: Settings | None = None, *, tokens=None) -> FastAPI:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, CalendarAccessFilter) for item in access_logger.filters):
        access_logger.addFilter(CalendarAccessFilter())
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
    app.state.export_limiter = LoginLimiter()
    app.state.import_limiter = LoginLimiter()
    app.state.expected_heads = heads
    app.state.session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.add_middleware(JsonLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(administration_router)
    app.include_router(operations_router)
    app.include_router(execution_router)
    app.include_router(analytics_router)
    app.include_router(platform_router)
    app.include_router(enterprise_router)
    app.include_router(collaboration_router)
    app.include_router(notifications_router)
    app.include_router(integrations_router)
    app.include_router(bulk_router)
    app.include_router(setup_closed_router)
    return app
