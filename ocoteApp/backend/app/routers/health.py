from secrets import compare_digest
from typing import Annotated

from alembic.migration import MigrationContext
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, DATABASE_NAME
from app.core.errors import ServiceUnavailable
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/health", tags=["health"])


def require_monitor(request: Request) -> None:
    supplied = request.headers.get("X-Health-Token", "").encode("utf-8")
    expected = request.app.state.settings.health_token.get_secret_value().encode("utf-8")
    if not compare_digest(supplied, expected):
        raise HTTPException(status_code=403)


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready", dependencies=[Depends(require_monitor)])
def ready(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise ServiceUnavailable
    try:
        database = session.execute(text("SELECT current_database()")).scalar_one()
        revisions = MigrationContext.configure(session.connection()).get_current_heads()
        if database != DATABASE_NAME or set(revisions) != set(request.app.state.expected_heads):
            raise ServiceUnavailable
    except SQLAlchemyError:
        raise ServiceUnavailable from None
    return {"status": "ready"}
