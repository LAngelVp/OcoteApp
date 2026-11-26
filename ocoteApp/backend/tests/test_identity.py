import os
import secrets
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.core.errors import CommandError
from app.core.security import PASSWORDS, AuthSettings, Tokens, check_origin, now, verify_password
from app.schemas.identity import (
    CatalogCreate,
    CatalogUpdate,
    ChangePassword,
    Login,
    PasswordReset,
    ReorderEntry,
    SettingCreate,
    UserCreate,
)
from app.services.administration import validate_graph, validate_workflow


@pytest.fixture
def api(tokens):
    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit OCOTE_RUN_PG_TESTS=1 and local administrative environment required")
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    from test_f8 import policy_values

    from app.core.config import Settings
    from app.main import create_app
    from app.models.identity import User
    from app.schemas.enterprise import MODULES, FlagWrite, PolicyWrite
    from app.services.enterprise import save_flag, save_policy
    from app.services.identity import bootstrap_admin
    from tools.f2_local import isolated_database, migration_engine, upgrade

    with isolated_database() as name:
        upgrade(name)
        migrator = migration_engine(name)
        try:
            with migrator.begin() as connection:
                connection.execute(text("INSERT INTO deployment_instances(id,root_key_ref) "
                                        "VALUES(:id,'synthetic-root')"), {"id": uuid4()})
        finally:
            migrator.dispose()
        engine = create_engine(
            make_url(Settings().database_url.get_secret_value()).set(database=name),
            hide_parameters=True,
            connect_args={"options": "-c lock_timeout=5000"},
        )
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with factory.begin() as db:
                bootstrap_admin(
                    db,
                    email="admin@example.invalid",
                    display_name="Synthetic admin",
                    password="Synthetic-password-123!",
                    request=SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4()))),
                )
                actor = db.scalar(select(User))
                synthetic = {"expected_version": 0, "reason": "Explicit UUID-only F8 fixture",
                             "current_password": "Synthetic-password-123!"}
                request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
                save_policy(db, PolicyWrite(**synthetic, values=policy_values()), request, actor)
                for code in MODULES:
                    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
                    save_flag(db, FlagWrite(**synthetic, code=code, enabled=True), request, actor)
            app = create_app(tokens=tokens)
            app.state.session_factory = factory
            with TestClient(
                app, base_url=tokens.settings.auth_origin, raise_server_exceptions=False
            ) as client:
                client.headers["origin"] = tokens.settings.auth_origin
                yield client, factory
        finally:
            engine.dispose()


def login_admin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.invalid", "password": "Synthetic-password-123!"},
    )
    assert response.status_code == 200, response.text
    return response


def test_real_administration_conflicts_and_no_defaults(api):
    client, _ = api
    response = login_admin(client)
    client.headers["authorization"] = "Bearer " + response.json()["access_token"]
    assert client.get("/api/v1/settings").json() == {"items": []}
    assert client.get("/api/v1/priorities").json()["items"] == []
    assert client.get("/api/v1/configuration-status").json()["complete"] is False
    body = {"code": "fixture", "name": "Synthetic", "reason": "Synthetic configuration"}
    created = client.post("/api/v1/departments", json=body)
    assert created.status_code == 201, created.text
    assert client.post("/api/v1/departments", json=body).status_code == 409
    identity = created.json()["id"]
    update_body = {
        "name": "Synthetic renamed",
        "is_active": True,
        "expected_version": 2,
        "reason": "Synthetic configuration",
    }
    conflict = client.patch("/api/v1/departments/" + identity, json=update_body)
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"
    assert conflict.json()["request_id"] == conflict.headers["x-request-id"]
    update_body["expected_version"] = 1
    assert client.patch("/api/v1/departments/" + identity, json=update_body).json()["version"] == 2
    assert client.get("/api/v1/users/" + str(uuid4())).status_code == 404
    assert (
        client.post(
            "/api/v1/settings",
            json={"key": "export_max_rows", "value": True, "reason": "Synthetic configuration"},
        ).status_code
        == 422
    )


def test_real_login_refresh_reuse_revokes_access(api):
    from sqlalchemy import select

    from app.core.security import COOKIE
    from app.models.identity import AuditEvent, RefreshSession

    client, factory = api
    initial = login_admin(client)
    assert initial.json()["user"]["role"] == "admin"
    assert "password_hash" not in initial.json()["user"]
    old_cookie = client.cookies.get(COOKIE)
    csrf = initial.json()["csrf_token"]
    header = initial.headers["set-cookie"]
    assert all(
        value in header for value in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api/v1/auth")
    )
    assert COOKIE not in initial.json()
    bearer = {"authorization": "Bearer " + initial.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 200
    assert client.get("/api/v1/auth/csrf").json()["csrf_token"] == csrf
    rotated = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["user"] == initial.json()["user"]
    reused = client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf, "Cookie": COOKIE + "=" + old_cookie}
    )
    assert reused.status_code == 401, reused.text
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 401
    with factory() as db:
        sessions = list(db.scalars(select(RefreshSession)))
        assert len(sessions) == 2
        assert all(record.revoked_at is not None for record in sessions)
        assert sessions[0].family_id == sessions[1].family_id
        assert sessions[0].expires_at == sessions[1].expires_at
        assert "refresh_reuse" in list(db.scalars(select(AuditEvent.event_type)))


@pytest.fixture(scope="session")
def tokens(tmp_path_factory):
    directory = tmp_path_factory.mktemp("auth")
    private = directory / "signing.pem"
    secret = directory / "csrf.key"
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    secret.write_bytes(secrets.token_bytes(32))
    return Tokens(
        AuthSettings(
            _env_file=None,
            auth_origin="https://localhost:8443",
            jwt_private_key_file=private,
            csrf_secret_file=secret,
        )
    )


def test_argon2id_and_strict_commands():
    encoded = PASSWORDS.hash("synthetic-password-for-test")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "synthetic-password-for-test")
    assert not verify_password(encoded, "wrong")
    with pytest.raises(ValidationError):
        SettingCreate(key="export_max_rows", value=True, reason="synthetic reason")
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@example.invalid",
            display_name="A",
            password="too-short",
            role="admin",
            reason="synthetic reason",
            token_version=123,
        )


def test_catalog_position_matches_postgresql_integer_range():
    bodies = [
        (
            CatalogCreate,
            {"code": "fixture", "name": "Synthetic", "reason": "Current justification"},
        ),
        (
            CatalogUpdate,
            {
                "name": "Synthetic", "is_active": True, "expected_version": 1,
                "reason": "Current justification",
            },
        ),
        (ReorderEntry, {"id": uuid4(), "expected_version": 1}),
    ]
    for schema, body in bodies:
        for value in (0, 2147483647):
            assert schema(**body, position=value).position == value
        for value in (-1, 2147483648, "1", True, 1.5):
            with pytest.raises(ValidationError):
                schema(**body, position=value)


@pytest.mark.parametrize(
    "command,field,extra,minimum",
    [
        (UserCreate, "password", {
            "email": "exact@example.invalid", "display_name": "Synthetic", "role": "admin",
            "reason": "Explicit user creation",
        }, 12),
        (Login, "password", {"email": "exact@example.invalid"}, 1),
        (PasswordReset, "new_password", {
            "expected_version": 1, "reason": "Explicit password reset",
        }, 12),
        (ChangePassword, "current_password", {"new_password": "Synthetic-new-123!"}, 1),
        (ChangePassword, "new_password", {"current_password": "Synthetic-old-123!"}, 12),
    ],
)
def test_secret_commands_preserve_exact_values_and_lengths(command, field, extra, minimum):
    password = "  Synthetic exact 123!  "
    parsed = command(**{**extra, field: password})
    assert getattr(parsed, field).get_secret_value() == password
    assert password not in repr(parsed)
    for invalid in ("x" * (minimum - 1), "x" * 129, 123, True):
        with pytest.raises(ValidationError):
            command(**{**extra, field: invalid})
    assert len(getattr(command(**{**extra, field: "x" * 128}), field).get_secret_value()) == 128


@pytest.mark.parametrize("code", [None, "WORKFLOW_INCOMPLETE", "WORKFLOW_HAS_NO_TERMINAL_PATH"])
def test_configuration_status_reports_workflow_failure_without_changing_gate(monkeypatch, code):
    from app.routers.administration import configuration_status
    from app.services import administration

    results = iter([administration.SETTING_KEYS, administration.HORIZONS])
    db = SimpleNamespace(scalars=lambda statement: next(results), scalar=lambda statement: uuid4())

    def validate(db):
        if code:
            raise CommandError(409, code)

    monkeypatch.setattr(administration, "validate_workflow", validate)
    status = configuration_status(None, db)
    assert status["workflow_error"] == code
    assert status["workflow_valid"] is (code is None)
    assert status["complete"] is (code is None)
    assert status["missing_settings"] == status["missing_horizons"] == []


def test_workflow_construction_keeps_local_rules_and_requires_completion_for_operation():
    initial = SimpleNamespace(
        id="open", kind="open", is_initial=True, is_active=True,
        requires_evidence=False, requires_reason=False,
    )
    terminal = SimpleNamespace(
        id="done", kind="completed", is_initial=False, is_active=True,
        requires_evidence=False, requires_reason=False,
    )
    edge = SimpleNamespace(
        from_stage_id="open", to_stage_id="done", is_active=True, allowed_roles=["admin"],
    )
    validate_graph([initial], [], allow_incomplete=True)
    with pytest.raises(CommandError, match="WORKFLOW_INCOMPLETE"):
        validate_graph([initial], [])
    validate_graph([initial, terminal], [], allow_incomplete=True)
    with pytest.raises(CommandError, match="WORKFLOW_HAS_NO_TERMINAL_PATH"):
        validate_graph([initial, terminal], [])
    validate_graph([initial, terminal], [edge])
    duplicate = SimpleNamespace(**{**vars(initial), "id": "duplicate"})
    with pytest.raises(CommandError, match="WORKFLOW_INCOMPLETE"):
        validate_graph([initial, duplicate], [], allow_incomplete=True)
    initial.requires_evidence = True
    with pytest.raises(CommandError, match="INVALID_INITIAL_STAGE"):
        validate_graph([initial], [], allow_incomplete=True)
    initial.requires_evidence = False
    edge.allowed_roles = ["gerente"]
    with pytest.raises(CommandError, match="INVALID_TRANSITION_ROLES"):
        validate_graph([initial, terminal], [edge], allow_incomplete=True)


@pytest.mark.parametrize("used_table", ["tasks", "evaluations"])
def test_workflow_construction_cannot_leave_an_incomplete_graph_after_use(monkeypatch, used_table):
    initial = SimpleNamespace(
        id="open", kind="open", is_initial=True, is_active=True,
        requires_evidence=False, requires_reason=False,
    )
    results = iter([[initial], []])
    db = SimpleNamespace(flush=lambda: None, scalars=lambda statement: next(results))
    monkeypatch.setattr(
        "app.services.administration.has_rows", lambda db, table: table == used_table,
    )
    with pytest.raises(CommandError, match="WORKFLOW_INCOMPLETE"):
        validate_workflow(db, allow_incomplete=True)


def test_jwt_claims_algorithm_type_and_csrf(tokens):
    user = SimpleNamespace(id=uuid4(), token_version=1)
    family = uuid4()
    encoded = tokens.access(user, family)
    assert tokens.decode(encoded, "access")["sid"] == str(family)
    with pytest.raises(CommandError):
        tokens.decode(encoded, "refresh")
    forged = jwt.encode({"sub": str(user.id)}, secrets.token_bytes(32), algorithm="HS256")
    with pytest.raises(CommandError):
        tokens.decode(forged, "access")
    expires = now() + timedelta(days=7)
    csrf = tokens.csrf(family, expires)
    tokens.check_csrf(csrf, family, expires)
    with pytest.raises(CommandError):
        tokens.check_csrf(csrf, uuid4(), expires)


def test_origin_is_exact_and_no_http_fallback(tokens):
    allowed = tokens.settings.auth_origin
    check_origin(allowed, None, allowed)
    check_origin(None, allowed + "/profile", allowed)
    for origin in (None, "null", "http://localhost:8443", allowed + ".evil.invalid"):
        with pytest.raises(CommandError):
            check_origin(origin, None, allowed)


def authenticated(client):
    response = login_admin(client)
    client.headers["authorization"] = "Bearer " + response.json()["access_token"]
    return response.json()


def create_person(client, *, role="colaborador", department=None, email="person@example.invalid"):
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "display_name": "Synthetic person",
            "password": "Synthetic-person-123!",
            "role": role,
            "department_id": department,
            "reason": "Synthetic test provisioning",
        },
    )
    assert response.status_code == 201, response.text
    assert "password_hash" not in response.text and "token_version" not in response.text
    return response.json()


def create_department(client, code):
    response = client.post(
        "/api/v1/departments",
        json={"code": code, "name": "Synthetic " + code, "reason": "Synthetic department creation"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def person_client(parent, email="person@example.invalid"):
    from fastapi.testclient import TestClient

    client = TestClient(parent.app, base_url=str(parent.base_url), raise_server_exceptions=False)
    client.headers["origin"] = parent.headers["origin"]
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Synthetic-person-123!"}
    )
    assert response.status_code == 200, response.text
    client.headers["authorization"] = "Bearer " + response.json()["access_token"]
    return client


def test_real_logout_password_origin_and_csrf(api):
    client, factory = api
    response = login_admin(client)
    data = response.json()
    bearer = {"authorization": "Bearer " + data["access_token"]}
    assert client.post("/api/v1/auth/refresh").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/refresh",
            headers={"origin": "https://evil.invalid", "x-csrf-token": data["csrf_token"]},
        ).status_code
        == 403
    )
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 200
    assert (
        client.post("/api/v1/auth/logout", headers={"x-csrf-token": data["csrf_token"]}).status_code
        == 204
    )
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 401
    response = login_admin(client)
    bearer = {"authorization": "Bearer " + response.json()["access_token"]}
    body = {"current_password": "incorrect", "new_password": "Changed-synthetic-123!"}
    assert client.post("/api/v1/auth/change-password", headers=bearer, json=body).status_code == 401
    body["current_password"] = "Synthetic-password-123!"
    assert client.post("/api/v1/auth/change-password", headers=bearer, json=body).status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.invalid", "password": "Synthetic-password-123!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.invalid", "password": body["new_password"]},
        ).status_code
        == 200
    )
    from sqlalchemy import select

    from app.models.identity import AuditEvent

    with factory() as db:
        payload = str(
            [(event.before_data, event.after_data) for event in db.scalars(select(AuditEvent))]
        )
        assert "Synthetic-password" not in payload and "Changed-synthetic" not in payload
        assert "argon2" not in payload and data["access_token"] not in payload


@pytest.mark.parametrize("change", ["role", "department", "state", "password"])
def test_real_admin_security_changes_revoke_sessions(api, change):
    client, _ = api
    authenticated(client)
    first = create_department(client, "first")
    second = create_department(client, "second")
    person = create_person(client, department=first)
    with person_client(client) as member:
        assert member.get("/api/v1/auth/me").status_code == 200
        body = {
            "display_name": "Synthetic person",
            "role": "colaborador",
            "department_id": first,
            "is_active": True,
            "expected_version": 1,
            "reason": "Synthetic security change",
        }
        if change == "password":
            response = client.post(
                "/api/v1/users/" + person["id"] + "/reset-password",
                json={
                    "expected_version": 1,
                    "new_password": "Reset-synthetic-123!",
                    "reason": "Synthetic credential reset",
                },
            )
            assert response.status_code == 204, response.text
        else:
            if change == "role":
                body["role"] = "lider"
            elif change == "department":
                body["department_id"] = second
            else:
                body["is_active"] = False
            response = client.patch("/api/v1/users/" + person["id"], json=body)
            assert response.status_code == 200, response.text
        assert member.get("/api/v1/auth/me").status_code == 401


def test_real_scope_and_negative_statuses(api):
    client, _ = api
    for path in ("/users", "/departments", "/settings", "/catalogs/assignees", "/auth/me"):
        response = client.get("/api/v1" + path)
        assert response.status_code == 401, response.text
        assert response.headers["content-type"] == "application/problem+json"
    authenticated(client)
    first = create_department(client, "own")
    second = create_department(client, "other")
    create_person(client, department=first)
    create_person(client, department=second, email="other@example.invalid")
    create_person(client, role="lider", department=first, email="leader@example.invalid")
    create_person(client, role="gerente", email="manager@example.invalid")
    with person_client(client) as member:
        for path in (
            "/users",
            "/users/" + str(uuid4()),
            "/settings",
            "/audit-events",
            "/release-history",
        ):
            assert member.get("/api/v1" + path).status_code == 403
        departments = member.get("/api/v1/catalogs/departments").json()["items"]
        assert [record["id"] for record in departments] == [first]
        people = member.get("/api/v1/catalogs/assignees").json()["items"]
        assert len(people) == 1 and set(people[0]) == {"id", "display_name", "department_id"}
        assert (
            member.get("/api/v1/catalogs/assignees", params={"department_id": second}).status_code
            == 404
        )
    with person_client(client, "leader@example.invalid") as leader:
        assert all(
            record["department_id"] == first
            for record in leader.get("/api/v1/catalogs/assignees").json()["items"]
        )
    with person_client(client, "manager@example.invalid") as manager:
        assert len(manager.get("/api/v1/catalogs/departments").json()["items"]) == 2
        assert manager.get("/api/v1/users").status_code == 403
    assert (
        client.patch(
            "/api/v1/departments/" + first,
            json={
                "name": "Synthetic",
                "is_active": False,
                "expected_version": 1,
                "reason": "Synthetic deactivation test",
            },
        ).status_code
        == 409
    )


def workflow_body():
    return {
        "stages": [
            {
                "code": "fixture_open",
                "name": "Synthetic open",
                "position": 10,
                "kind": "open",
                "is_initial": True,
                "reason": "Synthetic workflow setup",
            },
            {
                "code": "fixture_done",
                "name": "Synthetic done",
                "position": 20,
                "kind": "completed",
                "reason": "Synthetic workflow setup",
            },
        ],
        "transitions": [
            {
                "from_code": "fixture_open",
                "to_code": "fixture_done",
                "allowed_roles": ["admin", "lider", "colaborador"],
            }
        ],
        "reason": "Synthetic atomic workflow setup",
    }


def test_real_initial_graph_and_dependency_safe_deactivation(api):
    client, _ = api
    authenticated(client)
    stages = []
    for body in workflow_body()["stages"]:
        response = client.post("/api/v1/workflow-stages", json=body)
        assert response.status_code == 201, response.text
        stages.append(response.json())
        assert client.get("/api/v1/configuration-status").json()["workflow_valid"] is False
        assert client.get("/api/v1/workflow-transitions").json()["items"] == []
    initial, terminal = stages
    invalid = {**workflow_body()["stages"][0], "code": "invalid", "position": 30}
    rejected = client.post(
        "/api/v1/workflow-stages", json={**invalid, "requires_evidence": True},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "INVALID_INITIAL_STAGE"
    assert rejected.json()["request_id"] == rejected.headers["x-request-id"]
    assert client.post("/api/v1/workflow-stages", json=invalid).status_code == 409
    assert len(client.get("/api/v1/workflow-stages").json()["items"]) == 2
    edge = client.post(
        "/api/v1/workflow-transitions",
        json={
            "from_stage_id": initial["id"], "to_stage_id": terminal["id"],
            "allowed_roles": ["admin"], "is_active": True,
            "reason": "Explicit separate transition",
        },
    )
    assert edge.status_code == 201, edge.text
    edge_path = "/api/v1/workflow-transitions/" + edge.json()["id"]
    assert client.get("/api/v1/configuration-status").json()["workflow_valid"] is True
    assert len(client.get("/api/v1/catalogs/workflow").json()["stages"]) == 2
    change = {
        "allowed_roles": ["admin"], "is_active": False, "expected_version": 1,
        "reason": "Current transition deactivation",
    }
    assert client.patch(edge_path, json=change).status_code == 200
    assert client.get("/api/v1/configuration-status").json()["workflow_valid"] is False
    assert client.patch(edge_path, json=change).status_code == 409
    assert client.get(edge_path).json()["version"] == 2
    assert client.patch(
        edge_path, json={**change, "is_active": True, "expected_version": 2},
    ).status_code == 200
    assert client.get("/api/v1/configuration-status").json()["workflow_valid"] is True
    department = create_department(client, "dependent")
    person = create_person(client, department=department)
    update = {
        "name": "Synthetic dependent", "is_active": False, "expected_version": 1,
        "reason": "Current dependency change",
    }
    blocked = client.patch("/api/v1/departments/" + department, json=update)
    assert blocked.status_code == 409
    assert blocked.headers["content-type"] == "application/problem+json"
    assert blocked.json()["request_id"] == blocked.headers["x-request-id"]
    assert blocked.json()["code"] == "DEPARTMENT_HAS_ACTIVE_USERS"
    assert client.get("/api/v1/departments/" + department).json()["version"] == 1
    inactive = client.patch(
        "/api/v1/users/" + person["id"],
        json={
            "display_name": person["display_name"], "role": person["role"],
            "department_id": department, "is_active": False, "expected_version": 1,
            "reason": "Current user deactivation",
        },
    )
    assert inactive.status_code == 200, inactive.text
    assert client.patch("/api/v1/departments/" + department, json=update).status_code == 200
    current = client.get("/api/v1/departments/" + department).json()
    assert current["is_active"] is False and current["version"] == 2
    assert client.get("/api/v1/users/" + person["id"]).json()["department_id"] == department
    for path in ("/departments/" + department, "/users/" + person["id"]):
        assert client.delete("/api/v1" + path).status_code == 405
    overflow = client.post(
        "/api/v1/priorities",
        json={"code": "huge", "name": "Synthetic", "position": 2147483648,
              "reason": "Current numeric validation"},
    )
    assert overflow.status_code == 422
    assert overflow.headers["content-type"] == "application/problem+json"
    assert overflow.json()["request_id"] == overflow.headers["x-request-id"]
    events = client.get("/api/v1/audit-events", params={"limit": 50}).json()["items"]
    reasons = {
        event["after_data"].get("reason") for event in events
        if event["entity_id"] == department and event["after_data"]
    }
    assert {"Synthetic department creation", "Current dependency change"} <= reasons


def test_real_user_password_bytes_survive_create_edit_and_reset(api):
    from fastapi.testclient import TestClient

    client, _ = api
    authenticated(client)
    password = "  Synthetic secret 123!  "
    response = client.post(
        "/api/v1/users",
        json={
            "email": "exact@example.invalid", "display_name": "Synthetic exact password",
            "password": password, "role": "gerente", "is_active": True,
            "reason": "Explicit password creation",
        },
    )
    assert response.status_code == 201, response.text
    identity = response.json()["id"]
    with TestClient(client.app, base_url=str(client.base_url)) as peer:
        peer.headers["origin"] = client.headers["origin"]
        credentials = {"email": "exact@example.invalid", "password": password}
        assert peer.post("/api/v1/auth/login", json=credentials).status_code == 200
        updated = client.patch(
            "/api/v1/users/" + identity,
            json={
                "display_name": "Synthetic renamed", "role": "gerente", "is_active": True,
                "department_id": None, "expected_version": 1,
                "reason": "Current ordinary user edit",
            },
        )
        assert updated.status_code == 200, updated.text
        assert peer.post("/api/v1/auth/login", json=credentials).status_code == 200
        new_password = "  New synthetic secret 456!  "
        reset = client.post(
            "/api/v1/users/" + identity + "/reset-password",
            json={
                "new_password": new_password, "expected_version": 2,
                "reason": "Current exact password reset",
            },
        )
        assert reset.status_code == 204, reset.text
        credentials["password"] = new_password
        assert peer.post("/api/v1/auth/login", json=credentials).status_code == 200
        credentials["password"] = new_password.strip()
        assert peer.post("/api/v1/auth/login", json=credentials).status_code == 401
    audit_payload = client.get("/api/v1/audit-events").text
    assert password not in audit_payload and new_password not in audit_payload
    assert "password_hash" not in audit_payload


def test_real_workflow_and_explicit_configuration(api):
    client, _ = api
    authenticated(client)
    body = workflow_body()
    body["transitions"][0]["allowed_roles"] = ["gerente", "admin"]
    assert client.post("/api/v1/workflow", json=body).status_code == 422
    body["transitions"][0]["allowed_roles"] = ["lider"]
    assert client.post("/api/v1/workflow", json=body).status_code == 422
    assert client.get("/api/v1/workflow-stages").json()["items"] == []
    response = client.post("/api/v1/workflow", json=workflow_body())
    assert response.status_code == 201, response.text
    initial = next(stage for stage in response.json()["stages"] if stage["is_initial"])
    assert (
        client.patch(
            "/api/v1/workflow-stages/" + initial["id"],
            json={
                "name": initial["name"],
                "position": 10,
                "is_active": False,
                "requires_evidence": False,
                "requires_reason": False,
                "expected_version": 1,
                "reason": "Synthetic invalid deactivation",
            },
        ).status_code
        == 409
    )
    assert client.get("/api/v1/configuration-status").json()["workflow_valid"] is True
    for key, value in {
        "organization_name": "Synthetic organization",
        "organization_timezone": "America/Mexico_City",
        "evidence_max_bytes": 1000,
        "export_max_rows": 20,
    }.items():
        response = client.post(
            "/api/v1/settings",
            json={"key": key, "value": value, "reason": "Synthetic explicit configuration"},
        )
        assert response.status_code == 201, response.text
    for position, code in enumerate(["annual", "semiannual", "quarterly", "monthly", "custom"]):
        response = client.post(
            "/api/v1/horizon-types",
            json={
                "code": code,
                "name": "Synthetic " + code,
                "position": position,
                "reason": "Synthetic explicit horizon",
            },
        )
        assert response.status_code == 201, response.text
    normal = client.post(
        "/api/v1/priorities",
        json={
            "code": "normal",
            "name": "Synthetic normal",
            "position": 0,
            "reason": "Synthetic explicit priority",
        },
    )
    assert normal.status_code == 201, normal.text
    assert client.get("/api/v1/configuration-status").json()["complete"] is True
    edge = client.get("/api/v1/workflow-transitions").json()["items"][0]
    change = {
        "allowed_roles": edge["allowed_roles"], "is_active": False, "expected_version": 1,
        "reason": "Explicit configuration construction",
    }
    edge_path = "/api/v1/workflow-transitions/" + edge["id"]
    assert client.patch(edge_path, json=change).status_code == 200
    status = client.get("/api/v1/configuration-status").json()
    assert status["complete"] is False and status["workflow_valid"] is False
    assert status["workflow_error"] == "WORKFLOW_HAS_NO_TERMINAL_PATH"
    assert status["missing_settings"] == status["missing_horizons"] == []
    assert status["normal_present"] is True
    plan = {
        "title": "Synthetic gated plan", "horizon_type": "custom",
        "start_date": "2027-01-01", "due_date": "2027-12-31",
    }
    blocked = client.post("/api/v1/annual-plans", json=plan)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "WORKFLOW_HAS_NO_TERMINAL_PATH"
    assert blocked.headers["content-type"] == "application/problem+json"
    assert str(UUID(blocked.json()["request_id"])) == blocked.headers["x-request-id"]
    assert client.get("/api/v1/annual-plans").json()["items"] == []
    assert client.patch(
        edge_path, json={**change, "is_active": True, "expected_version": 2},
    ).status_code == 200
    recovered = client.get("/api/v1/configuration-status").json()
    assert recovered["complete"] is True and recovered["workflow_error"] is None
    assert client.post("/api/v1/annual-plans", json=plan).status_code == 201
    assert (
        client.patch(
            "/api/v1/priorities/" + normal.json()["id"],
            json={
                "name": "Synthetic normal",
                "position": 0,
                "is_active": False,
                "expected_version": 1,
                "reason": "Synthetic protected priority",
            },
        ).status_code
        == 409
    )


def test_real_concurrent_refresh_revokes_winner(api):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.core.security import COOKIE

    client, _ = api
    response = login_admin(client)
    cookie, csrf = client.cookies.get(COOKIE), response.json()["csrf_token"]

    def refresh_once():
        with TestClient(
            client.app, base_url=str(client.base_url), raise_server_exceptions=False
        ) as peer:
            return peer.post(
                "/api/v1/auth/refresh",
                headers={
                    "origin": client.headers["origin"],
                    "cookie": COOKIE + "=" + cookie,
                    "x-csrf-token": csrf,
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda unused: refresh_once(), range(2)))
    assert sorted(result.status_code for result in results) == [200, 401]
    winner = next(result.json()["access_token"] for result in results if result.status_code == 200)
    assert (
        client.get("/api/v1/auth/me", headers={"authorization": "Bearer " + winner}).status_code
        == 401
    )


def test_real_last_admin_concurrency(api):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import func, select

    from app.models.identity import User

    client, factory = api
    authenticated(client)
    own = client.get("/api/v1/auth/me").json()
    second = create_person(client, role="admin", email="second@example.invalid")
    with person_client(client, "second@example.invalid") as peer:

        def demote(pair):
            session, user = pair
            return session.patch(
                "/api/v1/users/" + user["id"],
                json={
                    "display_name": "Synthetic demoted",
                    "role": "gerente",
                    "department_id": None,
                    "is_active": True,
                    "expected_version": 1,
                    "reason": "Synthetic concurrent demotion",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, [(client, own), (peer, second)]))
        assert sorted(result.status_code for result in results) == [200, 409]
    with factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
            )
            == 1
        )


def test_real_bootstrap_cannot_repeat_or_reset(api):
    from sqlalchemy import select

    from app.models.identity import User
    from app.services.identity import bootstrap_admin

    _, factory = api
    with factory.begin() as db:
        original = db.scalar(select(User)).password_hash
    with pytest.raises(CommandError):
        with factory.begin() as db:
            bootstrap_admin(
                db,
                email="replacement@example.invalid",
                display_name="Synthetic",
                password="Never-reset-existing-123!",
                request=SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4()))),
            )
    with factory() as db:
        assert db.scalar(select(User)).password_hash == original


def test_backup_failure_prevents_f2_upgrade(tmp_path):
    from unittest.mock import MagicMock, patch

    from tools import f2_local

    with (
        patch.object(f2_local, "snapshot", return_value={}),
        patch.object(f2_local, "backup_restore", side_effect=RuntimeError("backup failed")),
        patch.object(f2_local, "upgrade") as upgrade,
        pytest.raises(RuntimeError, match="backup failed"),
    ):
        f2_local.controlled_upgrade(MagicMock(), tmp_path)
    upgrade.assert_not_called()


def test_real_expiration_request_limits_and_rate_limit(api, tokens):
    from sqlalchemy import select

    from app.models.identity import RefreshSession, User

    client, factory = api
    response = login_admin(client)
    with factory() as db:
        user = db.scalar(select(User))
        family = db.scalar(select(RefreshSession.family_id))
        expired = tokens.encode(
            user, family, "access", now() - timedelta(seconds=60), secrets.token_urlsafe(32)
        )
    assert (
        client.get("/api/v1/auth/me", headers={"authorization": "Bearer " + expired}).status_code
        == 401
    )
    assert client.post("/api/v1/auth/login", content="email=invalid").status_code == 415
    oversized = client.post(
        "/api/v1/auth/login", content=b"x" * 1048577, headers={"content-type": "application/json"}
    )
    assert oversized.status_code == 413
    assert oversized.json()["request_id"] == oversized.headers["x-request-id"]
    for _unused in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "absent@example.invalid", "password": "synthetic-invalid"},
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "absent@example.invalid", "password": "synthetic-invalid"},
        ).status_code
        == 429
    )


def test_real_refresh_rate_limit_keeps_current_session(api):
    client, _ = api
    response = login_admin(client)
    csrf = {"x-csrf-token": response.json()["csrf_token"]}
    for _unused in range(10):
        response = client.post("/api/v1/auth/refresh", headers=csrf)
        assert response.status_code == 200
    access = response.json()["access_token"]
    limited = client.post("/api/v1/auth/refresh", headers=csrf)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert (
        client.get("/api/v1/auth/me", headers={"authorization": "Bearer " + access}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "path,codes",
    [
        ("priorities", ["normal", "high"]),
        ("horizon-types", ["custom", "annual"]),
    ],
)
def test_real_catalog_reorder_is_atomic_and_versioned(api, path, codes):
    client, _ = api
    authenticated(client)
    records = []
    for position, code in enumerate(codes):
        response = client.post(
            "/api/v1/" + path,
            json={
                "code": code,
                "name": "Synthetic " + code,
                "position": position,
                "reason": "Synthetic catalog configuration",
            },
        )
        assert response.status_code == 201
        records.append(response.json())
    body = {
        "reason": "Synthetic atomic reordering",
        "items": [
            {"id": record["id"], "position": 1 - index, "expected_version": 1}
            for index, record in enumerate(records)
        ],
    }
    body["items"][1]["expected_version"] = 2
    assert client.post("/api/v1/" + path + "/reorder", json=body).status_code == 409
    for record in records:
        assert client.get("/api/v1/" + path + "/" + record["id"]).json() == record
    body["items"][1]["expected_version"] = 1
    response = client.post("/api/v1/" + path + "/reorder", json=body)
    assert response.status_code == 200, response.text
    assert [record["position"] for record in response.json()["items"]] == [1, 0]
    assert all(record["version"] == 2 for record in response.json()["items"])


def test_real_audit_and_release_projection_pagination(api):
    from sqlalchemy import text

    from tools.f2_local import migration_engine

    client, factory = api
    authenticated(client)
    engine = migration_engine(factory.kw["bind"].url.database)
    try:
        with engine.begin() as connection:
            for _unused in range(3):
                connection.execute(
                    text(
                        "INSERT INTO release_history (id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,request_id) VALUES (:id,now(),now(),'0.2.0',"
                        ":hash,:hash,'20261124_0001','20261124_0002','Synthetic operator',"
                        "'local','validation','running',:request_id)"
                    ),
                    {"id": uuid4(), "request_id": uuid4(), "hash": "0" * 64},
                )
    finally:
        engine.dispose()
    for path in ("audit-events", "releases"):
        seen, cursor = set(), None
        while True:
            params = {"limit": 5}
            if cursor:
                params["cursor"] = cursor
            response = client.get("/api/v1/" + path, params=params)
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) <= 5
            for record in body["items"]:
                assert record["id"] not in seen
                seen.add(record["id"])
                if path == "releases":
                    assert "artifact_sha256" not in record
                    assert "operator_ref" not in record
                    assert client.get("/api/v1/releases/" + record["id"]).json() == record
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert len(seen) == (3 if path == "releases" else 12)
    assert client.get("/api/v1/releases/" + str(uuid4())).status_code == 404
    assert client.get("/api/v1/release-history").json() == client.get("/api/v1/releases").json()


def test_failed_release_only_transitions_own_running_record():
    from unittest.mock import patch

    from tools import f2_local

    attempt = uuid4()
    with patch.object(f2_local.local, "role_connection") as connection:
        execute = connection.return_value.__enter__.return_value.execute
        execute.return_value.rowcount = 1
        assert f2_local.record_failure(attempt) == 1
    statement, values = execute.call_args.args
    assert "status='failed'" in statement
    assert "WHERE id=%s AND version=1 AND status='running'" in statement
    assert values[-1] == attempt


def test_real_runtime_append_only_and_database_constraints(api):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tools.f2_local import migration_engine

    _, factory = api
    for statement in (
        "UPDATE audit_events SET outcome='failure' WHERE false",
        "DELETE FROM audit_events WHERE false",
        "DELETE FROM users WHERE false",
        "UPDATE release_history SET version=version+1 WHERE false",
        "CREATE TABLE f2_forbidden(id INTEGER)",
        "SET ROLE ocote_migrador",
    ):
        with pytest.raises(DBAPIError), factory.begin() as db:
            db.execute(text(statement))
    engine = migration_engine(factory.kw["bind"].url.database)
    try:
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text("UPDATE audit_events SET outcome='failure'"))
    finally:
        engine.dispose()


def test_init_auth_never_overwrites_existing_keys(tmp_path, monkeypatch):
    from dotenv import dotenv_values

    from tools import bootstrap

    monkeypatch.setattr(bootstrap.local, "LOCAL", tmp_path)
    bootstrap.init_auth("https://localhost:8443")
    configuration = dotenv_values(tmp_path / "auth.env")
    assert configuration["AUTH_ORIGIN"] == "https://localhost:8443"
    assert Tokens(AuthSettings(_env_file=tmp_path / "auth.env")).kid
    original = (tmp_path / "auth-signing.pem").read_bytes()
    with pytest.raises(RuntimeError):
        bootstrap.init_auth("https://localhost:8443")
    assert (tmp_path / "auth-signing.pem").read_bytes() == original
