from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.models.collaboration import ServicePrincipal
from app.models.notifications import (
    NotificationConnector,
    NotificationConnectorCheck,
    NotificationRule,
)
from app.routers.enterprise import listing
from app.schemas.collaboration import PrincipalWrite as CollaborationPrincipalWrite
from app.schemas.enterprise import Reauthenticated
from app.schemas.notifications import (
    ConnectorTest,
    ConnectorWrite,
    FeedCreate,
    PreferencesWrite,
    PrincipalWrite,
    RuleWrite,
)
from app.schemas.platform import Change
from app.services import collaboration
from app.services import notifications as service
from app.services.identity import Administrator, CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["notifications"])
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/notifications")
def inbox(
    actor: CurrentUser,
    db: Database,
    limit: Limit = 5,
    cursor: UUID | None = None,
    unread: bool = False,
):
    return service.inbox(db, actor, limit, cursor, unread)


@router.post("/notifications/{identity}/read")
def read_notification(
    identity: UUID, body: Change, request: Request, actor: CurrentUser, db: Database
):
    return service.read_notification(db, identity, body, request, actor)


@router.get("/notification-preferences")
def preferences(actor: CurrentUser, db: Database):
    return service.preferences_view(service.preferences(db, actor))


@router.patch("/notification-preferences")
def save_preferences(body: PreferencesWrite, request: Request, actor: CurrentUser, db: Database):
    return service.save_preferences(db, body, request, actor)


@router.get("/integrations/calendar-feeds")
def feeds(actor: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return service.feeds(db, actor, limit, cursor)


@router.post("/integrations/calendar-feeds", status_code=201)
def create_feed(body: FeedCreate, request: Request, actor: CurrentUser, db: Database):
    return service.create_feed(db, body, request, actor)


@router.post("/integrations/calendar-feeds/{identity}/revoke")
def revoke_feed(identity: UUID, body: Change, request: Request, actor: CurrentUser, db: Database):
    return service.revoke_feed(db, identity, body, request, actor)


@router.get("/calendar-feeds/{identity}/content")
def calendar_content(identity: UUID, request: Request, db: Database, capability: str = ""):
    content = service.render_feed(db, identity, capability, request)
    return Response(
        content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "no-store, private",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="ocote.ics"',
        },
    )


@router.get("/notification-connectors")
def connectors(actor: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    service.require_connectors(db)
    return listing(
        db,
        select(NotificationConnector),
        NotificationConnector,
        service.connector_view,
        limit,
        cursor,
    )


@router.post("/notification-connectors", status_code=201)
def create_connector(body: ConnectorWrite, request: Request, actor: Administrator, db: Database):
    return service.save_connector(db, None, body, request, actor)


@router.patch("/notification-connectors/{identity}")
def update_connector(
    identity: UUID, body: ConnectorWrite, request: Request, actor: Administrator, db: Database
):
    return service.save_connector(db, identity, body, request, actor)


@router.post("/notification-connectors/{identity}/tests")
def test_connector(
    identity: UUID, body: ConnectorTest, request: Request, actor: Administrator, db: Database
):
    return service.test_connector(db, identity, body, request, actor)


@router.post("/notification-connectors/{identity}/activate")
def activate_connector(
    identity: UUID, body: Reauthenticated, request: Request, actor: Administrator, db: Database
):
    return service.activate_connector(db, identity, body, request, actor, True)


@router.post("/notification-connectors/{identity}/deactivate")
def deactivate_connector(
    identity: UUID, body: Reauthenticated, request: Request, actor: Administrator, db: Database
):
    return service.activate_connector(db, identity, body, request, actor, False)


@router.get("/notification-connectors/{identity}/health-checks")
def connector_checks(
    identity: UUID, actor: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    service.require_connectors(db)
    service.connector_for(db, identity)
    return listing(
        db,
        select(NotificationConnectorCheck).where(
            NotificationConnectorCheck.connector_id == identity
        ),
        NotificationConnectorCheck,
        lambda record: {
            key: getattr(record, key)
            for key in (
                "id",
                "config_version",
                "status",
                "result_code",
                "latency_ms",
                "created_at",
            )
        },
        limit,
        cursor,
    )


@router.get("/notification-rules")
def rules(actor: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    service.require_module(db, "notifications")
    return listing(db, select(NotificationRule), NotificationRule, service.rule_view, limit, cursor)


@router.post("/notification-rules", status_code=201)
def create_rule(body: RuleWrite, request: Request, actor: Administrator, db: Database):
    return service.save_rule(db, None, body, request, actor)


@router.patch("/notification-rules/{identity}")
def update_rule(
    identity: UUID, body: RuleWrite, request: Request, actor: Administrator, db: Database
):
    return service.save_rule(db, identity, body, request, actor)


@router.get("/notifications/service-principals")
def notification_principals(
    actor: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None
):
    service.require_module(db, "notifications")
    return listing(
        db,
        select(ServicePrincipal),
        ServicePrincipal,
        lambda row: {
            key: getattr(row, key)
            for key in (
                "id",
                "version",
                "name",
                "department_ids",
                "approved_scopes",
                "is_active",
            )
        },
        limit,
        cursor,
    )


@router.put("/notifications/service-principals/{identity}")
def notification_principal(
    identity: UUID, body: PrincipalWrite, request: Request, actor: Administrator, db: Database
):
    service.reauthenticate(db, actor, body, request)
    values = CollaborationPrincipalWrite.model_validate(
        body.model_dump(exclude={"current_password"})
    )
    return collaboration.write_principal(
        db, actor, identity, values, request, notification_context=True
    )
