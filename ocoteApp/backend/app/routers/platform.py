from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.models.platform import EncryptedSecret, SecretKeyVersion
from app.schemas.platform import (
    Activation,
    Change,
    Custody,
    IntegrationWrite,
    Kind,
    Purpose,
    Rotate,
    SecretWrite,
)
from app.services import platform as service
from app.services.identity import Administrator, Database

router = APIRouter(prefix="/api/v1/admin", tags=["platform"])


@router.get("/health")
def health(request: Request, actor: Administrator, db: Database):
    return service.health(db, request)


@router.patch("/custody")
def custody(body: Custody, request: Request, actor: Administrator, db: Database):
    return service.update_custody(db, body, request, actor)


@router.put("/integrations/{kind}")
def configure(
    kind: Kind, body: IntegrationWrite, request: Request, actor: Administrator, db: Database
):
    return service.save_integration(db, kind, body, request, actor)


@router.post("/integrations/{kind}/test")
def test(kind: Kind, body: Change, request: Request, actor: Administrator, db: Database):
    return service.test_integration(db, kind, body, request, actor)


@router.post("/integrations/{kind}/activation")
def activate(kind: Kind, body: Activation, request: Request, actor: Administrator, db: Database):
    return service.activate_integration(db, kind, body, request, actor)


@router.get("/vault")
def secrets(actor: Administrator, db: Database):
    records = list(
        db.scalars(
            select(EncryptedSecret)
            .distinct(EncryptedSecret.owner_id, EncryptedSecret.purpose)
            .order_by(
                EncryptedSecret.owner_id,
                EncryptedSecret.purpose,
                EncryptedSecret.secret_version.desc(),
            )
            .limit(101)
        )
    )
    if len(records) > 100:
        from app.core.errors import CommandError

        raise CommandError(413, "VAULT_METADATA_LIMIT_EXCEEDED")
    keys = list(
        db.scalars(
            select(SecretKeyVersion)
            .distinct(SecretKeyVersion.purpose)
            .order_by(SecretKeyVersion.purpose, SecretKeyVersion.epoch.desc())
        )
    )
    return {
        "items": [service.secret_view(row) for row in records],
        "keys": [{"purpose": row.purpose, "epoch": row.epoch} for row in keys],
    }


@router.put("/vault/{owner}/{purpose}")
def replace(
    owner: UUID,
    purpose: Purpose,
    body: SecretWrite,
    request: Request,
    actor: Administrator,
    db: Database,
):
    return service.write_secret(db, owner, purpose, body, request, actor)


@router.post("/vault/rotate")
def rotate(body: Rotate, request: Request, actor: Administrator, db: Database):
    return service.rotate(db, body, request, actor)
