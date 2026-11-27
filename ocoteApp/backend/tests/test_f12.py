import io
import zipfile

import pytest
from openpyxl import Workbook, load_workbook

from app.core.errors import CommandError
from app.core.tabular import ImportLimits, parse_table, pdf_report, xlsx_report


def workbook_bytes(*rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    return content.getvalue()


@pytest.mark.parametrize("file_format", ["csv", "xlsx"])
def test_f12_parse_table_round_trip(file_format):
    content = (b"title,due_date\r\nOCOTE,2026-12-01\r\n" if file_format == "csv" else
               workbook_bytes(["title", "due_date"], ["OCOTE", "2026-12-01"]))
    assert parse_table(content, file_format, ImportLimits(10, 1048576)) == (
        ["title", "due_date"], [["OCOTE", "2026-12-01"]],
    )


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t=", " \r=", "\ufeff="])
def test_f12_import_never_accepts_formula_prefix(prefix):
    content = ("title\r\n\"" + prefix + "SUM(A1)\"\r\n").encode("utf-8")
    with pytest.raises(CommandError):
        parse_table(content, "csv", ImportLimits(10, 1048576))


@pytest.mark.parametrize("content", [b"", b"a,a\n1,2", b"a,b\n1", b"a\n\x00", b"a\n\xff"])
def test_f12_invalid_csv_fails_closed(content):
    with pytest.raises(CommandError):
        parse_table(content, "csv", ImportLimits(10, 1048576))


def test_f12_xlsx_formula_is_rejected_without_evaluation():
    with pytest.raises(CommandError, match="IMPORT_ACTIVE_CONTENT_FORBIDDEN"):
        parse_table(workbook_bytes(["title"], ["=HYPERLINK(\"https://example.test\")"]),
                    "xlsx", ImportLimits(10, 1048576))


@pytest.mark.parametrize("name,value", [
    ("xl/vbaProject.bin", b"macro"),
    ("../outside.xml", b"<root/>"),
    ("xl/externalLinks/link.xml", b"<root/>"),
    ("extra.xml", b"<!DOCTYPE x [<!ENTITY x SYSTEM 'file:///secret'>]><x>&x;</x>"),
    ("external.rels", b"<Relationships><Relationship TargetMode='External' "
                      b"Target='https://example.test'/></Relationships>"),
])
def test_f12_xlsx_active_or_external_content_is_rejected(name, value):
    content = io.BytesIO(workbook_bytes(["title"], ["OCOTE"]))
    with zipfile.ZipFile(content, "a") as archive:
        archive.writestr(name, value)
    with pytest.raises(CommandError):
        parse_table(content.getvalue(), "xlsx", ImportLimits(10, 1048576))


def test_f12_zip_bomb_and_rows_are_bounded():
    content = io.BytesIO(workbook_bytes(["title"], ["OCOTE"]))
    with zipfile.ZipFile(content, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.xml", b"<root>" + b"x" * 1048576 + b"</root>")
    with pytest.raises(CommandError):
        parse_table(content.getvalue(), "xlsx", ImportLimits(10, 1048576))
    with pytest.raises(CommandError, match="IMPORT_TOO_LARGE"):
        parse_table(b"title\na\nb\n", "csv", ImportLimits(1, 1024))


def test_f12_xlsx_export_is_text_without_formulas_or_links():
    values = ["=SUM(A1)", "+1", "-1", "@test", "\t=CMD()", "https://example.test"]
    content = xlsx_report(["title"], [[value] for value in values], {"summary": "=CMD()"},
                          1048576)
    workbook = load_workbook(io.BytesIO(content), data_only=False)
    for row in workbook["OCOTE"].iter_rows(min_row=2):
        assert row[0].data_type == "s"
        assert row[0].hyperlink is None
        assert not row[0].value.startswith(("=", "+", "-", "@", "\t"))
    assert workbook["Contexto"]["B1"].data_type == "s"
    workbook.close()


def test_f12_pdf_plain_text_and_output_limit():
    content = pdf_report(["Titulo"], [["OCOTE <img src='https://example.test'>"]],
                         {"Periodo": "2026"}, 1048576)
    assert content.startswith(b"%PDF-")
    with pytest.raises(CommandError, match="EXPORT_TOO_LARGE"):
        pdf_report(["Titulo"], [["OCOTE"]], {}, 1)
    with pytest.raises(CommandError, match="EXPORT_TOO_LARGE"):
        xlsx_report(["Titulo"], [["OCOTE"]], {}, 1)


@pytest.mark.parametrize("purpose", ["import_staging", "report_result"])
def test_f12_large_payload_is_bound_and_separate_from_secrets(purpose):
    from dataclasses import replace
    from uuid import uuid4

    from app.core.vault import Vault

    vault = Vault(b"s" * 32, uuid4(), "synthetic-root")
    key = vault.new_key(purpose, 1)
    value = vault.encrypt_payload(key, uuid4(), 1, b"synthetic" * 10000)
    assert vault.decrypt_payload(key, value) == b"synthetic" * 10000
    for changed in (replace(value, owner_id=uuid4()), replace(value, version=2),
                    replace(value, ciphertext=value.ciphertext[:-1] + b"!")):
        with pytest.raises(CommandError, match="VAULT_UNAVAILABLE"):
            vault.decrypt_payload(key, changed)
    with pytest.raises(CommandError, match="VAULT_UNAVAILABLE"):
        vault.decrypt(key, value)
    with pytest.raises(CommandError, match="VAULT_UNAVAILABLE"):
        vault.encrypt(key, uuid4(), 1, b"x" * 65537)


def test_f12_payload_rejects_other_purposes_and_unbounded_content():
    from uuid import uuid4

    from app.core.vault import Vault

    vault = Vault(b"s" * 32, uuid4(), "synthetic-root")
    with pytest.raises(CommandError, match="VAULT_UNAVAILABLE"):
        vault.encrypt_payload(vault.new_key("backup", 1), uuid4(), 1, b"content")
    for content in (b"", b"x" * 16777217):
        with pytest.raises(CommandError, match="VAULT_UNAVAILABLE"):
            vault.encrypt_payload(vault.new_key("import_staging", 1), uuid4(), 1, content)


def test_f12_native_excel_civil_dates_are_not_datetimes():
    from datetime import datetime

    content = workbook_bytes(["title", "due_date"], ["OCOTE", datetime(2026, 12, 1)])
    assert parse_table(content, "xlsx", ImportLimits(10, 1048576))[1] == [
        ["OCOTE", "2026-12-01"],
    ]


@pytest.mark.parametrize("entity_type,role,allowed", [
    ("plan", "admin", True), ("plan", "gerente", True), ("plan", "lider", False),
    ("objective", "admin", True), ("objective", "gerente", True),
    ("objective", "lider", False), ("task", "admin", True), ("task", "lider", True),
    ("task", "gerente", False), ("task", "colaborador", False),
])
def test_f12_import_roles_are_enforced_before_processing(monkeypatch, entity_type, role, allowed):
    from types import SimpleNamespace

    from app.services import bulk

    monkeypatch.setattr(bulk.enterprise, "require_module", lambda *_args: None)
    policy = SimpleNamespace(import_max_rows=1000, import_max_bytes=10485760)
    monkeypatch.setattr(bulk.enterprise, "policy", lambda _db: policy)
    if allowed:
        assert bulk.authorize_import(None, SimpleNamespace(role=role), entity_type) is policy
    else:
        with pytest.raises(CommandError, match="FORBIDDEN"):
            bulk.authorize_import(None, SimpleNamespace(role=role), entity_type)


def test_f12_preview_performs_no_domain_writes(monkeypatch):
    from types import SimpleNamespace

    from app.services import bulk

    monkeypatch.setattr(bulk, "authorize_import", lambda *_args: ImportLimits(10, 1048576))
    monkeypatch.setattr(bulk, "validate_domain", lambda *_args: [])
    monkeypatch.setattr(bulk, "configuration_hash", lambda *_args: "a" * 64)
    monkeypatch.setattr(bulk, "authorize_import", lambda *_args: SimpleNamespace(
        import_max_rows=10, import_max_bytes=1048576,
    ))

    class ReadOnly:
        def __getattr__(self, _name):
            raise AssertionError("Preview attempted a database side effect")

    record = SimpleNamespace(entity_type="plan", file_format="csv", file_hash="b" * 64)
    mapping = {"title": "title", "start": "start_date", "end": "due_date",
               "horizon": "horizon_type"}
    rows, references, context_hash, preview_hash = bulk.preview_rows(
        ReadOnly(), object(), record, mapping,
        b"title,start,end,horizon\nSynthetic,2026-01-01,2026-12-31,annual\n",
    )
    assert rows[0]["data"]["title"] == "Synthetic" and rows[0]["errors"] == []
    assert references == [] and context_hash == "a" * 64 and len(preview_hash) == 64


@pytest.mark.parametrize("target", ["original_due_date", "completed_at", "role", "stage_id"])
def test_f12_mapping_cannot_modify_originals_or_final_state(target):
    from app.services.bulk import normalize_row

    with pytest.raises(CommandError, match="IMPORT_MAPPING_INVALID"):
        normalize_row("task", {"column": target}, ["column"], ["synthetic"])


def test_f12_executive_rows_use_only_supplied_sealed_snapshot():
    from app.services.executive_reports import sealed_rows

    original = {"title": "Sealed title", "department": {"name": "Sealed department"},
                "assignee": {"display_name": "Sealed assignee"}, "stage": {"name": "Done"},
                "original_due_date": "2026-01-01", "due_date": "2026-01-02",
                "completed_at": None, "progress_percent": 0, "punctuality_status": "pending"}
    row = sealed_rows([original])[0]
    assert row[:4] == ["Sealed title", "Sealed department", "Sealed assignee", "Done"]
    assert row[4:6] == ["2026-01-01", "2026-01-02"]
    assert row[7] == 0


def test_f12_executive_reports_deny_collaborator_before_queries():
    from types import SimpleNamespace

    from app.services.executive_reports import authorize

    with pytest.raises(CommandError, match="FORBIDDEN"):
        authorize(None, SimpleNamespace(role="colaborador"))


def test_f12_agent_protocol_has_no_pickle_and_detects_tampering():
    from uuid import uuid4

    from app.core.operations_agent import decode, envelope, pipe_address

    secret = b"s" * 32
    payload = {"command": "probe", "nonce": str(uuid4()), "protocol_version": 1}
    encoded = envelope(payload, secret)
    assert decode(encoded, secret) == payload
    for changed in (encoded.replace(b"probe", b"shell"), b"not-json", b"{}", b"x" * 16385):
        with pytest.raises(CommandError, match="OPERATIONS_AGENT_UNAVAILABLE"):
            decode(changed, secret)
    assert pipe_address(uuid4()).startswith("\\\\.\\pipe\\OCOTE-operations-")
    with pytest.raises(ValueError):
        pipe_address("https://example.test")


def test_f12_capture_context_is_separate_expiring_and_never_renews(monkeypatch, tmp_path):
    from tools import f11_local, f12_local

    contents = {}

    class Seal:
        def __init__(self, path, context):
            assert context != f11_local.OPERATOR_CONTEXT
            self.path = path

        def create(self, value):
            self.path.touch(exist_ok=False)
            contents[self.path] = value

        def read(self):
            return contents[self.path]

    monkeypatch.setattr(f12_local, "OSSealedFile", Seal)
    monkeypatch.setattr(f12_local, "private_directory", lambda _path: None)
    path = tmp_path / "synthetic.dpapi"
    f12_local.save_authorization("synthetic-password", path=path, issued_at=100)
    assert f12_local.authorization(path=path, current_time=101)["expires_at"] == 3700
    with pytest.raises(CommandError, match="NO_RENEWAL"):
        f12_local.save_authorization("synthetic-password", path=path, issued_at=102)
    for moment in (99, 3700, float("nan"), True):
        with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
            f12_local.authorization(path=path, current_time=moment)


@pytest.mark.parametrize("status", [0, 1])
def test_f12_final_gates_never_release_when_local_inputs_are_missing(monkeypatch, status):
    from tools import f12_local

    revoked = []
    monkeypatch.setattr(f12_local, "revoke", lambda: revoked.append(True))
    monkeypatch.delenv("PGPASSWORD", raising=False)
    with pytest.raises(CommandError):
        f12_local.run_final_gates(None)
    assert revoked == [True]


def test_f12_release_rejects_missing_authorization_before_admin_connection(monkeypatch, tmp_path):
    from tools import f12_release

    def missing():
        raise CommandError(503, "LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Administrative connection before a fresh capture")

    monkeypatch.setattr(f12_release.operator, "authorization", missing)
    monkeypatch.setattr(f12_release.local, "admin_connection", forbidden)
    with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
        f12_release.apply(tmp_path)


@pytest.mark.parametrize("defect", [None, "head", "seed", "missing", "history"])
def test_f12_release_additive_projection_is_strict(defect):
    import copy

    from tools import f12_release

    before = {"tables": ["alembic_version", "release_history", "users"], "rows": {
        "alembic_version": ["source"], "release_history": [], "users": ['{"id":"preserved"}'],
    }}
    after = copy.deepcopy(before)
    after["tables"] += sorted(f12_release.ADDED)
    after["rows"].update({name: [] for name in f12_release.ADDED})
    after["rows"]["alembic_version"] = ['{"version_num": "20261126_0011"}']
    if defect == "head":
        after["rows"]["alembic_version"] = ["wrong"]
    elif defect == "seed":
        after["rows"]["import_jobs"] = ["unsolicited"]
    elif defect == "missing":
        after["tables"].remove("users")
    elif defect == "history":
        after["rows"]["users"] = []
    if defect:
        with pytest.raises(RuntimeError):
            f12_release.upgraded(before, after)
    else:
        f12_release.upgraded(before, after)


def test_f12_backup_archive_is_encrypted_bound_and_tamper_evident(monkeypatch, tmp_path):
    from uuid import uuid4

    from tools import f12_operations as agent

    monkeypatch.setattr(agent.local, "protect", lambda _path: None)
    source, encrypted, restored = (tmp_path / name for name in ("plain", "encrypted", "restored"))
    source.write_bytes(b"synthetic-private-backup" * 10000)
    instance, location = uuid4(), uuid4()
    metadata = agent.encrypt_archive(source, encrypted, b"k" * 32, instance, location)
    assert b"synthetic-private-backup" not in encrypted.read_bytes()
    agent.decrypt_archive(encrypted, restored, b"k" * 32, metadata, instance, location)
    assert restored.read_bytes() == source.read_bytes()
    restored.unlink()
    for key, identity in ((b"s" * 32, instance), (b"k" * 32, uuid4())):
        with pytest.raises(CommandError, match="BACKUP_AUTHENTICATION_FAILED"):
            agent.decrypt_archive(encrypted, restored, key, metadata, identity, location)
        assert not restored.exists()
    restored.write_bytes(b"existing-preserved-content")
    with pytest.raises(CommandError, match="BACKUP_TARGET_ALREADY_EXISTS"):
        agent.decrypt_archive(encrypted, restored, b"k" * 32, metadata, instance, location)
    assert restored.read_bytes() == b"existing-preserved-content"


def test_f12_preview_returns_only_normalized_visible_cells():
    from app.services.bulk import public_preview

    assert public_preview({"title": "Synthetic", "due_date": "2026-12-01",
                           "description": "private-description", "unmapped": "private-source",
                           "custom_fields": {"private": "value"}}) == {
        "title": "Synthetic", "due_date": "2026-12-01",
    }


@pytest.mark.parametrize("revision,valid", [("20261126_0010", False), ("20261126_0011", True)])
def test_f12_worker_cannot_run_against_f11_origin(monkeypatch, tmp_path, revision, valid):
    from types import SimpleNamespace

    from tools import f12_worker

    monkeypatch.setattr(f12_worker, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(f12_worker, "config_lock", lambda *_args, **_kwargs: None)
    database = SimpleNamespace(scalar=lambda query: "ocote_runtime" if "current_user" in str(query)
                               else revision)
    if valid:
        f12_worker.require_runtime(database)
    else:
        with pytest.raises(CommandError, match="F12_REVISION_REQUIRED"):
            f12_worker.require_runtime(database)


@pytest.mark.parametrize("role", ["gerente", "lider"])
def test_f12_import_list_filters_entity_and_department_before_limit(monkeypatch, role):
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.dialects import postgresql

    from app.services import bulk

    queries = []
    monkeypatch.setattr(bulk.enterprise, "require_module", lambda *_args: None)
    monkeypatch.setattr(bulk.enterprise, "require_page_size", lambda *_args: None)

    def scalars(statement):
        queries.append(statement.compile(dialect=postgresql.dialect()))
        return []

    user = SimpleNamespace(id=uuid4(), role=role, department_id=uuid4())
    bulk.list_imports(SimpleNamespace(scalars=scalars), user, limit=5)
    assert "import_jobs.entity_type" in str(queries[0]).split("WHERE")[1]
    if role == "lider":
        assert "import_jobs.department_id" in str(queries[0]).split("WHERE")[1]
    assert "LIMIT" in str(queries[0])


def test_f12_untrusted_nested_metadata_is_sanitized():
    from app.services.bulk import normalize_row

    with pytest.raises(CommandError, match="IMPORT_METADATA_INVALID"):
        normalize_row("task", {"field": "custom_fields"}, ["field"],
                      ["[" * 4000 + "]" * 4000])


@pytest.mark.parametrize("secret", [" " + "s" * 32, "\u00f1" * 32])
def test_f12_agent_authentication_matches_the_separate_operator_contract(secret):
    from uuid import uuid4

    from pydantic import ValidationError

    from app.schemas.bulk import AgentWrite

    with pytest.raises(ValidationError):
        AgentWrite(expected_version=0, reason="Synthetic authentication check",
                   current_password="synthetic", service_principal_id=uuid4(),
                   capabilities=["backup"], destination_ref=uuid4(),
                   authentication_secret=secret)


def test_f12_postgres_fixture_uses_real_put_routes_and_current_versions():
    from types import SimpleNamespace

    from test_f12_postgres import configure_f12

    from app.routers.enterprise import router

    codes = ("imports", "executive_reports", "advanced_operations", "evaluations", "exports")
    versions = {code: index + 2 for index, code in enumerate(codes)}
    calls = []

    def get(path):
        assert path == "/api/v1/admin/configuration"
        return SimpleNamespace(status_code=200, text="synthetic", json=lambda: {
            "security_policy": {"version": 7},
            "modules": [{"code": code, "version": version} for code, version in versions.items()],
        })

    def put(path, *, json):
        assert any(route.path == path and "PUT" in route.methods for route in router.routes)
        assert json["expected_version"] == (7 if path.endswith("security-policy")
                                            else versions[json["code"]])
        calls.append((path, json))
        return SimpleNamespace(status_code=200, text="synthetic")

    configure_f12(SimpleNamespace(get=get, put=put))
    assert len(calls) == 6
    assert [body["code"] for _path, body in calls[1:]] == list(codes)


@pytest.mark.parametrize("model_name,column_name", [
    ("job", "operation_payload"), ("import", "result_ids"),
])
def test_f12_nullable_jsonb_preserves_sql_null_without_reinterpreting_json_null(
    model_name, column_name,
):
    import json

    from sqlalchemy import JSON
    from sqlalchemy.dialects import postgresql

    from app.models.bulk import ImportJob
    from app.models.collaboration import JobRun

    model = JobRun if model_name == "job" else ImportJob
    column = model.__table__.c[column_name]
    bind = column.type.bind_processor(postgresql.dialect())
    assert column.type.none_as_null is True
    assert bind(None) is None
    assert bind(JSON.NULL) == "null"
    value = {"destination_ref": "synthetic", "source_backup_id": None}
    assert json.loads(bind(value)) == value


@pytest.mark.parametrize("captured", ["matching", "other", None])
def test_f12_leader_cannot_open_global_or_other_department_staging(monkeypatch, captured):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services import bulk

    department = uuid4()
    owner = SimpleNamespace(id=uuid4(), role="lider", department_id=department)
    record = SimpleNamespace(entity_type="task", department_id=(
        department if captured == "matching" else uuid4() if captured == "other" else None
    ))
    monkeypatch.setattr(bulk, "authorize_import", lambda *_args: None)
    database = SimpleNamespace(scalar=lambda _query: record)
    if captured == "matching":
        assert bulk.import_record(database, owner, uuid4()) is record
    else:
        with pytest.raises(CommandError, match="RESOURCE_NOT_FOUND"):
            bulk.import_record(database, owner, uuid4())


def test_f12_database_diagnostics_never_expose_sql_parameters_or_primary_values():
    import json
    from types import SimpleNamespace

    from test_f12_postgres import safe_database_error

    context = SimpleNamespace(
        statement="private SQL text", parameters={"password": "private-password"},
        original_exception=SimpleNamespace(sqlstate="23514", diag=SimpleNamespace(
            constraint_name="ck_f12_operation_payload", table_name="job_runs", column_name=None,
            message_primary="private-primary-value",
        )),
    )
    result = safe_database_error(context)
    assert result["sqlstate"] == "23514"
    assert result["constraint_name"] == "ck_f12_operation_payload"
    assert result["table_name"] == "job_runs"
    assert result["guard"] is None
    assert "private" not in json.dumps(result)