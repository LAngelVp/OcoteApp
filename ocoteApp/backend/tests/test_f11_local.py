import json
import time

import pytest

from app.core.errors import CommandError
from tools import f11_local


def test_f11_capture_is_separate_expiring_and_never_renews(monkeypatch, tmp_path):
    from tools.f8_local import OPERATOR_CONTEXT as f8_context
    from tools.f9_local import OPERATOR_CONTEXT as f9_context
    from tools.f10_local import OPERATOR_CONTEXT as f10_context

    contents = {}

    class Seal:
        def __init__(self, path, context):
            assert context not in {f8_context, f9_context, f10_context}
            self.path = path

        def create(self, value):
            self.path.touch(exist_ok=False)
            contents[self.path] = value

        def read(self):
            return contents[self.path]

    monkeypatch.setattr(f11_local, "OSSealedFile", Seal)
    monkeypatch.setattr(f11_local, "private_directory", lambda _path: None)
    path = tmp_path / "synthetic.dpapi"
    f11_local.save_authorization("synthetic-password", path=path, issued_at=100)
    assert f11_local.authorization(path=path, current_time=101)["expires_at"] == 3700
    with pytest.raises(CommandError, match="FRESH_F11_CAPTURE_REQUIRED_NO_RENEWAL"):
        f11_local.save_authorization("synthetic-password", path=path, issued_at=102)
    for moment in (99, 3700, float("nan"), True):
        with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
            f11_local.authorization(path=path, current_time=moment)
    payload = json.loads(contents[path])
    payload["purpose"] = "ocote-f10-local-postgres-only"
    contents[path] = json.dumps(payload).encode()
    with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
        f11_local.authorization(path=path, current_time=101)


def test_f11_restore_diagnostics_never_include_row_values():
    from tools.f11_release import ReleaseFailure, snapshot_difference

    before = {"indexes": [("synthetic_index", "old")], "rows": {"users": ["sensitive"]}}
    restored = {"indexes": [("synthetic_index", "new")], "rows": {"users": ["private"]}}
    details = snapshot_difference(before, restored)
    assert details == {"sections": ["indexes", "rows"], "indexes": ["synthetic_index"]}
    error = ReleaseFailure("RESTORED_SNAPSHOT_DIFFERS", label="recorded", **details)
    encoded = json.dumps({"code": error.code, **error.details})
    assert "sensitive" not in encoded and "private" not in encoded
    assert str(error) == "RESTORED_SNAPSHOT_DIFFERS"


def test_f11_pg_failure_records_only_exit_and_sqlstate(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from tools import f11_release

    def run(_arguments, **kwargs):
        assert kwargs["env"]["PGPASSWORD"] == "synthetic-password"
        return SimpleNamespace(returncode=1, stderr=b"ERROR: 23514: sensitive-data")

    monkeypatch.setattr(f11_release.subprocess, "run", run)
    with pytest.raises(f11_release.ReleaseFailure) as failure:
        f11_release.pg_run([str(tmp_path / "pg_restore.exe")], "synthetic-password")
    encoded = f11_release.local.canonical(failure.value.details)
    assert b"sensitive-data" not in encoded and b"synthetic-password" not in encoded
    assert failure.value.details["exit_code"] == 1
    assert failure.value.details["command"] == "pg_restore"
    assert failure.value.details["sqlstates"] == ["23514"]


def test_f11_modules_are_installed_without_implicit_flags():
    from app.schemas.enterprise import MODULES, FlagWrite

    for code in ("sso", "devops", "api_keys", "outgoing_webhooks"):
        assert code in MODULES
        assert FlagWrite(
            code=code, enabled=True, expected_version=0,
            reason="Explicit UUID-only module registration test",
            current_password="Synthetic-password-123!",
        ).enabled


@pytest.mark.parametrize("failure", ["migration-protections", "pg1", None])
def test_f11_gates_order_and_always_revoke(monkeypatch, tmp_path, failure):
    calls = []
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setattr(
        f11_local, "authorization",
        lambda: {"password": "synthetic", "expires_at": time.time() + 3600},
    )
    monkeypatch.setattr(f11_local, "preflight", lambda **_kwargs: None)
    monkeypatch.setattr(f11_local, "private_directory", lambda _path: None)
    monkeypatch.setattr(f11_local, "write_private", lambda *_args: None)
    monkeypatch.setattr(f11_local, "revoke", lambda: calls.append("revoked"))
    monkeypatch.setattr(f11_local, "drain_api", lambda: calls.append("drained"))

    def run(arguments, _payload, output):
        calls.append(output.stem)
        if output.stem == "migration-protections":
            assert all("test_f11_postgres.py::" in name for name in arguments[-2:])
        return int(output.stem == failure)

    monkeypatch.setattr(f11_local, "run_authorized", run)
    assert f11_local.run_final_gates(tmp_path) == int(failure is not None)
    expected = ["migration-protections"]
    if failure != "migration-protections":
        expected.append("pg1")
    if failure is None:
        expected.extend(["drained", "release"])
    assert calls == [*expected, "revoked"]


def test_f11_revoke_removes_every_phase_seal(monkeypatch, tmp_path):
    paths = tuple(tmp_path / (phase + ".dpapi") for phase in ("f11", "f10", "f9", "f8"))
    for path in paths:
        path.touch()
    monkeypatch.setattr(f11_local, "authorization_paths", lambda: paths)
    f11_local.revoke()
    assert not any(path.exists() for path in paths)


def test_f11_preflight_rejects_old_capture_without_using_it(monkeypatch, tmp_path):
    paths = tuple(tmp_path / (phase + ".dpapi") for phase in ("f11", "f10", "f9", "f8"))
    paths[1].touch()
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setattr(f11_local, "authorization_paths", lambda: paths)
    with pytest.raises(CommandError, match="FRESH_F11_CAPTURE_REQUIRED_NO_RENEWAL"):
        f11_local.preflight()
    assert paths[1].exists()


def test_f11_release_preserves_old_values_and_rejects_missing_tables_or_seeds():
    import copy

    from tools import f11_release

    before = {
        "tables": ["alembic_version", "refresh_sessions", "feature_flags"],
        "rows": {
            "alembic_version": [json.dumps({"version_num": f11_release.SOURCE})],
            "refresh_sessions": [json.dumps({"id": "synthetic", "revoked_at": None})],
            "feature_flags": [],
        },
    }
    after = copy.deepcopy(before)
    after["tables"] += sorted(f11_release.ADDED)
    after["rows"].update({name: [] for name in f11_release.ADDED})
    after["rows"]["alembic_version"] = [json.dumps({"version_num": f11_release.HEAD})]
    after["rows"]["refresh_sessions"] = [
        json.dumps({"id": "synthetic", "revoked_at": None, "external_identity_id": None})
    ]
    f11_release.upgraded(before, after)
    removed = copy.deepcopy(after)
    removed["tables"].remove("feature_flags")
    with pytest.raises(RuntimeError, match="table set"):
        f11_release.upgraded(before, removed)
    changed = copy.deepcopy(after)
    changed["rows"]["refresh_sessions"] = [json.dumps({"id": "synthetic", "revoked_at": "changed"})]
    with pytest.raises(RuntimeError, match="Historical value changed"):
        f11_release.upgraded(before, changed)
    seeded = copy.deepcopy(after)
    seeded["rows"]["api_keys"] = [json.dumps({"id": "unsolicited"})]
    with pytest.raises(RuntimeError, match="business defaults"):
        f11_release.upgraded(before, seeded)


@pytest.mark.parametrize("revision", ["20261126_0010", "20261126_0009", "20261125_0008"])
def test_f11_recurrence_requires_own_head_and_keeps_fail_closed_modules(
    monkeypatch, tmp_path, revision,
):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from tools import f11_worker

    monkeypatch.setattr(f11_worker, "BACKEND_DIR", tmp_path)
    database = SimpleNamespace(
        scalar=lambda query: {
            "SELECT current_user": "ocote_runtime",
            "SELECT version_num FROM alembic_version": revision,
        }[str(query)]
    )
    factory = SimpleNamespace(begin=lambda: nullcontext(database))
    monkeypatch.setattr(f11_worker, "config_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(f11_worker, "enabled", lambda *_args: False)
    if revision == "20261126_0010":
        assert f11_worker.recurrence_tick(factory, 1) == {
            "processed": 0, "generated": 0, "paused": 0, "conflicts": 0, "failures": 0,
        }
    else:
        with pytest.raises(CommandError, match="F11_REVISION_REQUIRED"):
            f11_worker.recurrence_tick(factory, 1)


@pytest.mark.parametrize("mode", ["webhooks", "notifications", "recurrence"])
@pytest.mark.parametrize("revision", ["20261126_0010", "20261126_0009", "20261125_0008", None])
def test_f11_worker_modes_require_own_head_before_dispatch(
    monkeypatch, tmp_path, capsys, mode, revision,
):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    from uuid import uuid4

    from tools import f11_worker

    calls = []
    database = SimpleNamespace(
        scalar=lambda query: {
            "SELECT current_user": "ocote_runtime",
            "SELECT version_num FROM alembic_version": revision,
        }[str(query)]
    )
    factory = SimpleNamespace(begin=lambda: nullcontext(database))
    engine = SimpleNamespace(dispose=lambda: calls.append("disposed"))
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setattr(f11_worker, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(f11_worker, "Settings", lambda: None)
    monkeypatch.setattr(f11_worker, "create_database_engine", lambda _settings: engine)
    monkeypatch.setattr(f11_worker, "sessionmaker", lambda **_kwargs: factory)
    monkeypatch.setattr(f11_worker, "config_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sys, "argv", ["f11_worker", "--mode", mode, "--principal", str(uuid4())],
    )

    def dispatch(selected_mode, selected_factory, *_arguments):
        assert selected_factory is factory
        calls.append(selected_mode)
        return {"processed": 0}

    monkeypatch.setattr(f11_worker, "tick", lambda *args: dispatch("webhooks", *args))
    monkeypatch.setattr(
        f11_worker, "notification_tick", lambda *args: dispatch("notifications", *args),
    )
    monkeypatch.setattr(
        f11_worker, "recurrence_tick", lambda *args: dispatch("recurrence", *args),
    )
    if revision == "20261126_0010":
        assert f11_worker.main() == 0
        assert calls == [mode, "disposed"]
    else:
        assert f11_worker.main() == 1
        assert calls == ["disposed"]
        assert capsys.readouterr().out.strip() == "F11_REVISION_REQUIRED"


@pytest.mark.parametrize("revision", ["20261126_0009", "20261126_0010", "20261125_0008"])
def test_f11_notification_context_preserves_previous_head_and_scope_checks(
    monkeypatch, tmp_path, revision,
):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services import notification_worker

    monkeypatch.setattr(notification_worker, "BACKEND_DIR", tmp_path)
    principal = SimpleNamespace(
        is_active=True, department_ids=[uuid4()], approved_scopes=["notifications:dispatch"],
    )
    database = SimpleNamespace(
        scalar=lambda query: {
            "SELECT current_user": "ocote_runtime",
            "SELECT version_num FROM alembic_version": revision,
        }[str(query)],
        get=lambda *_args: principal,
    )
    monkeypatch.setattr(notification_worker, "config_lock", lambda *_args, **_kwargs: None)
    if revision == "20261125_0008":
        with pytest.raises(CommandError, match="F10_REVISION_REQUIRED"):
            notification_worker.context(database, uuid4())
    else:
        assert notification_worker.context(database, uuid4()) is principal
        principal.approved_scopes = []
        with pytest.raises(CommandError, match="NOTIFICATION_SERVICE_SCOPE_REQUIRED"):
            notification_worker.context(database, uuid4())


@pytest.mark.parametrize("difference", [None, "rows", "unknown_index", "semantics"])
def test_f11_restore_accepts_only_named_semantically_equal_indexes(monkeypatch, difference):
    from tools import f11_release

    calls = []
    before = {"indexes": [(name, "= ANY ((ARRAY[" + ", ".join(
        "'" + kind + "'::character varying" for kind in kinds) + "])::text[])" )
        for name, kinds in f11_release.INDEX_KINDS.items()], "rows": {"users": []}}
    recovered = {"indexes": [(name, f11_release.canonical_kind_predicate(
        definition, f11_release.INDEX_KINDS[name])) for name, definition in before["indexes"]],
                 "rows": {"users": []}}
    source, destination = object(), object()

    def signature(connection):
        calls.append(connection)
        return connection if difference == "semantics" else ("shape", "truth")

    monkeypatch.setattr(f11_release, "index_signature", signature)
    monkeypatch.setattr(f11_release, "provider_index_signature", signature)
    monkeypatch.setattr(f11_release, "index_properties", lambda *_args: ("extra-catalog",))
    if difference == "rows":
        recovered["rows"] = {"users": ["sensitive"]}
    if difference == "unknown_index":
        recovered["indexes"].append(("unapproved", "new"))
    if difference:
        with pytest.raises(f11_release.ReleaseFailure, match="RESTORED_"):
            f11_release.compare_restored(before, recovered, source, destination)
        if difference != "semantics":
            assert calls == []
    else:
        assert f11_release.compare_restored(before, recovered, source, destination) == {
            "indexes": ["uq_f11_provider_name_scope", "uq_f8_local_kind"], "triggers": [],
        }
        assert calls == [source, destination, source, destination]


@pytest.mark.parametrize("defect", [None, "unique", "expression", "predicate"])
def test_f11_provider_index_requires_shape_null_semantics_and_entire_kind_domain(defect):
    from types import SimpleNamespace

    from tools import f11_release

    shape = [True, False, True, True, True, "8 0 10 11", "1 1 1 1", "0 0 0 0",
             "0 0 0 0", 4, 4, "btree", "integration_configs", "lower((name)::text)",
             False, "synthetic_catalog_predicate"]
    if defect == "unique":
        shape[0] = False
    if defect == "expression":
        shape[13] = "name"
    kinds = []

    def execute(_query, parameters=None):
        if parameters is None:
            return SimpleNamespace(fetchone=lambda: tuple(shape))
        kinds.append(parameters[0])
        truth = parameters[0] in {"sso", "devops", "outgoing_webhook"}
        return SimpleNamespace(fetchone=lambda: (not truth if defect == "predicate" else truth,))

    connection = SimpleNamespace(execute=execute)
    if defect:
        with pytest.raises(f11_release.ReleaseFailure, match="F11_PROVIDER_INDEX_"):
            f11_release.provider_index_signature(connection)
    else:
        assert f11_release.provider_index_signature(connection) == (
            tuple(shape[:-1]), (False, False, False, True, True, True),
        )
        assert kinds == ["local_storage", "clamav", "object_storage", "sso", "devops",
                         "outgoing_webhook"]


@pytest.mark.parametrize("failure", [None, "inputs", "preflight", "api", "expiry", "child"])
def test_f11_recovery_wrapper_revokes_on_every_exit(monkeypatch, tmp_path, failure):
    from tools import f11_recovery

    calls = []
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setattr(f11_local, "revoke", lambda: calls.append("revoked"))
    monkeypatch.setattr(f11_recovery, "verify_evidence", lambda _path: None)
    monkeypatch.setattr(f11_recovery, "verify_tools", lambda *_args: None)
    monkeypatch.setattr(f11_local, "authorization", lambda: {
        "password": "synthetic", "expires_at": time.time() + (10 if failure == "expiry" else 3600),
    })

    def preflight(**_kwargs):
        if failure == "preflight":
            raise CommandError(503, "SYNTHETIC_PREFLIGHT")

    def child(arguments, _payload, _output):
        calls.append("recovery")
        assert arguments[:2] == ["-m", "tools.f11_recovery"]
        assert "final-gates" not in arguments and "tools.f11_release" not in arguments
        return 1 if failure == "child" else 0

    monkeypatch.setattr(f11_local, "preflight", preflight)
    monkeypatch.setattr(f11_local, "api_listeners", lambda: [("127.0.0.1", 1)]
                        if failure == "api" else [])
    monkeypatch.setattr(f11_local, "private_directory", lambda _path: None)
    monkeypatch.setattr(f11_local, "run_authorized", child)
    arguments = (None if failure == "inputs" else tmp_path / "new", tmp_path / "old", "hash")
    if failure in {"inputs", "preflight", "api", "expiry"}:
        with pytest.raises(CommandError):
            f11_local.run_recovery(*arguments)
        assert calls == ["revoked"]
    else:
        assert f11_local.run_recovery(*arguments) == int(failure == "child")
        assert calls == ["recovery", "revoked"]


def test_f11_recovery_evidence_and_tool_delta_are_pinned(monkeypatch, tmp_path):
    import hashlib

    from tools import f11_recovery as recovery

    source = tmp_path / ("f11-" + str(recovery.ATTEMPT))
    source.mkdir()
    old = {name: "old" for name in sorted(recovery.TOOLS) if not name.endswith("f11_recovery.py")}
    old["backend/alembic/versions/20261126_0010_integrations.py"] = "immutable"
    manifest = {"files": old, "source_revision": recovery.release.SOURCE,
                "target_revision": recovery.release.HEAD}
    path = source / "artifact-manifest.json"
    path.write_text(json.dumps(manifest), encoding="ascii")
    monkeypatch.setattr(recovery, "EVIDENCE", {path.name: recovery.local.digest(path)})
    recovery.verify_evidence(source)
    current = {**old, **dict.fromkeys(recovery.TOOLS, "new")}
    monkeypatch.setattr(recovery.release, "artifact_files", lambda: current)
    approved = hashlib.sha256(recovery.local.canonical({
        name: current[name] for name in sorted(recovery.TOOLS)
    })).hexdigest()
    assert recovery.verify_tools(source, approved) == current
    with pytest.raises(recovery.release.ReleaseFailure, match="APPROVAL_HASH"):
        recovery.verify_tools(source, "wrong")
    current["backend/alembic/versions/20261126_0010_integrations.py"] = "changed"
    with pytest.raises(recovery.release.ReleaseFailure, match="UNAPPROVED_ARTIFACT_DELTA"):
        recovery.verify_tools(source, approved)
    path.write_text("changed", encoding="ascii")
    with pytest.raises(recovery.release.ReleaseFailure, match="EVIDENCE_HASH"):
        recovery.verify_evidence(source)
    (source / "unexpected").touch()
    with pytest.raises(recovery.release.ReleaseFailure, match="EVIDENCE_SET"):
        recovery.verify_evidence(source)


@pytest.fixture
def f11_recovery_state(tmp_path):
    import copy
    import hashlib

    from tools import f11_recovery as recovery

    source = tmp_path / ("f11-" + str(recovery.ATTEMPT))
    source.mkdir()
    manifest = {"files": {"synthetic": "hash"}}
    (source / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="ascii")
    tables = ["alembic_version", "release_history", "deployment_instances"] + [
        "historical_" + str(index) for index in range(55)
    ]
    rows = {name: [] for name in tables}
    rows["alembic_version"] = [json.dumps({"version_num": recovery.release.SOURCE})]
    rows["release_history"] = [json.dumps({"id": "historical-" + str(index),
                                        "status": "succeeded" if index < 9 else "failed"})
                               for index in range(10)]
    before = {"tables": tables, "rows": rows, "indexes": []}
    baseline = copy.deepcopy(before)
    baseline["tables"] += sorted(recovery.release.ADDED)
    baseline["rows"].update({name: [] for name in recovery.release.ADDED})
    baseline["rows"]["alembic_version"] = [json.dumps({"version_num": recovery.release.HEAD})]
    own = {
        "id": str(recovery.ATTEMPT), "request_id": str(recovery.REQUEST),
        "source_revision": recovery.release.SOURCE, "target_revision": recovery.release.HEAD,
        "application_version": "0.11.0", "deployment_mode": "local", "phase": "validation",
        "status": "running", "version": 1, "result_code": None, "finished_at": None,
        "artifact_sha256": hashlib.sha256(recovery.local.canonical(manifest["files"])).hexdigest(),
        "manifest_sha256": recovery.EVIDENCE["artifact-manifest.json"],
        "backup_manifest_sha256": recovery.EVIDENCE["before-manifest.json"],
        "updated_at": "synthetic-original-time",
    }
    baseline["rows"]["release_history"].append(json.dumps(own))
    return source, before, baseline, own


@pytest.mark.parametrize("defect", [None, "head", "seed", "attempt", "status", "version"])
def test_f11_recovery_requires_exact_running_origin(f11_recovery_state, defect):
    from tools import f11_recovery as recovery

    source, _before, baseline, own = f11_recovery_state
    if defect == "head":
        baseline["rows"]["alembic_version"] = [json.dumps({"version_num": recovery.release.SOURCE})]
    elif defect == "seed":
        baseline["rows"]["api_keys"].append("synthetic-unsolicited")
    elif defect:
        key = {"attempt": "id", "status": "status", "version": "version"}[defect]
        own[key] = {"attempt": "other", "status": "succeeded", "version": 2}[defect]
        baseline["rows"]["release_history"][-1] = json.dumps(own)
    if defect:
        with pytest.raises(recovery.release.ReleaseFailure):
            recovery.state(baseline, source)
    else:
        recovery.state(baseline, source)


@pytest.mark.parametrize("failure", [None, "recorded", "terminal", "writers", "uuid", "root",
                                     "expiry_before_cas", "catalog_before_cas",
                                     "security_before_cas", "security_after_cas"])
def test_f11_recovery_order_and_maintenance_on_failure(
    monkeypatch, tmp_path, f11_recovery_state, failure,
):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from uuid import uuid4

    from tools import f11_recovery as recovery

    source, before, baseline, _own = f11_recovery_state
    calls = []
    marker = tmp_path / "maintenance.json"
    marker.write_text(json.dumps({"attempt": str(recovery.ATTEMPT), "phase": "F11"}))
    seal = tmp_path / "master.dpapi"
    seal.write_bytes(b"synthetic-root")
    for name in ("before.dump", "recorded.dump"):
        (source / name).write_bytes(b"synthetic-dump")
    hashes = {**recovery.EVIDENCE, "master.dpapi": recovery.local.digest(seal)}
    monkeypatch.setattr(recovery, "EVIDENCE", hashes)
    monkeypatch.setattr(recovery.local, "MARKER", marker)
    monkeypatch.setattr(recovery.local, "protect", lambda _path: None)
    monkeypatch.setattr(recovery, "seal_path", lambda _instance: seal)
    monkeypatch.setattr(recovery, "verify_evidence", lambda _source: None)
    monkeypatch.setattr(recovery, "verify_tools", lambda *_args: {"synthetic": "hash"})
    monkeypatch.setattr(recovery.local, "verify_identity", lambda _admin: None)
    catalog_reads = []

    def catalog(_admin):
        catalog_reads.append(True)
        return [(1, "changed" if failure == "catalog_before_cas" and len(catalog_reads) > 1
                 else "origin")]

    monkeypatch.setattr(recovery.local, "catalog", catalog)
    monkeypatch.setattr(recovery.local, "legacy_catalog", lambda _admin: [])
    security_reads = []

    def security_catalog(_admin):
        security_reads.append(True)
        changed = ((failure == "security_before_cas" and len(security_reads) > 1) or
                   (failure == "security_after_cas" and len(security_reads) > 2))
        return {"grants": ["unexpected"] if changed else []}

    monkeypatch.setattr(recovery.release, "security_catalog", security_catalog)
    monkeypatch.setattr(recovery.previous, "snapshot", lambda _admin: baseline)
    authorization_reads = []

    def authorization():
        authorization_reads.append(True)
        remaining = (100 if failure == "expiry_before_cas" and len(authorization_reads) > 1
                     else 3600)
        return {"password": "synthetic", "expires_at": time.time() + remaining}

    monkeypatch.setattr(recovery.operator, "authorization", authorization)
    monkeypatch.setenv("PGPASSWORD", "synthetic")
    monkeypatch.setattr(recovery.operator, "api_listeners", lambda: [])

    def execute(query, _parameters=None):
        if "advisory" in query:
            return SimpleNamespace(fetchone=lambda: (True,))
        if "FROM deployment_instances" in query:
            return SimpleNamespace(fetchall=lambda: [(uuid4(),)])
        value = int((failure == "writers" and "pg_stat_activity" in query) or
                    (failure == "uuid" and "pg_database WHERE" in query))
        return SimpleNamespace(fetchone=lambda: (value,))

    admin = SimpleNamespace(execute=execute)
    monkeypatch.setattr(recovery.local, "admin_connection", lambda: nullcontext(admin))

    def restored_before(_directory, _seal):
        calls.append("before")
        return before

    def restored(_directory, label, expected, **kwargs):
        calls.append(label)
        assert expected is baseline and "upgrade" not in kwargs
        if failure == label:
            raise recovery.release.ReleaseFailure("SYNTHETIC_RESTORE_FAILED")

    def terminal(_admin, _directory, expected, _seal):
        assert expected is baseline
        assert marker.exists()
        calls.extend(["CAS", "terminal"])
        if failure == "terminal":
            raise recovery.release.ReleaseFailure("SYNTHETIC_TERMINAL_FAILED")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Recovery must not run Alembic or stop/start an API")

    monkeypatch.setattr(recovery, "restore_before", restored_before)
    monkeypatch.setattr(recovery.release, "restored", restored)
    monkeypatch.setattr(recovery, "terminal", terminal)
    monkeypatch.setattr(recovery.previous, "upgrade", forbidden)
    monkeypatch.setattr(recovery.operator, "drain_api", forbidden)
    if failure == "root":
        seal.write_bytes(b"different-root")
    root = tmp_path / "recovery"
    if failure:
        with pytest.raises(recovery.release.ReleaseFailure):
            recovery.recover(source, root, "approved")
        assert marker.exists()
        if failure in {"writers", "uuid", "root"}:
            assert calls == []
        if failure in {"recorded", "expiry_before_cas", "catalog_before_cas",
                       "security_before_cas"}:
            assert calls == ["before", "recorded"]
        if failure == "security_after_cas":
            assert calls == ["before", "recorded", "CAS", "terminal"]
    else:
        directory = recovery.recover(source, root, "approved")
        assert calls == ["before", "recorded", "CAS", "terminal"]
        assert not marker.exists()
        assert (directory / "recorded-manifest.json").exists()


@pytest.mark.parametrize("failure", [None, "cas", "backup", "historical"])
def test_f11_recovery_terminal_cas_and_backup_preserve_previous_ledger(
    monkeypatch, tmp_path, f11_recovery_state, failure,
):
    import copy
    from types import SimpleNamespace

    from tools import f11_recovery as recovery

    _source, _before, baseline, own = f11_recovery_state
    final = copy.deepcopy(baseline)
    own.update(version=2, status="succeeded", phase="complete", result_code="F11_LOCAL_VERIFIED",
               finished_at="synthetic-time", updated_at="synthetic-time")
    final["rows"]["release_history"][-1] = json.dumps(own)
    if failure == "historical":
        final["rows"]["release_history"][0] = json.dumps({"id": "rewritten", "status": "succeeded"})
    calls = []

    def execute(query, parameters):
        calls.append("CAS")
        assert "version=1" in query and "phase='validation'" in query
        assert recovery.ATTEMPT in parameters and recovery.REQUEST in parameters
        return SimpleNamespace(rowcount=0 if failure == "cas" else 1)

    from contextlib import nullcontext

    monkeypatch.setattr(recovery.local, "role_connection", lambda _url: nullcontext(
        SimpleNamespace(execute=execute)
    ))
    monkeypatch.setattr(recovery.previous, "snapshot", lambda _admin: final)
    monkeypatch.setattr(recovery.local, "journal", lambda *_args, **_kwargs: None)

    def backup(_admin, _directory, label, **_kwargs):
        calls.append(label)
        if failure == "backup":
            raise recovery.release.ReleaseFailure("SYNTHETIC_TERMINAL_BACKUP_FAILURE")

    monkeypatch.setattr(recovery.release, "backup", backup)
    if failure:
        with pytest.raises(RuntimeError):
            recovery.terminal(object(), tmp_path, baseline, tmp_path / "root.dpapi")
    else:
        recovery.terminal(object(), tmp_path, baseline, tmp_path / "root.dpapi")
    assert calls == (["CAS"] if failure == "cas" else ["CAS", "terminal"])


@pytest.fixture
def f11_schema_comparison(monkeypatch):
    import copy
    from types import SimpleNamespace

    from tools import f11_release as release

    provider_array = (
        "(ARRAY['sso'::character varying, 'devops'::character varying, "
        "'outgoing_webhook'::character varying])::text[]"
    )
    local_array = "(ARRAY['local_storage'::character varying, 'clamav'::character varying])::text[]"
    before = {
        "indexes": [
            ("uq_f8_local_kind", "CREATE UNIQUE INDEX uq_f8_local_kind ON "
             "public.integration_configs USING btree (kind) WHERE ((kind)::text = ANY (" +
             local_array + "))"),
            ("uq_f11_provider_name_scope", "CREATE UNIQUE INDEX uq_f11_provider_name_scope ON "
             "public.integration_configs USING btree (provider, lower((name)::text), scope_kind, "
             "department_id) NULLS NOT DISTINCT WHERE ((kind)::text = ANY (" +
             provider_array + "))"),
        ],
        "triggers": [
            ("integration_configs", "CREATE TRIGGER guard_f11_integration BEFORE INSERT OR UPDATE "
             "ON public.integration_configs FOR EACH ROW WHEN (((new.kind)::text = ANY (" +
             provider_array + "))) EXECUTE FUNCTION guard_f11_integration()"),
            ("integration_configs", "CREATE CONSTRAINT TRIGGER audit_f11_integration AFTER INSERT "
             "OR UPDATE ON public.integration_configs DEFERRABLE INITIALLY DEFERRED "
             "FOR EACH ROW WHEN (((new.kind)::text = ANY (" + provider_array +
             "))) EXECUTE FUNCTION audit_f8_record()"),
        ],
        "rows": {},
        "functions": [],
    }
    recovered = {
        section: [(name, definition.replace(
            provider_array, "'{sso,devops,outgoing_webhook}'::text[]")
                   .replace(local_array, "'{local_storage,clamav}'::text[]"))
                  for name, definition in entries]
        for section, entries in before.items() if section in {"indexes", "triggers"}
    }
    recovered.update(rows={}, functions=[])
    metadata = {
        name: {
            "table_schema": "public", "table": "integration_configs", "type": properties[1],
            "enabled": "O", "deferrable": properties[2], "deferred": properties[2], "columns": "",
            "argument_count": 0, "arguments": "", "old_table": None, "new_table": None,
            "parent": False, "constraint": properties[2], "constraint_index": False,
            "function_schema": "public", "function_name": properties[3],
            "kind_type": "character varying(20)", "function_definition": "unchanged-function",
            "function_owner": "ocote_migrador", "security_definer": False,
            "function_config": ["search_path=pg_catalog, public"], "kind_collation": "default",
        }
        for name, properties in release.TRIGGER_GUARDS.items()
    }

    def database():
        connection = SimpleNamespace(
            trigger_rows=copy.deepcopy(metadata),
            index_row=(True, False, True, False, False, None, 0, None),
        )

        def execute(query, parameters):
            if "jsonb_build_object" in query:
                assert parameters[0] in release.TRIGGER_GUARDS
                return SimpleNamespace(fetchone=lambda: (connection.trigger_rows[parameters[0]],))
            assert parameters[0] in release.INDEX_KINDS
            return SimpleNamespace(fetchone=lambda: connection.index_row)

        connection.execute = execute
        return connection

    monkeypatch.setattr(release, "index_signature", lambda _connection: ("f8-signature",))
    monkeypatch.setattr(release, "provider_index_signature", lambda _connection: ("f11-signature",))
    return before, recovered, database(), database()


@pytest.mark.parametrize("form", ["varchar_array", "text_array", "text_literal", "element_casts"])
def test_f11_schema_canonicalization_accepts_only_known_constant_casts(f11_schema_comparison, form):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    if form == "varchar_array":
        recovered = before
    elif form in {"text_array", "element_casts"}:
        for section in ("indexes", "triggers"):
            recovered[section] = [
                (name, definition.replace(
                    "'{sso,devops,outgoing_webhook}'::text[]",
                    "ARRAY['sso'::text, 'devops'::text, 'outgoing_webhook'::text]"
                    if form == "text_array" else
                    "ARRAY[('sso'::character varying)::text, ('devops'::character varying)::text, "
                    "('outgoing_webhook'::character varying)::text]",
                ).replace("'{local_storage,clamav}'::text[]",
                          "ARRAY['local_storage'::text, 'clamav'::text]"
                          if form == "text_array" else
                          "ARRAY[('local_storage'::character varying)::text, "
                          "('clamav'::character varying)::text]"))
                for name, definition in recovered[section]
            ]
    result = release.compare_restored(before, recovered, source, destination)
    if form == "varchar_array":
        assert result == {"indexes": [], "triggers": []}
    else:
        assert result == {
            "indexes": ["uq_f11_provider_name_scope", "uq_f8_local_kind"],
            "triggers": ["audit_f11_integration", "guard_f11_integration"],
        }


@pytest.mark.parametrize("section,position,old,new", [
    ("indexes", 1, "lower", "upper"),
    ("indexes", 1, "NULLS NOT DISTINCT", "NULLS DISTINCT"),
    ("indexes", 1, "sso,devops", "sso,github"),
    ("indexes", 0, "= ANY", "<> ALL"),
    ("triggers", 0, "BEFORE INSERT", "AFTER INSERT"),
    ("triggers", 0, "new.kind", "old.kind"),
    ("triggers", 0, "= ANY", "<> ALL"),
    ("triggers", 0, "FUNCTION guard_f11_integration()", "FUNCTION other_guard()"),
    ("triggers", 1, "INITIALLY DEFERRED", "INITIALLY IMMEDIATE"),
    ("triggers", 1, "FOR EACH ROW", "FOR EACH STATEMENT"),
    ("triggers", 1, "outgoing_webhook}", "object_storage}"),
])
def test_f11_canonicalization_never_masks_real_definition_changes(
    f11_schema_comparison, section, position, old, new,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    name, definition = recovered[section][position]
    assert old in definition
    recovered[section][position] = (name, definition.replace(old, new))
    with pytest.raises(release.ReleaseFailure, match="RESTORED_"):
        release.compare_restored(before, recovered, source, destination)


@pytest.mark.parametrize("field,value", [
    ("enabled", "D"), ("type", 21), ("deferrable", True), ("deferred", True),
    ("columns", "5"), ("argument_count", 1), ("arguments", "00"),
    ("old_table", "old_rows"), ("new_table", "new_rows"), ("parent", True),
    ("constraint", True), ("constraint_index", True),
    ("function_schema", "other_schema"), ("function_name", "other_guard"),
    ("kind_type", "text"), ("function_definition", "changed-function"),
    ("function_owner", "postgres"), ("security_definer", True),
    ("function_config", ["search_path=untrusted"]), ("kind_collation", "other-collation"),
])
def test_f11_trigger_catalog_is_checked_even_when_snapshot_text_matches(
    f11_schema_comparison, field, value,
):
    from tools import f11_release as release

    before, _recovered, source, destination = f11_schema_comparison
    destination.trigger_rows["guard_f11_integration"][field] = value
    with pytest.raises(release.ReleaseFailure, match="RESTORED_TRIGGER_CATALOG_"):
        release.compare_restored(before, before, source, destination)


@pytest.mark.parametrize("catalog", [None, (False, False, True, False, False, None, 0, None)])
def test_f11_index_catalog_cannot_be_missing_or_changed(f11_schema_comparison, catalog):
    from tools import f11_release as release

    before, _recovered, source, destination = f11_schema_comparison
    destination.index_row = catalog
    with pytest.raises(release.ReleaseFailure, match="RESTORED_INDEX_CATALOG_"):
        release.compare_restored(before, before, source, destination)


def test_f11_unknown_trigger_cannot_use_the_known_array_equivalence(f11_schema_comparison):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    for snapshot in (before, recovered):
        table, definition = snapshot["triggers"][0]
        snapshot["triggers"][0] = (
            table, definition.replace("guard_f11_integration", "unknown_guard"),
        )
    with pytest.raises(release.ReleaseFailure, match="RESTORED_TRIGGER_DEFINITION_DIFFERS"):
        release.compare_restored(before, recovered, source, destination)
    diagnostic = release.snapshot_difference(before, recovered)
    assert "unrecognized_trigger" in diagnostic["triggers"]
    assert len(diagnostic["trigger_definition_hashes"]["source"]) == 2


@pytest.mark.parametrize("section,position,old,new", [
    ("indexes", 1, "lower", "upper"),
    ("triggers", 0, "BEFORE INSERT", "AFTER INSERT"),
])
def test_f11_definition_failure_journals_both_catalog_ddls_without_rows(
    f11_schema_comparison, monkeypatch, tmp_path, section, position, old, new,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    before["rows"] = recovered["rows"] = {"users": ["private-row-secret"]}
    name, definition = recovered[section][position]
    recovered[section][position] = (name, definition.replace(old, new))
    events = []
    monkeypatch.setattr(release.local, "journal", lambda _path, event, **data:
                        events.append({"event": event, **data}))
    with pytest.raises(release.ReleaseFailure):
        with release.verification(tmp_path, "recorded", "snapshot_compare"):
            release.compare_restored(before, recovered, source, destination)
    diagnostic = events[-1]["diagnostic"]
    if section == "triggers":
        diagnostic = next(entry for entry in diagnostic["trigger_definitions"]
                          if entry["trigger"] == "guard_f11_integration")
    assert diagnostic["source_def"] == before[section][position][1]
    assert diagnostic["restored_def"] == recovered[section][position][1]
    assert "private-row-secret" not in json.dumps(events)


def test_f11_catalog_ddl_redacts_unknown_literals_and_preserves_known_array_delta():
    from tools import f11_release as release

    definition = "CREATE INDEX synthetic ON public.integration_configs (lower('secret''value'))"
    assert "secret" not in release.catalog_ddl(definition)
    assert "'[REDACTED]'" in release.catalog_ddl(definition)
    assert release.catalog_ddl(r"E'secret\'value'") == "'[REDACTED]'"
    assert release.catalog_ddl(None) is None
    for array in ("'{sso,devops,outgoing_webhook}'::text[]",
                  "ARRAY['sso'::text, 'devops'::text, 'outgoing_webhook'::text]"):
        assert release.catalog_ddl(array) == array


@pytest.mark.parametrize("old,new", [
    (None, None),
    ("CREATE UNIQUE INDEX", "CREATE INDEX"),
    ("lower((name)::text)", "upper((name)::text)"),
    ("lower((name)::text)", "coalesce((name)::text, '')"),
    ("provider, lower", "scope_kind, lower"),
    ("scope_kind, department_id", "department_id, scope_kind"),
    ("NULLS NOT DISTINCT", "NULLS DISTINCT"),
    ("= ANY", "<> ALL"),
    ("(kind)::text", "(scope_kind)::text"),
    ("'sso'::character varying", "'object_storage'::character varying"),
    ("::character varying)::text", "::character varying)::name"),
    ("WHERE (", "WHERE (true OR "),
])
def test_f11_observed_provider_ddl_allows_only_proven_element_casts(
    f11_schema_comparison, old, new,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    name, definition = recovered["indexes"][1]
    element_array = (
        "ARRAY[('sso'::character varying)::text, ('devops'::character varying)::text, "
        "('outgoing_webhook'::character varying)::text]"
    )
    definition = definition.replace("'{sso,devops,outgoing_webhook}'::text[]", element_array)
    if old is not None:
        assert old in definition
        recovered["indexes"][1] = (name, definition.replace(old, new))
        with pytest.raises(release.ReleaseFailure, match="RESTORED_INDEX_DEFINITION_DIFFERS"):
            release.compare_restored(before, recovered, source, destination)
        return
    recovered["indexes"][1] = (name, definition)
    assert release.canonical_kind_predicate(definition, release.PROVIDER_KINDS) == definition
    assert release.compare_restored(before, recovered, source, destination)["indexes"] == [
        "uq_f11_provider_name_scope", "uq_f8_local_kind",
    ]


@pytest.mark.parametrize("position,value", [
    (0, False), (1, True), (2, False), (3, True), (4, True),
    (5, ["fillfactor=75"]), (6, 12345), (7, "upper((name)::text)"),
])
def test_f11_element_cast_equivalence_does_not_skip_index_catalog(
    f11_schema_comparison, position, value,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    before["indexes"] = before["indexes"][1:]
    name, definition = recovered["indexes"][1]
    recovered["indexes"] = [(name, definition.replace(
        "'{sso,devops,outgoing_webhook}'::text[]",
        "ARRAY[('sso'::character varying)::text, ('devops'::character varying)::text, "
        "('outgoing_webhook'::character varying)::text]",
    ))]
    catalog = list(destination.index_row)
    catalog[position] = value
    destination.index_row = tuple(catalog)
    with pytest.raises(release.ReleaseFailure, match="RESTORED_INDEX_CATALOG_DIFFERS") as failure:
        release.compare_restored(before, recovered, source, destination)
    assert failure.value.details["index"] == "uq_f11_provider_name_scope"
    assert failure.value.details["source_def"].startswith("CREATE UNIQUE INDEX")
    assert failure.value.details["restored_def"].startswith("CREATE UNIQUE INDEX")


def test_f11_trigger_catalog_failure_includes_sanitized_ddl_pair(f11_schema_comparison):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    destination.trigger_rows["guard_f11_integration"]["enabled"] = "D"
    with pytest.raises(release.ReleaseFailure, match="RESTORED_TRIGGER_CATALOG_INVALID") as failure:
        release.compare_restored(before, recovered, source, destination)
    assert failure.value.details["source_def"].startswith("CREATE TRIGGER guard_f11_integration ")
    assert failure.value.details["restored_def"].startswith("CREATE TRIGGER guard_f11_integration ")


@pytest.mark.parametrize("position,value", [
    (0, False), (1, True), (2, False), (3, False), (4, False),
    (9, 3), (10, 3), (11, "hash"), (12, "other_table"),
    (13, "upper((name)::text)"), (14, True),
])
def test_f11_provider_catalog_shape_remains_strict(position, value):
    from types import SimpleNamespace

    from tools import f11_release as release

    shape = [True, False, True, True, True, "11 0 13 14", "3126 3126 3126 10065",
             "100 100 100 0", "0 0 0 0", 4, 4, "btree", "integration_configs",
             "lower((name)::text)", False, "unchanged-predicate"]
    shape[position] = value
    connection = SimpleNamespace(execute=lambda _query: SimpleNamespace(
        fetchone=lambda: tuple(shape),
    ))
    with pytest.raises(release.ReleaseFailure, match="F11_PROVIDER_INDEX_SHAPE_INVALID"):
        release.provider_index_signature(connection)


@pytest.mark.parametrize("field", ["key_order", "opclass", "collation", "sort_options"])
def test_f11_provider_signature_differences_are_never_normalized_away(
    f11_schema_comparison, monkeypatch, field,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    monkeypatch.setattr(release, "provider_index_signature", lambda connection:
                        ("same-signature", field if connection is destination else "original"))
    with pytest.raises(release.ReleaseFailure, match="RESTORED_INDEX_SEMANTICS_DIFFER") as failure:
        release.compare_restored(before, recovered, source, destination)
    assert failure.value.details["index"] == "uq_f11_provider_name_scope"


@pytest.mark.parametrize("section", [
    "relations", "routines", "relation_grants", "column_grants", "routine_grants",
    "schema_grants", "default_grants", "views", "policies", "sequences",
])
def test_f11_full_security_catalog_cannot_change(monkeypatch, section):
    from tools import f11_release as release

    source, destination = object(), object()
    original = {name: [] for name in (
        "relations", "routines", "relation_grants", "column_grants", "routine_grants",
        "schema_grants", "default_grants", "views", "policies", "sequences",
    )}
    monkeypatch.setattr(release, "security_catalog", lambda connection:
                        original if connection is source else {**original, section: ["changed"]})
    with pytest.raises(
        release.ReleaseFailure, match="RESTORED_SECURITY_CATALOG_DIFFERS",
    ) as failure:
        release.compare_security_catalog(source, destination)
    assert failure.value.details["sections"] == [section]
    assert "changed" not in json.dumps(failure.value.details)
    monkeypatch.setattr(release, "security_catalog", lambda _connection: original)
    release.compare_security_catalog(source, destination)


def test_f11_security_catalog_reads_metadata_only():
    from types import SimpleNamespace

    from tools import f11_release as release

    queries = []

    def execute(query):
        assert query.startswith("SELECT ")
        assert "row_to_json" not in query and "prosrc" not in query
        queries.append(query)
        return SimpleNamespace(fetchall=lambda: [])

    catalog = release.security_catalog(SimpleNamespace(execute=execute))
    assert len(queries) == len(catalog) == 10
    assert "views" in catalog and "column_grants" in catalog and "routine_grants" in catalog


@pytest.mark.parametrize("section,position,old,new", [
    ("indexes", 0, "(kind) WHERE", "(provider) WHERE"),
    ("indexes", 0, "ARRAY[('local_storage'", "ARRAY[('sso'"),
    ("indexes", 0, "::character varying)::text", "::character varying)::name"),
    ("indexes", 1, "NULLS NOT DISTINCT", "NULLS DISTINCT"),
    ("triggers", 0, "new.kind", "old.kind"),
    ("triggers", 0, "BEFORE INSERT", "AFTER INSERT"),
    ("triggers", 0, "FUNCTION guard_f11_integration()", "FUNCTION other_guard()"),
    ("triggers", 1, "INITIALLY DEFERRED", "INITIALLY IMMEDIATE"),
    ("triggers", 1, "::character varying)::text", "::character varying)::name"),
])
def test_f11_real_element_cast_forms_never_hide_structural_changes(
    f11_schema_comparison, section, position, old, new,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    for key in ("indexes", "triggers"):
        entries = []
        for name, definition in recovered[key]:
            for kinds in release.INDEX_KINDS.values():
                definition = definition.replace(
                    "'{" + ",".join(kinds) + "}'::text[]",
                    "ARRAY[" + ", ".join("('" + kind + "'::character varying)::text"
                                         for kind in kinds) + "]",
                )
            entries.append((name, definition))
        recovered[key] = entries
    name, definition = recovered[section][position]
    assert old in definition
    recovered[section][position] = (name, definition.replace(old, new))
    with pytest.raises(release.ReleaseFailure, match="RESTORED_"):
        release.compare_restored(before, recovered, source, destination)


@pytest.mark.parametrize("structured", [False, True])
def test_f11_index_guard_failures_always_keep_the_sanitized_ddl_pair(
    f11_schema_comparison, monkeypatch, structured,
):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison

    def signature(_connection):
        if structured:
            raise release.ReleaseFailure("F11_PROVIDER_INDEX_SHAPE_INVALID")
        raise RuntimeError("sensitive-diagnostic-not-for-evidence")

    monkeypatch.setattr(release, "provider_index_signature", signature)
    with pytest.raises(release.ReleaseFailure) as failure:
        release.compare_restored(before, recovered, source, destination)
    assert failure.value.details["index"] == "uq_f11_provider_name_scope"
    assert failure.value.details["source_def"].startswith("CREATE UNIQUE INDEX")
    assert failure.value.details["restored_def"].startswith("CREATE UNIQUE INDEX")
    assert "sensitive-diagnostic" not in json.dumps(failure.value.details)


@pytest.mark.parametrize("section", ["columns", "constraints", "functions", "tables", "rows"])
def test_f11_other_snapshot_sections_remain_strict(f11_schema_comparison, section):
    from tools import f11_release as release

    before, recovered, source, destination = f11_schema_comparison
    before[section] = []
    recovered[section] = ["private-value-not-for-evidence"]
    with pytest.raises(release.ReleaseFailure, match="RESTORED_SNAPSHOT_DIFFERS") as failure:
        release.compare_restored(before, recovered, source, destination)
    assert section in failure.value.details["sections"]
    assert "private-value" not in json.dumps(failure.value.details)