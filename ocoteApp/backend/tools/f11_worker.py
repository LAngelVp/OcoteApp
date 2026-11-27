"""Bounded F11 webhooks/notifications/recurrence passes using runtime only."""

import argparse
import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Date, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import CommandError
from app.db.engine import create_database_engine
from app.models.collaboration import RecurrenceSchedule
from app.models.identity import User
from app.schemas.collaboration import RecurrenceRun
from app.services import collaboration, operations
from app.services.enterprise import enabled
from app.services.identity import config_lock
from app.services.notification_worker import tick as notification_tick
from app.services.webhook_worker import budget, tick
from tools.f9_worker import idempotency_key


def checked_limit(value):
    try:
        return budget(int(value))
    except (ValueError, CommandError):
        raise argparse.ArgumentTypeError("Limit must be between 1 and 100") from None


def require_f11_runtime(database):
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise CommandError(503, "MAINTENANCE")
    config_lock(database, exclusive=False)
    if database.scalar(text("SELECT current_user")) != "ocote_runtime":
        raise CommandError(503, "RUNTIME_IDENTITY_REQUIRED")
    if database.scalar(text("SELECT version_num FROM alembic_version")) != "20261126_0010":
        raise CommandError(503, "F11_REVISION_REQUIRED")


def recurrence_tick(factory, limit):
    budget(limit)
    report = {"processed": 0, "generated": 0, "paused": 0, "conflicts": 0, "failures": 0}

    with factory.begin() as database:
        require_f11_runtime(database)
        if not all(enabled(database, code) for code in ("recurrence", "templates", "calendar")):
            return report
        moment = operations.instant(database)
        identities = list(
            database.scalars(
                select(RecurrenceSchedule.id)
                .where(
                    RecurrenceSchedule.enabled,
                    RecurrenceSchedule.next_due_at.is_not(None),
                    RecurrenceSchedule.next_due_at
                    <= func.timezone(RecurrenceSchedule.timezone, moment).cast(Date),
                )
                .order_by(RecurrenceSchedule.next_due_at, RecurrenceSchedule.id)
                .limit(100)
            )
        )
    for identity in identities:
        if report["processed"] >= limit:
            break
        try:
            with factory.begin() as database:
                require_f11_runtime(database)
                schedule = database.get(RecurrenceSchedule, identity)
                if schedule is None or not schedule.enabled or schedule.next_due_at is None:
                    continue
                owner = database.get(User, schedule.owner_user_id)
                if owner is None:
                    raise CommandError(503, "RECURRENCE_CONTEXT_INTEGRITY_FAILURE")
                actor = SimpleNamespace(
                    id=owner.id, role=owner.role, department_id=owner.department_id,
                    actor_service_id=schedule.service_principal_id,
                )
                through = (
                    operations.instant(database).astimezone(ZoneInfo(schedule.timezone)).date()
                )
                remaining = limit - report["processed"]
                result = collaboration.run_schedule(
                    database, actor, identity,
                    RecurrenceRun(
                        expected_version=schedule.version,
                        idempotency_key=idempotency_key(schedule, through, remaining),
                        through_date=through.isoformat(), limit=remaining,
                        reason="Ejecucion interna de recurrencia F11 con autorizacion vigente.",
                    ),
                    SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4()))),
                )
                processed = result["processed_count"]
                generated = 0 if result["replayed"] else len(result["generated_ids"])
                paused = int(result["job"]["state"] == "paused")
            report["processed"] += processed
            report["generated"] += generated
            report["paused"] += paused
        except CommandError as error:
            report["conflicts" if error.status == 409 else "failures"] += 1
        except DBAPIError:
            report["failures"] += 1
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("webhooks", "notifications", "recurrence"), default="webhooks"
    )
    parser.add_argument("--principal", type=UUID)
    parser.add_argument("--limit", type=checked_limit, default=100)
    arguments = parser.parse_args()
    if arguments.mode != "recurrence" and arguments.principal is None:
        parser.error("--principal is required for webhooks/notifications")
    if os.environ.get("PGPASSWORD"):
        print("RUNTIME_MUST_NOT_INHERIT_ADMINISTRATIVE_PASSWORD")
        return 1
    engine = None
    try:
        engine = create_database_engine(Settings())
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory.begin() as database:
            require_f11_runtime(database)
        report = (
            recurrence_tick(factory, arguments.limit)
            if arguments.mode == "recurrence"
            else (tick if arguments.mode == "webhooks" else notification_tick)(
                factory, arguments.principal, arguments.limit
            )
        )
        print(json.dumps(report))
        return int(
            any(report.get(key, 0) > 0 for key in ("rejected", "ambiguous", "failed", "failures"))
        )
    except CommandError as error:
        print(error.code)
    except Exception:
        print("F11_WORKER_FAILED")
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())