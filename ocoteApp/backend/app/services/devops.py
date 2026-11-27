import json
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select

from app.core.devops import external_reference, inbound_event
from app.core.errors import CommandError
from app.core.security import now
from app.models.identity import User
from app.models.integrations import TaskExternalLink, WebhookInbox
from app.models.platform import IntegrationConfig
from app.services import identity, integrations
from app.services import operations as operation
from app.services.administration import check_version
from app.services.collaboration import resource, save_record
from app.services.enterprise import require_page_size


def task_context(db, actor, task_id, *, write=False):
    integrations.modules(db, "devops")
    operation.configuration(db)
    if not actor.is_active:
        raise CommandError(401, "INVALID_CREDENTIALS")
    return resource(db, actor, "task", task_id, write=write,
                    roles=("admin", "lider", "colaborador"))


def connector(db, integration_id, objective, *, lock=False):
    record = integrations.connector_for(db, integration_id, lock=lock)
    if record.kind != "devops" or not record.is_active:
        raise CommandError(404, "DEVOPS_PROVIDER_UNAVAILABLE")
    if record.scope_kind == "department" and record.department_id != objective.department_id:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    return record


def providers(db, actor, task_id, limit, cursor=None):
    _task, _plan, objective = task_context(db, actor, task_id)
    require_page_size(db, limit)
    query = select(IntegrationConfig).where(
        IntegrationConfig.kind == "devops", IntegrationConfig.is_active,
        or_(IntegrationConfig.scope_kind == "organization",
            IntegrationConfig.department_id == objective.department_id),
    )
    if cursor:
        query = query.where(IntegrationConfig.id > cursor)
    rows = list(db.scalars(query.order_by(IntegrationConfig.id).limit(limit + 1)))
    return {"items": [{"id": record.id, "name": record.name, "provider": record.provider,
                       "repositories": record.config["repositories"]} for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def links(db, actor, task_id, limit, cursor=None):
    task, _plan, _objective = task_context(db, actor, task_id)
    require_page_size(db, limit)
    query = select(TaskExternalLink).where(TaskExternalLink.task_id == task.id)
    if cursor:
        query = query.where(TaskExternalLink.id > cursor)
    rows = list(db.scalars(query.order_by(TaskExternalLink.id).limit(limit + 1)))
    return {"items": [operation.state(record) for record in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def create_link(db, actor, task_id, body, request):
    task, _plan, objective = task_context(db, actor, task_id, write=True)
    check_version(task, body.expected_version)
    record = connector(db, body.integration_id, objective)
    config, credential = integrations.connector_material(db, record, request)
    prepared = (record.config_revision, record.version, actor.id, actor.token_version)
    provider_id, task_id = record.id, task.id
    db.commit()
    try:
        verified = external_reference(
            config, json.loads(credential)["access_token"], body.repository_id, body.kind,
            body.external_id, transport=getattr(request.app.state, "integration_transport", None),
        )
    finally:
        credential = None
    db.expire_all()
    db.info.pop("f8_flags", None)
    db.info.pop("f8_policy", None)
    identity.config_lock(db, exclusive=False)
    actor = db.get(User, prepared[2], populate_existing=True)
    if actor is None or not actor.is_active or actor.token_version != prepared[3]:
        raise CommandError(401, "INVALID_CREDENTIALS")
    task, _plan, objective = task_context(db, actor, task_id, write=True)
    check_version(task, body.expected_version)
    record = connector(db, provider_id, objective, lock=True)
    if (record.config_revision, record.version) != prepared[:2]:
        raise CommandError(409, "CONNECTOR_CHANGED_DURING_VERIFICATION")
    duplicate = db.scalar(select(TaskExternalLink.id).where(
        TaskExternalLink.task_id == task.id, TaskExternalLink.integration_id == record.id,
        TaskExternalLink.repository_id == body.repository_id,
        TaskExternalLink.kind == body.kind, TaskExternalLink.external_id == body.external_id,
    ))
    if duplicate is not None:
        raise CommandError(409, "EXTERNAL_LINK_ALREADY_RECORDED")
    moment = now()
    link = TaskExternalLink(
        id=uuid4(), version=1, created_at=moment, updated_at=moment, task_id=task.id,
        integration_id=record.id, repository_id=body.repository_id, kind=body.kind,
        external_id=body.external_id, canonical_url=verified["canonical_url"],
        safe_projection=verified["safe_projection"], created_by=actor.id, deactivated_at=None,
    )
    save_record(db, actor, request, link, {}, "external_link_created", body.reason)
    return operation.state(link)


def deactivate_link(db, actor, task_id, link_id, body, request):
    task, _plan, _objective = task_context(db, actor, task_id, write=True)
    record = db.scalar(select(TaskExternalLink).where(
        TaskExternalLink.id == link_id, TaskExternalLink.task_id == task.id,
    ).with_for_update())
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    check_version(record, body.expected_version)
    if record.deactivated_at is None:
        before = operation.state(record)
        record.deactivated_at = now()
        identity.touch(record)
        save_record(db, actor, request, record, before, "external_link_deactivated", body.reason)
    return operation.state(record)


def inbox(db, actor, integration_id, limit, cursor=None):
    integrations.administrator(actor)
    integrations.modules(db, "devops")
    require_page_size(db, limit)
    record = integrations.connector_for(db, integration_id)
    if record.kind != "devops":
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    query = select(WebhookInbox).where(WebhookInbox.integration_id == record.id)
    if cursor:
        query = query.where(WebhookInbox.id > cursor)
    rows = list(db.scalars(query.order_by(WebhookInbox.id).limit(limit + 1)))
    fields = ("id", "created_at", "integration_id", "delivery_id", "event_type", "request_id")
    return {"items": [{key: getattr(item, key) for key in fields} for item in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def receive(db, integration_id, headers, body, request):
    integrations.modules(db, "devops")
    record = integrations.connector_for(db, integration_id, lock=True)
    if record.kind != "devops" or not record.is_active:
        raise CommandError(401, "DEVOPS_EVENT_INVALID")
    config, credential = integrations.connector_material(db, record, request)
    try:
        event = inbound_event(config, json.loads(credential)["webhook_secret"], headers, body)
    finally:
        credential = None
    previous = db.scalar(select(WebhookInbox).where(
        WebhookInbox.integration_id == record.id,
        WebhookInbox.delivery_id == event["delivery_id"],
    ))
    if previous is not None:
        if previous.body_hash != event["body_hash"]:
            raise CommandError(409, "DEVOPS_DELIVERY_COLLISION")
        return {"accepted": True, "duplicate": True, "id": previous.id}
    recent = db.scalar(select(func.count()).select_from(WebhookInbox).where(
        WebhookInbox.integration_id == record.id,
        WebhookInbox.created_at >= now() - timedelta(minutes=1),
    ))
    if recent >= config.api_endpoint.rate_per_minute:
        raise CommandError(429, "DEVOPS_EVENT_RATE_LIMIT")
    inbox = WebhookInbox(
        id=uuid4(), created_at=now(), integration_id=record.id,
        request_id=UUID(request.state.request_id), **event,
    )
    db.add(inbox)
    db.flush([inbox])
    identity.audit(db, request, "devops_event_received", entity="webhook_inbox",
                   entity_id=inbox.id, after={"integration_id": str(record.id),
                                             "event_type": event["event_type"]})
    db.flush()
    return {"accepted": True, "duplicate": False, "id": inbox.id}