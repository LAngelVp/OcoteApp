from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import AwareDatetime
from starlette.concurrency import run_in_threadpool

from app.routers.auth import set_sso_cookie
from app.schemas.enterprise import Reauthenticated
from app.schemas.integrations import (
    APIKeyIssue,
    ConnectorTest,
    ConnectorWrite,
    ExternalLinkDeactivate,
    ExternalLinkWrite,
    PrincipalWrite,
    ServiceTaskUpdate,
    WebhookReplay,
    WebhookSubscriptionWrite,
)
from app.schemas.operations import TaskCreate
from app.services import devops, federation, outgoing_webhooks
from app.services import integrations as service
from app.services.identity import Administrator, CurrentUser, Database, TokenService

router = APIRouter(prefix="/api/v1", tags=["integrations"])
Limit = Annotated[int, Query(ge=1, le=50)]


@router.get("/integrations/configs")
def configs(user: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return service.connectors(db, user, limit, cursor)


@router.post("/integrations/configs", status_code=201)
def create_config(body: ConnectorWrite, request: Request, user: Administrator, db: Database):
    return service.save_connector(db, None, body, request, user)


@router.patch("/integrations/configs/{identity}")
def update_config(
    identity: UUID, body: ConnectorWrite, request: Request, user: Administrator, db: Database,
):
    return service.save_connector(db, identity, body, request, user)


@router.post("/integrations/configs/{identity}/test")
def test_config(
    identity: UUID, body: ConnectorTest, request: Request, response: Response,
    user: Administrator, db: Database, tokens: TokenService,
):
    result, browser = service.test_connector(db, tokens, identity, body, request, user)
    if browser is not None:
        set_sso_cookie(response, result["transaction_id"], browser)
    return result


@router.get("/integrations/configs/{identity}/checks")
def config_checks(identity: UUID, user: Administrator, db: Database, limit: Limit = 5,
                   cursor: UUID | None = None):
    return service.connector_checks(db, identity, user, limit, cursor)


@router.post("/integrations/configs/{identity}/activate")
def activate_config(
    identity: UUID, body: Reauthenticated, request: Request, user: Administrator, db: Database,
):
    return service.activate_connector(db, identity, body, request, user)


@router.post("/integrations/configs/{identity}/deactivate")
def deactivate_config(
    identity: UUID, body: Reauthenticated, request: Request, user: Administrator, db: Database,
):
    return service.deactivate_connector(db, identity, body, request, user)


@router.get("/integrations/external-identities")
def identities(user: Administrator, db: Database, limit: Limit = 5,
                cursor: UUID | None = None, user_id: UUID | None = None):
    return federation.bindings(db, user, limit, cursor, user_id)


@router.post("/integrations/external-identities/{identity}/revoke")
def revoke_identity(
    identity: UUID, body: Reauthenticated, request: Request, user: Administrator, db: Database,
):
    return federation.revoke_binding(db, identity, body, request, user)


@router.get("/tasks/{task_id}/external-links")
def external_links(task_id: UUID, user: CurrentUser, db: Database, limit: Limit = 5,
                   cursor: UUID | None = None):
    return devops.links(db, user, task_id, limit, cursor)


@router.get("/tasks/{task_id}/external-link-providers")
def external_link_providers(task_id: UUID, user: CurrentUser, db: Database, limit: Limit = 5,
                             cursor: UUID | None = None):
    return devops.providers(db, user, task_id, limit, cursor)


@router.post("/tasks/{task_id}/external-links", status_code=201)
def create_external_link(task_id: UUID, body: ExternalLinkWrite, request: Request,
                         user: CurrentUser, db: Database):
    return devops.create_link(db, user, task_id, body, request)


@router.post("/tasks/{task_id}/external-links/{link_id}/deactivate")
def deactivate_external_link(task_id: UUID, link_id: UUID, body: ExternalLinkDeactivate,
                             request: Request, user: CurrentUser, db: Database):
    return devops.deactivate_link(db, user, task_id, link_id, body, request)


@router.get("/integrations/devops/{integration_id}/inbox")
def devops_inbox(integration_id: UUID, user: Administrator, db: Database, limit: Limit = 5,
                  cursor: UUID | None = None):
    return devops.inbox(db, user, integration_id, limit, cursor)


@router.post("/integrations/devops/{integration_id}/events", status_code=202)
async def devops_event(integration_id: UUID, request: Request, db: Database):
    body = await request.body()
    return await run_in_threadpool(
        devops.receive, db, integration_id, request.headers, body, request
    )


@router.get("/integrations/service-principals")
def principals(user: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return service.principal_list(db, user, limit, cursor)


@router.post("/integrations/service-principals", status_code=201)
def create_principal(body: PrincipalWrite, request: Request, user: Administrator, db: Database):
    return service.save_principal(db, None, body, request, user)


@router.patch("/integrations/service-principals/{identity}")
def update_principal(
    identity: UUID, body: PrincipalWrite, request: Request, user: Administrator, db: Database,
):
    return service.save_principal(db, identity, body, request, user)


@router.get("/integrations/api-keys")
def keys(user: Administrator, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return service.keys(db, user, limit, cursor)


@router.post("/integrations/api-keys", status_code=201)
def issue_key(body: APIKeyIssue, request: Request, user: Administrator, db: Database):
    return service.issue_key(db, body, request, user)


@router.post("/integrations/api-keys/{identity}/rotate", status_code=201)
def rotate_key(
    identity: UUID, body: APIKeyIssue, request: Request, user: Administrator, db: Database,
):
    return service.rotate_key(db, identity, body, request, user)


@router.post("/integrations/api-keys/{identity}/revoke")
def revoke_key(
    identity: UUID, body: Reauthenticated, request: Request, user: Administrator, db: Database,
):
    return service.revoke_key(db, identity, body, request, user)


@router.get("/integrations/webhook-subscriptions")
def webhook_subscriptions(user: Administrator, db: Database, limit: Limit = 5,
                           cursor: UUID | None = None):
    return outgoing_webhooks.subscriptions(db, user, limit, cursor)


@router.post("/integrations/webhook-subscriptions", status_code=201)
def create_webhook_subscription(body: WebhookSubscriptionWrite, request: Request,
                                 user: Administrator, db: Database):
    return outgoing_webhooks.save_subscription(db, None, body, request, user)


@router.patch("/integrations/webhook-subscriptions/{identity}")
def update_webhook_subscription(identity: UUID, body: WebhookSubscriptionWrite, request: Request,
                                 user: Administrator, db: Database):
    return outgoing_webhooks.save_subscription(db, identity, body, request, user)


@router.post("/integrations/webhook-subscriptions/{identity}/replay", status_code=201)
def replay_webhook(identity: UUID, body: WebhookReplay, request: Request,
                    user: Administrator, db: Database):
    return outgoing_webhooks.replay(db, identity, body, request, user)


@router.get("/integrations/webhook-deliveries")
def webhook_deliveries(user: Administrator, db: Database, limit: Limit = 5,
                        cursor: UUID | None = None, subscription_id: UUID | None = None,
                        state: Literal["pending", "sending", "delivered", "dead_letter",
                                       "cancelled"] | None = None,
                        since: AwareDatetime | None = None, until: AwareDatetime | None = None):
    return outgoing_webhooks.deliveries(db, user, limit, cursor, subscription_id=subscription_id,
                                       state=state, since=since, until=until)


@router.get("/integrations/webhook-deliveries/{identity}/attempts")
def webhook_attempts(identity: UUID, user: Administrator, db: Database, limit: Limit = 5,
                       cursor: UUID | None = None):
    return outgoing_webhooks.attempts(db, user, identity, limit, cursor)


@router.get("/service/tasks")
def tasks(request: Request, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    actor = service.authenticate_key(db, request, "tasks:read")
    return service.technical_tasks(db, actor, limit, cursor)


@router.get("/service/tasks/{identity}")
def task(identity: UUID, request: Request, db: Database):
    actor = service.authenticate_key(db, request, "tasks:read")
    return service.operation.task_view(db, service.technical_task(db, actor, identity), actor)


@router.post("/service/tasks", status_code=201)
def create_task(body: TaskCreate, request: Request, db: Database):
    actor = service.authenticate_key(db, request, "tasks:create")
    return service.create_technical_task(db, actor, body, request)


@router.patch("/service/tasks/{identity}")
def update_task(identity: UUID, body: ServiceTaskUpdate, request: Request, db: Database):
    actor = service.authenticate_key(db, request, "tasks:update_metadata")
    return service.update_technical_task(db, actor, identity, body, request)