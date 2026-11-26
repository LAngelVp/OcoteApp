"""One bounded recurrence pass using runtime only; no external delivery or daemon."""

import argparse
import json
import os
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5
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


def checked_budget(value):
    try:
        budget = int(value)
        if not 1 <= budget <= 100:
            raise ValueError
        return budget
    except ValueError:
        raise argparse.ArgumentTypeError("Budget must be between 1 and 100") from None


def idempotency_key(schedule, through_date, limit):
    return uuid5(
        NAMESPACE_URL, f"ocote:f9:{schedule.id}:{schedule.next_due_at}:{through_date}:{limit}"
    )


def tick(factory, budget):
    if type(budget) is not int or not 1 <= budget <= 100:
        raise CommandError(422, "RECURRENCE_LIMIT_INVALID")
    report = {"processed": 0, "generated": 0, "paused": 0, "conflicts": 0, "failures": 0}
    if (BACKEND_DIR / ".local" / "maintenance.json").exists():
        raise CommandError(503, "MAINTENANCE")
    with factory.begin() as database:
        config_lock(database, exclusive=False)
        if database.scalar(text("SELECT current_user")) != "ocote_runtime":
            raise CommandError(503, "RUNTIME_IDENTITY_REQUIRED")
        if database.scalar(text("SELECT version_num FROM alembic_version")) != "20261125_0008":
            raise CommandError(503, "F9_REVISION_REQUIRED")
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
        if report["processed"] >= budget:
            break
        if (BACKEND_DIR / ".local" / "maintenance.json").exists():
            raise CommandError(503, "MAINTENANCE")
        try:
            with factory.begin() as database:
                config_lock(database, exclusive=False)
                schedule = database.get(RecurrenceSchedule, identity)
                if schedule is None or not schedule.enabled or schedule.next_due_at is None:
                    continue
                owner = database.get(User, schedule.owner_user_id)
                if owner is None:
                    raise CommandError(503, "RECURRENCE_CONTEXT_INTEGRITY_FAILURE")
                actor = SimpleNamespace(
                    id=owner.id,
                    role=owner.role,
                    department_id=owner.department_id,
                    actor_service_id=schedule.service_principal_id,
                )
                through = (
                    operations.instant(database).astimezone(ZoneInfo(schedule.timezone)).date()
                )
                limit = budget - report["processed"]
                result = collaboration.run_schedule(
                    database,
                    actor,
                    identity,
                    RecurrenceRun(
                        expected_version=schedule.version,
                        idempotency_key=idempotency_key(schedule, through, limit),
                        through_date=through.isoformat(),
                        limit=limit,
                        reason="Ejecucion interna de recurrencia F9 autorizada por programacion.",
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
    parser.add_argument("--limit", type=checked_budget, default=100)
    arguments = parser.parse_args()
    if os.environ.get("PGPASSWORD"):
        print("RUNTIME_MUST_NOT_INHERIT_ADMINISTRATIVE_PASSWORD")
        return 1
    engine = None
    try:
        engine = create_database_engine(Settings())
        report = tick(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), arguments.limit
        )
        print(json.dumps(report))
        return int(report["failures"] > 0)
    except CommandError as error:
        print(error.code)
    except Exception:
        print("F9_WORKER_FAILED")
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
