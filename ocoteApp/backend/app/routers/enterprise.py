import base64
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.core.errors import CommandError
from app.models.enterprise import CalendarConfig, CalendarHoliday
from app.models.platform import IntegrationConfig
from app.schemas.enterprise import (
    BrandingReset,
    BrandingWrite,
    CalendarPreview,
    CalendarWrite,
    FlagWrite,
    HolidayWrite,
    LogoUpload,
    ObjectActivation,
    ObjectWrite,
    PolicyWrite,
    Reauthenticated,
)
from app.services import enterprise as service
from app.services import object_integrations as providers
from app.services.identity import Administrator, CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["configuration"])


@router.get("/configuration")
def configuration(actor: CurrentUser, db: Database):
    return service.configuration(db, actor)


@router.get("/admin/configuration")
def admin_configuration(actor: Administrator, db: Database):
    return service.configuration(db, actor, admin=True)


@router.put("/admin/security-policy")
def security_policy(body: PolicyWrite, request: Request, actor: Administrator, db: Database):
    return service.save_policy(db, body, request, actor)


@router.put("/admin/feature-flags")
def feature_flag(body: FlagWrite, request: Request, actor: Administrator, db: Database):
    return service.save_flag(db, body, request, actor)


@router.put("/admin/branding")
def branding(body: BrandingWrite, request: Request, actor: Administrator, db: Database):
    return service.save_branding(db, body, request, actor)


@router.post("/admin/branding/reset")
def reset_branding(body: BrandingReset, request: Request, actor: Administrator, db: Database):
    values = body.model_dump()
    return service.save_branding(
        db,
        BrandingWrite(
            **values,
            organization_name="OCOTE",
            welcome_text="",
            footer_text="",
            token_overrides={},
            logo_asset_id=None,
        ),
        request,
        actor,
    )


@router.post("/admin/branding/logo", status_code=201)
def upload_logo(body: LogoUpload, request: Request, actor: Administrator, db: Database):
    try:
        content = base64.b64decode(body.content.get_secret_value(), validate=True)
    except ValueError:
        raise CommandError(422, "INVALID_LOGO_ENCODING") from None
    return service.upload_logo(db, content, body.media_type, body, request, actor)


@router.get("/branding/logo/{identity}")
def logo(identity: UUID, actor: CurrentUser, db: Database):
    record = service.read_logo(db, identity, actor)
    return Response(
        record.content,
        media_type=record.media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def listing(db, query, model, projector, limit, cursor):
    service.require_page_size(db, limit)
    if cursor:
        query = query.where(model.id > cursor)
    rows = list(db.scalars(query.order_by(model.id).limit(limit + 1)))
    return {
        "items": [projector(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/admin/calendars")
def calendars(
    actor: Administrator,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
    cursor: UUID | None = None,
):
    return listing(db, select(CalendarConfig), CalendarConfig, service.calendar_view, limit, cursor)


@router.post("/admin/calendars", status_code=201)
def create_calendar(body: CalendarWrite, request: Request, actor: Administrator, db: Database):
    return service.save_calendar(db, None, body, request, actor)


@router.put("/admin/calendars/{identity}")
def update_calendar(
    identity: UUID, body: CalendarWrite, request: Request, actor: Administrator, db: Database
):
    return service.save_calendar(db, identity, body, request, actor)


@router.get("/admin/calendars/{identity}/holidays")
def holidays(
    identity: UUID,
    year: Annotated[int, Query(ge=1900, le=9998)],
    actor: Administrator,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
    cursor: UUID | None = None,
):
    from datetime import date

    query = select(CalendarHoliday).where(
        CalendarHoliday.calendar_id == identity,
        CalendarHoliday.holiday_date >= date(year, 1, 1),
        CalendarHoliday.holiday_date < date(year + 1, 1, 1),
    )
    return listing(db, query, CalendarHoliday, service.holiday_view, limit, cursor)


@router.post("/admin/calendars/{identity}/holidays", status_code=201)
def create_holiday(
    identity: UUID, body: HolidayWrite, request: Request, actor: Administrator, db: Database
):
    return service.save_holiday(db, identity, None, body, request, actor)


@router.put("/admin/calendars/{identity}/holidays/{holiday_id}")
def update_holiday(
    identity: UUID,
    holiday_id: UUID,
    body: HolidayWrite,
    request: Request,
    actor: Administrator,
    db: Database,
):
    return service.save_holiday(db, identity, holiday_id, body, request, actor)


@router.post("/calendar/preview")
def calendar_preview(body: CalendarPreview, actor: CurrentUser, db: Database):
    return service.preview_calendar(
        db, actor, body.department_id, body.start_date, body.days, body.mode
    )


@router.post("/admin/calendar-preview")
def admin_calendar_preview(body: CalendarPreview, actor: Administrator, db: Database):
    return service.preview_calendar(
        db, actor, body.department_id, body.start_date, body.days, body.mode
    )


@router.get("/admin/object-storage")
def object_providers(
    actor: Administrator,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
    cursor: UUID | None = None,
):
    return listing(
        db,
        select(IntegrationConfig).where(IntegrationConfig.kind == "object_storage"),
        IntegrationConfig,
        providers.view,
        limit,
        cursor,
    )


@router.post("/admin/object-storage", status_code=201)
def create_object_provider(body: ObjectWrite, request: Request, actor: Administrator, db: Database):
    return providers.save(db, None, body, request, actor)


@router.put("/admin/object-storage/{identity}")
def update_object_provider(
    identity: UUID, body: ObjectWrite, request: Request, actor: Administrator, db: Database
):
    return providers.save(db, identity, body, request, actor)


@router.post("/admin/object-storage/{identity}/test")
def test_object_provider(
    identity: UUID, body: Reauthenticated, request: Request, actor: Administrator, db: Database
):
    return providers.test(db, identity, body, request, actor)


@router.post("/admin/object-storage/{identity}/activation")
def activate_object_provider(
    identity: UUID, body: ObjectActivation, request: Request, actor: Administrator, db: Database
):
    return providers.activate(db, identity, body, request, actor)
