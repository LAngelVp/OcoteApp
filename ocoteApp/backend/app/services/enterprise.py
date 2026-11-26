import hashlib
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.core.branding import recode_logo, validate_palette
from app.core.errors import CommandError
from app.core.security import compromised_passwords, now, verify_password
from app.models.enterprise import (
    CalendarConfig,
    CalendarHoliday,
    FeatureFlag,
    OrganizationProfile,
    PrivateAsset,
    SecurityPolicy,
)
from app.models.identity import Department, SystemSetting
from app.schemas.enterprise import FUTURE_MODULES, MODULES, PolicyValues
from app.services.identity import audit, touch
from app.services.platform import instance, revision


def reauthenticate(db, actor, body, request):
    db.refresh(actor, with_for_update=True)
    settings, moment = policy(db, required=False), now()
    if actor.locked_until and actor.locked_until > moment:
        audit(
            db, request, "security_denied", actor=actor.id, entity="users",
            entity_id=actor.id, after={"code": "REAUTHENTICATION_LOCKED"}, outcome="denied",
        )
        raise CommandError(429, "REAUTHENTICATION_LOCKED", persist=True)
    if not verify_password(actor.password_hash, body.current_password.get_secret_value()):
        window = timedelta(seconds=settings.failed_window_seconds if settings else 60)
        if actor.failed_window_at is None or moment - actor.failed_window_at >= window:
            actor.failed_window_at, actor.failed_attempt_count = moment, 0
        actor.failed_attempt_count += 1
        if actor.failed_attempt_count >= (settings.failed_attempt_threshold if settings else 3):
            actor.locked_until = moment + timedelta(
                seconds=settings.lockout_seconds if settings else 60
            )
        touch(actor)
        audit(
            db, request, "security_denied", actor=actor.id, entity="users",
            entity_id=actor.id, after={"code": "REAUTHENTICATION_REQUIRED"}, outcome="denied",
        )
        raise CommandError(401, "REAUTHENTICATION_REQUIRED", persist=True)
    if actor.failed_attempt_count or actor.failed_window_at or actor.locked_until:
        actor.failed_attempt_count = 0
        actor.failed_window_at = actor.locked_until = None
        touch(actor)
        db.flush()


def policy(db, *, required=True):
    if "f8_policy" not in db.info:
        db.info["f8_policy"] = db.scalar(select(SecurityPolicy))
    record = db.info["f8_policy"]
    if record is None and required:
        raise CommandError(503, "SECURITY_CONFIGURATION_REQUIRED")
    return record


def policy_view(record):
    if record is None:
        return None
    return {
        "id": record.id,
        "version": record.version,
        **{name: getattr(record, name) for name in PolicyValues.model_fields},
        "password_max_length": 128,
        "compromised_check_required": True,
    }


def enabled(db, code):
    if code not in MODULES:
        return False
    if "f8_flags" not in db.info:
        db.info["f8_flags"] = {
            record.code: record.enabled for record in db.scalars(select(FeatureFlag))
        }
    return db.info["f8_flags"].get(code) is True


def require_module(db, code):
    if not enabled(db, code):
        raise CommandError(403, "MODULE_DISABLED_OR_UNCONFIGURED")


def require_page_size(db, size):
    record = policy(db)
    if size not in record.page_sizes:
        raise CommandError(422, "PAGE_SIZE_NOT_ALLOWED")


def validate_password(db, value):
    settings = policy(db)
    known_compromised = {
        "passwordpassword",
        "Password123!",
        "Password123456!",
        "123456789012",
        "qwertyuiop123",
        "correct horse battery staple",
    }
    requirements = (
        (settings.require_upper, any(character.isupper() for character in value)),
        (settings.require_lower, any(character.islower() for character in value)),
        (settings.require_digit, any(character.isdigit() for character in value)),
        (
            settings.require_symbol,
            any(not character.isalnum() and not character.isspace() for character in value),
        ),
    )
    if (
        not settings.password_min_length <= len(value) <= 128
        or value in known_compromised
        or value.casefold() in compromised_passwords()
        or any(required and not met for required, met in requirements)
    ):
        raise CommandError(422, "PASSWORD_POLICY_NOT_MET")


def request_modules(db, request):
    segments = request.url.path.strip("/").split("/")[2:]
    if not segments:
        return
    resource = segments[0]
    if request.method == "POST":
        if resource == "tasks" and len(segments) == 3 and segments[-1] == "subtasks":
            require_module(db, "subtasks")
        if segments[-1] == "due-date-requests" and resource in {"tasks", "subtasks"}:
            require_module(db, "due_date_requests")
        if resource == "exports":
            require_module(db, "exports")
        if resource == "evaluations" and len(segments) == 1:
            require_module(db, "evaluations")
    if resource in {"kanban", "timeline", "analytics"}:
        require_module(db, resource)
    if resource == "calendar":
        require_module(db, "calendar")


def session_policy(db, record, claims=None, *, activity=True):
    settings = policy(db, required=False)
    if settings is None:
        return
    from sqlalchemy import func, update

    from app.models.identity import RefreshSession

    started, last_seen = db.execute(
        select(
            func.min(RefreshSession.created_at),
            func.max(func.coalesce(RefreshSession.last_seen_at, RefreshSession.created_at)),
        ).where(RefreshSession.family_id == record.family_id)
    ).one()
    moment = now()
    if (
        started is None
        or moment >= started + timedelta(seconds=settings.refresh_absolute_seconds)
        or moment >= last_seen + timedelta(seconds=settings.idle_timeout_seconds)
        or (
            claims is not None and moment.timestamp() - claims["iat"] >= settings.access_ttl_seconds
        )
    ):
        raise CommandError(401, "SESSION_POLICY_EXPIRED")
    if activity:
        available = db.scalar(
            select(RefreshSession.id)
            .where(RefreshSession.id == record.id)
            .with_for_update(skip_locked=True)
        )
        if available is not None:
            db.execute(
                update(RefreshSession)
                .where(RefreshSession.id == available)
                .values(last_seen_at=func.greatest(RefreshSession.last_seen_at, moment))
            )


def changed(db, record, body, request, actor, fields):
    record.configuration_revision_id = revision(db, request, actor, record, body.reason, fields)
    db.add(record)
    db.flush()
    return record


def save_policy(db, body, request, actor):
    reauthenticate(db, actor, body, request)
    record = db.scalar(select(SecurityPolicy).with_for_update())
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = SecurityPolicy(id=uuid4(), instance_id=instance(db).id)
    else:
        touch(record)
    for name, value in body.values.model_dump().items():
        setattr(record, name, value)
    changed(db, record, body, request, actor, PolicyValues.model_fields)
    db.info["f8_policy"] = record
    return policy_view(record)


def save_flag(db, body, request, actor):
    reauthenticate(db, actor, body, request)
    record = db.scalar(select(FeatureFlag).where(FeatureFlag.code == body.code).with_for_update())
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = FeatureFlag(id=uuid4(), code=body.code)
    else:
        touch(record)
    record.enabled = body.enabled
    changed(db, record, body, request, actor, ["enabled"])
    return {"code": record.code, "enabled": record.enabled, "version": record.version}


def organization_name(db):
    return db.scalar(select(SystemSetting).where(SystemSetting.key == "organization_name"))


def branding_view(db):
    record = db.scalar(select(OrganizationProfile))
    name = organization_name(db)
    return {
        "version": record.version if record else 0,
        "organization_name": name.value if name else None,
        "organization_name_version": name.version if name else 0,
        "welcome_text": record.welcome_text if record else "",
        "footer_text": record.footer_text if record else "",
        "token_overrides": record.token_overrides if record else {},
        "logo_asset_id": record.logo_asset_id if record else None,
        "contrast": validate_palette(record.token_overrides if record else {}),
    }


def save_branding(db, body, request, actor):
    reauthenticate(db, actor, body, request)
    validate_palette(body.token_overrides)
    record = db.scalar(select(OrganizationProfile).with_for_update())
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    name = organization_name(db)
    if body.organization_name_version != (name.version if name else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if len(body.organization_name) > 120 and (name is None or name.value != body.organization_name):
        raise CommandError(422, "ORGANIZATION_NAME_TOO_LONG")
    if body.logo_asset_id is not None and db.get(PrivateAsset, body.logo_asset_id) is None:
        raise CommandError(422, "INVALID_PRIVATE_LOGO")
    if name is None:
        name = SystemSetting(
            id=uuid4(), key="organization_name", value=body.organization_name, updated_by=actor.id
        )
        db.add(name)
    elif name.value != body.organization_name:
        name.value, name.updated_by = body.organization_name, actor.id
        touch(name)
    if record is None:
        record = OrganizationProfile(id=uuid4(), instance_id=instance(db).id)
    else:
        touch(record)
    for field in ("welcome_text", "footer_text", "token_overrides", "logo_asset_id"):
        setattr(record, field, getattr(body, field))
    changed(
        db,
        record,
        body,
        request,
        actor,
        ["organization_name", "welcome_text", "footer_text", "token_overrides", "logo_asset_id"],
    )
    return branding_view(db)


def scanner(db, request):
    injected = getattr(request.app.state, "logo_scanner", None)
    if injected is not None:
        return injected
    from app.core.evidence import ClamAV
    from app.models.platform import IntegrationConfig

    record = db.scalar(select(IntegrationConfig).where(IntegrationConfig.kind == "clamav"))
    if record is None or not record.is_active or record.tested_version != record.config_revision:
        raise CommandError(503, "LOGO_SCANNER_UNAVAILABLE")
    return ClamAV(record.config["port"], record.config["timeout"])


def upload_logo(db, content, media_type, body, request, actor):
    reauthenticate(db, actor, body, request)
    if body.expected_version != branding_view(db)["version"]:
        raise CommandError(409, "VERSION_CONFLICT")
    content, media_type, width, height, version = recode_logo(
        content, media_type, scanner(db, request)
    )
    record = PrivateAsset(
        id=uuid4(),
        kind="logo",
        media_type=media_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        width=width,
        height=height,
        scanned_at=now(),
        scan_version=version,
    )
    changed(db, record, body, request, actor, ["logo_uploaded"])
    return {"id": record.id, "media_type": media_type, "width": width, "height": height}


def read_logo(db, identity, actor):
    profile = db.scalar(select(OrganizationProfile))
    if actor.role != "admin" and (profile is None or profile.logo_asset_id != identity):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    record = db.get(PrivateAsset, identity)
    if record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if hashlib.sha256(record.content).hexdigest() != record.sha256:
        raise CommandError(503, "PRIVATE_ASSET_INTEGRITY_FAILURE")
    return record


def department_scope(db, scope, identity):
    if scope == "department":
        record = db.get(Department, identity)
        if record is None or not record.is_active:
            raise CommandError(422, "INVALID_DEPARTMENT")


def calendar_view(record):
    return {
        name: getattr(record, name)
        for name in (
            "id",
            "version",
            "name",
            "scope_kind",
            "department_id",
            "weekday_mask",
            "inheritance",
        )
    }


def save_calendar(db, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    department_scope(db, body.scope_kind, body.department_id)
    record = db.get(CalendarConfig, identity, with_for_update=True) if identity else None
    if identity and record is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = CalendarConfig(
            id=uuid4(), scope_kind=body.scope_kind, department_id=body.department_id
        )
    else:
        if (record.scope_kind, record.department_id) != (body.scope_kind, body.department_id):
            raise CommandError(409, "CALENDAR_SCOPE_IMMUTABLE")
        touch(record)
    record.name, record.weekday_mask, record.inheritance = (
        body.name,
        body.weekday_mask,
        body.inheritance,
    )
    changed(db, record, body, request, actor, ["workdays", "inheritance", "name"])
    return calendar_view(record)


def holiday_view(record):
    return {
        name: getattr(record, name)
        for name in ("id", "version", "calendar_id", "holiday_date", "name", "is_active")
    }


def save_holiday(db, calendar_id, identity, body, request, actor):
    reauthenticate(db, actor, body, request)
    if db.get(CalendarConfig, calendar_id, with_for_update=True) is None:
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    record = db.get(CalendarHoliday, identity, with_for_update=True) if identity else None
    if identity and (record is None or record.calendar_id != calendar_id):
        raise CommandError(404, "RESOURCE_NOT_FOUND")
    if body.expected_version != (record.version if record else 0):
        raise CommandError(409, "VERSION_CONFLICT")
    if record is None:
        record = CalendarHoliday(
            id=uuid4(), calendar_id=calendar_id, holiday_date=body.holiday_date
        )
    else:
        if record.holiday_date != body.holiday_date:
            raise CommandError(409, "HOLIDAY_DATE_IMMUTABLE")
        touch(record)
    record.name, record.is_active = body.name, body.is_active
    changed(db, record, body, request, actor, ["name", "is_active"])
    return holiday_view(record)


def calendar_effective(db, department_id):
    global_calendar = db.scalar(
        select(CalendarConfig).where(CalendarConfig.scope_kind == "organization")
    )
    local = db.scalar(
        select(CalendarConfig).where(
            CalendarConfig.department_id == department_id, CalendarConfig.scope_kind == "department"
        )
    )
    selected = local if local and local.inheritance == "replace" else global_calendar
    if selected is None:
        raise CommandError(503, "CALENDAR_CONFIGURATION_REQUIRED")
    identities = [selected.id]
    if local and local.inheritance == "inherit" and local.id != selected.id:
        identities.append(local.id)
    return selected, identities


def working_offset(start, days, weekday_mask, holidays, mode):
    if type(days) is not int or not 0 <= days <= 365 or mode not in {"natural", "business"}:
        raise CommandError(422, "INVALID_CALENDAR_PREVIEW")
    if days > (date.max - start).days:
        raise CommandError(422, "CALENDAR_DATE_OUT_OF_RANGE")
    if mode == "natural":
        return start + timedelta(days=days)
    moment, remaining = start, days
    for _ in range(36500):
        if not remaining:
            return moment
        if moment == date.max:
            raise CommandError(422, "CALENDAR_DATE_OUT_OF_RANGE")
        moment += timedelta(days=1)
        if weekday_mask & (1 << moment.weekday()) and moment not in holidays:
            remaining -= 1
    raise CommandError(413, "CALENDAR_PREVIEW_LIMIT")


def preview_calendar(db, actor, department_id, start, days, mode):
    if actor.role in {"lider", "colaborador"}:
        if department_id not in {None, actor.department_id}:
            raise CommandError(404, "RESOURCE_NOT_FOUND")
        department_id = actor.department_id
    selected, identities = calendar_effective(db, department_id)
    holidays = set(
        db.scalars(
            select(CalendarHoliday.holiday_date).where(
                CalendarHoliday.calendar_id.in_(identities),
                CalendarHoliday.is_active,
                CalendarHoliday.holiday_date.between(
                    start, start + timedelta(days=min(36500, (date.max - start).days))
                ),
            )
        )
    )
    result = working_offset(start, days, selected.weekday_mask, holidays, mode)
    return {
        "start_date": start,
        "days": days,
        "mode": mode,
        "date": result,
        "timezone": "America/Mexico_City",
        "calendar_id": selected.id,
        "calendar_version": selected.version,
        "original_dates_changed": False,
    }


def configuration(db, actor, *, admin=False):
    flags = {record.code: record for record in db.scalars(select(FeatureFlag))}
    values = {
        "revision": db.scalar(
            text("SELECT coalesce(max(sequence),0) FROM configuration_revisions")
        ),
        "branding": branding_view(db),
        "page_sizes": policy(db, required=False).page_sizes if policy(db, required=False) else None,
        "flags": {code: flags[code].enabled if code in flags else None for code in sorted(MODULES)},
    }
    if admin:
        values["security_policy"] = policy_view(policy(db, required=False))
        values["modules"] = [
            {
                "code": code,
                "installed": code in MODULES,
                "enabled": flags[code].enabled if code in flags else None,
                "version": flags[code].version if code in flags else 0,
            }
            for code in sorted(MODULES | FUTURE_MODULES)
        ]
    return values
