from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.models.bulk import BackupRecord, RetentionPolicy
from app.models.collaboration import JobRun
from app.schemas.bulk import (
    AgentWrite,
    BackupRequest,
    ImportCommit,
    ImportCreate,
    ImportPreview,
    ReportCreate,
    RetentionWrite,
)
from app.schemas.enterprise import Reauthenticated
from app.services import advanced_operations as operations
from app.services import bulk as imports
from app.services import executive_reports as reports
from app.services.identity import CurrentUser, Database

router = APIRouter(prefix="/api/v1", tags=["bulk-and-operations"])
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/imports")
def import_jobs(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return imports.list_imports(db, user, limit=limit, cursor=cursor)


@router.post("/imports", status_code=201)
def create_import(body: ImportCreate, request: Request, user: CurrentUser, db: Database):
    return imports.create_import(db, user, body, request)


@router.get("/imports/{identity}")
def import_job(identity: UUID, request: Request, user: CurrentUser, db: Database):
    return imports.preview_detail(db, user, identity, request)


@router.post("/imports/{identity}/dry-run")
def preview_import(identity: UUID, body: ImportPreview, request: Request,
                   user: CurrentUser, db: Database):
    return imports.preview_import(db, user, identity, body, request)


@router.post("/imports/{identity}/commit")
def commit_import(identity: UUID, body: ImportCommit, request: Request,
                  user: CurrentUser, db: Database):
    return imports.commit_import(db, user, identity, body, request)


@router.get("/executive-reports")
def executive_reports(user: CurrentUser, db: Database, limit: Limit = 5,
                      cursor: UUID | None = None):
    return reports.list_reports(db, user, limit=limit, cursor=cursor)


@router.post("/executive-reports", status_code=201)
def create_report(body: ReportCreate, request: Request, user: CurrentUser, db: Database):
    return reports.create_report(db, user, body, request)


@router.get("/executive-reports/{identity}")
def executive_report(identity: UUID, user: CurrentUser, db: Database):
    return reports.report_view(reports.report_record(db, user, identity))


@router.get("/executive-reports/{identity}/content")
def report_content(identity: UUID, request: Request, user: CurrentUser, db: Database):
    return reports.download_report(db, user, identity, request)


@router.get("/admin/operations/health")
def health(request: Request, user: CurrentUser, db: Database):
    return operations.health(db, user, request)


@router.get("/admin/operations/agent")
def agent(user: CurrentUser, db: Database):
    operations.authorize(db, user)
    return operations.agent_view(operations.agent_record(db))


@router.get("/admin/operations/principals")
def operation_principals(user: CurrentUser, db: Database, limit: Limit = 5,
                         cursor: UUID | None = None):
    return operations.principals(db, user, limit=limit, cursor=cursor)


@router.post("/admin/operations/agent")
def register_agent(body: AgentWrite, request: Request, user: CurrentUser, db: Database):
    return operations.register_agent(db, user, body, request)


@router.post("/admin/operations/agent/tests")
def test_agent(body: Reauthenticated, request: Request, user: CurrentUser, db: Database):
    return operations.test_agent(db, user, body, request)


@router.post("/admin/operations/agent/activate")
def activate_agent(body: Reauthenticated, request: Request, user: CurrentUser, db: Database):
    return operations.activate_agent(db, user, body, request)


@router.post("/admin/operations/agent/deactivate")
def deactivate_agent(body: Reauthenticated, request: Request, user: CurrentUser, db: Database):
    return operations.deactivate_agent(db, user, body, request)


@router.get("/admin/operations/backups")
def backups(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return operations.page(db, user, BackupRecord, limit=limit, cursor=cursor)


@router.post("/admin/operations/backups", status_code=202)
def request_backup(body: BackupRequest, request: Request, user: CurrentUser, db: Database):
    return operations.request_backup(db, user, body, request)


@router.post("/admin/operations/backups/{identity}/verify", status_code=202)
def verify_backup(identity: UUID, body: BackupRequest, request: Request,
                  user: CurrentUser, db: Database):
    return operations.request_backup(db, user, body, request, source_id=identity)


@router.get("/admin/operations/jobs")
def jobs(user: CurrentUser, db: Database, limit: Limit = 5, cursor: UUID | None = None):
    return operations.page(db, user, JobRun, limit=limit, cursor=cursor)


@router.get("/admin/operations/retention-policies")
def retention_policies(user: CurrentUser, db: Database, limit: Limit = 5,
                       cursor: UUID | None = None):
    return operations.page(db, user, RetentionPolicy, limit=limit, cursor=cursor)


@router.post("/admin/operations/retention-policies", status_code=201)
def create_retention(body: RetentionWrite, request: Request, user: CurrentUser, db: Database):
    return operations.write_retention(db, user, body, request)


@router.patch("/admin/operations/retention-policies/{identity}")
def update_retention(identity: UUID, body: RetentionWrite, request: Request,
                     user: CurrentUser, db: Database):
    return operations.write_retention(db, user, body, request, identity)