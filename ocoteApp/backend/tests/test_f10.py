from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_identity import api as api
from test_identity import tokens as tokens
from test_operations import core as core

from app.core.errors import CommandError
from app.core.notifications import (
    calendar_content,
    fold_line,
    ical_escape,
    provider_target,
    quiet_until,
    send,
)
from app.schemas.notifications import ChatConfig, PreferencesWrite, SMTPConfig


def network(**changes):
    return {
        "host": "hooks.slack.com",
        "approved_addresses": ["93.184.216.34"],
        "connect_timeout_seconds": 2,
        "read_timeout_seconds": 3,
        "rate_per_minute": 10,
        "audience_approved": False,
        "allow_private_endpoint": False,
        **changes,
    }


def test_f10_codes_are_registered_without_seeding_or_activating_modules():
    from typing import get_args

    from app.core.vault import PURPOSES
    from app.schemas.enterprise import MODULES
    from app.schemas.platform import Purpose

    assert {
        "notifications",
        "email_notifications",
        "corporate_messaging",
        "calendar_feeds",
    } <= MODULES
    assert {"notifications", "calendar_feed"} <= PURPOSES & set(get_args(Purpose))


def test_f10_personal_projections_never_include_feed_capabilities_or_secret_references():
    from app.services.notifications import feed_signature, feed_view, preferences_view

    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        owner_user_id=uuid4(),
        name="Synthetic feed",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        created_at=datetime.now(UTC),
        revoked_at=None,
        token_hash="synthetic",
        signing_secret_id=uuid4(),
    )
    assert set(feed_view(record)) == {
        "id",
        "version",
        "name",
        "created_at",
        "expires_at",
        "revoked_at",
    }
    signature = feed_signature("synthetic key", record, "synthetic nonce")
    assert signature != feed_signature("different key", record, "synthetic nonce")
    assert signature != feed_signature("synthetic key", record, "different nonce")
    record.owner_user_id = uuid4()
    assert signature != feed_signature("synthetic key", record, "synthetic nonce")
    assert preferences_view(None) is None


def test_f10_vault_boundary_decodes_only_owned_utf8_secrets(monkeypatch):
    from app.models.platform import EncryptedSecret
    from app.services import platform
    from app.services.notifications import decrypted_secret

    owner, identity = uuid4(), uuid4()
    secret = SimpleNamespace(owner_id=owner, purpose="calendar_feed", key_id=uuid4())
    db = SimpleNamespace(get=lambda model, key: secret if model is EncryptedSecret else None)
    monkeypatch.setattr(platform, "wrapped", lambda key: None)
    monkeypatch.setattr(platform, "encrypted", lambda value: None)
    monkeypatch.setattr(
        platform, "vault", lambda *args: SimpleNamespace(decrypt=lambda *args: b"synthetic-key")
    )
    assert decrypted_secret(db, owner, identity, "calendar_feed") == "synthetic-key"
    with pytest.raises(CommandError):
        decrypted_secret(db, uuid4(), identity, "calendar_feed")


def test_f10_personal_routes_compile_and_feed_access_logs_redact_query():
    import logging

    from fastapi import FastAPI

    from app.core.notifications import CalendarAccessFilter
    from app.routers.notifications import router

    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/notification-preferences" in paths
    assert "/api/v1/calendar-feeds/{identity}/content" in paths
    assert "/api/v1/notification-connectors/{identity}/tests" in paths
    assert "/api/v1/notification-rules/{identity}" in paths
    assert "/api/v1/notifications/service-principals/{identity}" in paths
    arguments = (
        "client",
        "GET",
        "/api/v1/calendar-feeds/synthetic/content?capability=private",
        "1.1",
        200,
    )
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 1, "%s %s %s %s %s", arguments, None
    )
    assert CalendarAccessFilter().filter(record)
    assert "private" not in record.getMessage()


def test_f10_connector_projection_omits_secret_values_and_ciphertext():
    from app.services.notifications import connector_view

    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        name="Synthetic",
        scope_kind="organization",
        department_id=None,
        provider="slack",
        config=network(provider="slack", destination="Synthetic"),
        config_revision=1,
        is_active=False,
        tested_version=None,
        tested_at=None,
        secret_id=uuid4(),
    )
    view = connector_view(record)
    assert view["secret_configured"] is True
    assert not {"secret_id", "credential", "ciphertext", "token", "webhook_url"} & view.keys()


@pytest.mark.parametrize("changed_during_probe", [False, True])
def test_f10_probe_runs_without_transaction_and_fences_changed_revisions(
    monkeypatch, changed_during_probe
):
    from app.services import notifications as service

    actor = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        config_revision=1,
        provider="slack",
        is_active=False,
        tested_version=None,
        tested_at=None,
    )
    db = SimpleNamespace(info={}, in_transaction=True, added=[], committed=False)

    def commit():
        db.in_transaction, db.committed = False, True

    def lock(*args):
        db.in_transaction = True

    def deliver(*args, **kwargs):
        assert db.committed and not db.in_transaction
        if changed_during_probe:
            record.version += 1

    db.commit, db.expire_all, db.flush = commit, lambda: None, lambda: None
    db.add, db.scalar, db.get = db.added.append, lambda query: 0, lambda *args, **kwargs: actor
    monkeypatch.setattr(service, "reauthenticate", lambda *args: None)
    monkeypatch.setattr(service, "require_connectors", lambda *args: None)
    monkeypatch.setattr(service, "connector_for", lambda *args: record)
    monkeypatch.setattr(service, "changed", lambda *args: None)
    monkeypatch.setattr(service, "connector_view", lambda row: {"version": row.version})
    monkeypatch.setattr(service, "config_lock", lock)
    monkeypatch.setattr(service, "send", deliver)
    monkeypatch.setattr(
        service,
        "connector_material",
        lambda *args: (
            network(provider="slack", destination="Synthetic", audience_approved=True),
            "synthetic-secret",
        ),
    )
    request = SimpleNamespace(
        state=SimpleNamespace(request_id=str(uuid4())), app=SimpleNamespace(state=SimpleNamespace())
    )
    body = SimpleNamespace(
        expected_version=1, destination="Synthetic", confirmed=True, reason="Synthetic probe"
    )
    if changed_during_probe:
        with pytest.raises(CommandError) as failure:
            service.test_connector(db, record.id, body, request, actor)
        assert failure.value.code == "CONFIGURATION_CHANGED_DURING_TEST"
        assert record.tested_version is None
        assert db.added[-1].status == "failed"
    else:
        assert service.test_connector(db, record.id, body, request, actor)["passed"]
        assert record.tested_version == 1
        assert db.added[-1].status == "passed"


def test_f10_worker_has_bounded_budget_backoff_and_stable_date_deduplication():
    from app.services.notification_worker import checked_budget, date_event_id, retry_time, tick

    for value in (0, 101, True, "10", None):
        with pytest.raises(CommandError):
            checked_budget(value)
    assert checked_budget(100) == 100
    with pytest.raises(CommandError):
        tick(None, uuid4(), 0)
    moment = datetime(2026, 11, 26, tzinfo=UTC)
    assert (retry_time(moment, 10, 300) - moment).total_seconds() == 86400
    rule, task = SimpleNamespace(id=uuid4(), version=1), SimpleNamespace(id=uuid4())
    identity = date_event_id(rule, task, moment.date())
    assert identity == date_event_id(rule, task, moment.date())
    rule.version += 1
    assert identity != date_event_id(rule, task, moment.date())


def test_f10_worker_never_invents_missing_preferences_or_enables_channels(monkeypatch):
    from app.services import notification_worker as worker

    rule = SimpleNamespace(channels=["in_app", "email", "messaging"])
    assert worker.chosen_channels(None, rule, None) == set()
    preference = SimpleNamespace(opt_in=False, channels=rule.channels)
    assert worker.chosen_channels(None, rule, preference) == set()
    preference.opt_in = True
    monkeypatch.setattr(worker.enterprise, "enabled", lambda *args: False)
    assert worker.chosen_channels(None, rule, preference) == {"in_app"}


def test_f10_worker_queries_compile_with_row_locks_and_scope_before_limits():
    from sqlalchemy.dialects import postgresql

    from app.services import notification_worker as worker

    captured = []

    def scalar(query):
        captured.append(str(query.compile(dialect=postgresql.dialect())))
        return None

    principal = SimpleNamespace(id=uuid4(), department_ids=[uuid4()])
    assert worker.claim(SimpleNamespace(scalar=scalar), principal, None) is None
    assert "FOR UPDATE OF notification_deliveries SKIP LOCKED" in captured[0]
    assert "transactional_outbox.department_id IN" in captured[0]


@pytest.mark.parametrize(
    "passed,expired,expected",
    [
        (True, False, "accepted"),
        (False, False, "ambiguous"),
        (True, True, "ambiguous"),
    ],
)
def test_f10_worker_fences_completion_and_never_calls_unknown_outcome_success(
    monkeypatch, passed, expired, expected
):
    from datetime import timedelta

    from app.models.notifications import Notification, NotificationDelivery
    from app.services import notification_worker as worker

    moment, token = datetime.now(UTC), uuid4()
    record = SimpleNamespace(
        state="sending",
        lease_token=token,
        notification_id=uuid4(),
        lease_until=moment + timedelta(seconds=-1 if expired else 90),
        version=1,
    )
    notice = SimpleNamespace(rule_id=uuid4())
    records = {NotificationDelivery: record, Notification: notice}
    db = SimpleNamespace(get=lambda model, *args, **kwargs: records.get(model))
    monkeypatch.setattr(worker, "changed", lambda *args: None)
    monkeypatch.setattr(worker, "queue_retry", lambda *args: None)
    prepared = {"id": uuid4(), "lease_token": token}
    assert worker.finish(db, None, prepared, passed, None) == expected
    assert record.lease_token is None and record.lease_until is None
    assert worker.finish(db, None, prepared, True, None) == "superseded"


def test_f10_revision_is_additive_and_models_have_no_business_defaults():
    import importlib
    import runpy
    from pathlib import Path

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.models import notifications

    for module in (
        "identity",
        "operations",
        "evaluations",
        "platform",
        "enterprise",
        "collaboration",
    ):
        importlib.import_module("app.models." + module)
    revision = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic/versions/20261126_0009_notifications.py")
    )
    assert revision["down_revision"] == "20261125_0008"
    assert len(revision["TABLES"]) == 8
    for table in revision["TABLES"]:
        assert table in notifications.Base.metadata.tables
        assert str(
            CreateTable(notifications.Base.metadata.tables[table]).compile(
                dialect=postgresql.dialect()
            )
        )
    with pytest.raises(RuntimeError):
        revision["downgrade"]()


def test_f10_dispatch_scope_is_explicit_and_inbox_is_quiet_hours_filtered():
    from sqlalchemy.dialects import postgresql

    from app.schemas.collaboration import PrincipalWrite
    from app.services.notifications import scoped_notifications

    body = PrincipalWrite(
        expected_version=0,
        reason="Synthetic worker permission",
        name="Synthetic worker",
        department_ids=[uuid4()],
        approved_scopes=["notifications:dispatch"],
        is_active=True,
    )
    assert body.approved_scopes == ["notifications:dispatch"]
    actor = SimpleNamespace(id=uuid4(), role="colaborador", department_id=uuid4())
    query = str(scoped_notifications(actor).compile(dialect=postgresql.dialect()))
    assert "notifications.available_at <=" in query and "notifications.in_app" in query
    assert "tasks.assignee_id =" in query and "notifications.user_id =" in query


def test_f10_provider_targets_never_accept_unapproved_hosts_or_redirect_urls():
    config = network(provider="slack", destination="Synthetic channel")
    assert (
        provider_target(config, "https://hooks.slack.com/services/synthetic/probe")[0]
        == config["host"]
    )
    for secret in (
        "http://hooks.slack.com/services/probe",
        "https://hooks.slack.com.evil.invalid/services/a",
        "https://user:secret@hooks.slack.com/services/a",
        "https://hooks.slack.com/services/a#secret",
        "https://hooks.slack.com/services/a?token=secret",
        "https://127.0.0.1/services/a",
    ):
        with pytest.raises(CommandError) as failure:
            provider_target(config, secret)
        assert failure.value.code == "NOTIFICATION_PROVIDER_UNAVAILABLE_OR_UNSAFE"
        assert secret not in str(failure.value)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "10.0.0.1"]
)
def test_f10_chat_rejects_nonpublic_addresses(address):
    with pytest.raises(ValidationError):
        ChatConfig(
            **network(provider="slack", destination="Synthetic", approved_addresses=[address])
        )


def test_f10_smtp_requires_tls_and_explicit_private_approval():
    values = network(
        provider="smtp",
        host="mail.example.invalid",
        port=465,
        security="tls",
        authentication="login",
        username="synthetic",
        sender_email="ocote@example.invalid",
        sender_name="OCOTE",
        test_recipient="test@example.invalid",
    )
    assert SMTPConfig(**values).security == "tls"
    for change in (
        {"security": "none"},
        {"username": None},
        {"sender_name": "OCOTE\r\nBcc: other"},
        {"approved_addresses": ["10.0.0.1"]},
    ):
        with pytest.raises(ValidationError):
            SMTPConfig(**(values | change))
    assert SMTPConfig(
        **(values | {"approved_addresses": ["10.0.0.1"], "allow_private_endpoint": True})
    )


def test_f10_transport_uses_only_generic_content_and_sanitizes_provider_failures():
    captured = []

    def transport(*arguments, **options):
        captured.append((arguments, options))
        return 200, {}, b"ok"

    config = network(provider="slack", destination="Synthetic")
    send(config, "https://hooks.slack.com/services/synthetic/probe", test=True, transport=transport)
    assert b"PRUEBA DE CONEXION" in captured[0][0][6]
    assert captured[0][1]["limit"] == 16384
    with pytest.raises(CommandError) as failure:
        send(
            config,
            "https://hooks.slack.com/services/synthetic/probe",
            transport=lambda *args, **kwargs: (302, {}, b"secret"),
        )
    assert failure.value.code == "NOTIFICATION_PROVIDER_UNAVAILABLE_OR_UNSAFE"


@pytest.mark.parametrize(
    "moment,zone,start,end,expected",
    [
        (
            "2026-01-02T03:00:00+00:00",
            "America/Mexico_City",
            "22:00",
            "07:00",
            "2026-01-02T03:00:00+00:00",
        ),
        (
            "2026-01-02T05:00:00+00:00",
            "America/Mexico_City",
            "22:00",
            "07:00",
            "2026-01-02T13:00:00+00:00",
        ),
        (
            "2026-11-01T04:30:00+00:00",
            "America/New_York",
            "00:00",
            "01:30",
            "2026-11-01T06:30:00+00:00",
        ),
        (
            "2026-03-08T06:30:00+00:00",
            "America/New_York",
            "00:00",
            "02:30",
            "2026-03-08T07:30:00+00:00",
        ),
    ],
)
def test_f10_quiet_hours_cross_midnight_and_dst(moment, zone, start, end, expected):
    assert quiet_until(datetime.fromisoformat(moment), start, end, zone) == datetime.fromisoformat(
        expected
    )


def test_f10_preferences_have_no_implicit_timezone_or_quiet_interval():
    values = {
        "expected_version": 0,
        "reason": "Synthetic preference",
        "channels": ["in_app"],
        "opt_in": True,
        "quiet_start": None,
        "quiet_end": None,
        "timezone": "America/Mexico_City",
    }
    assert PreferencesWrite(**values).opt_in
    for changes in (
        {"timezone": "invalid/no"},
        {"quiet_start": "22:00"},
        {"channels": ["in_app", "in_app"]},
    ):
        with pytest.raises(ValidationError):
            PreferencesWrite(**(values | changes))


def test_f10_ical_dates_are_exclusive_stable_and_utf8_folded():
    task = SimpleNamespace(
        id=uuid4(),
        start_date=date(2026, 12, 31),
        due_date=date(2027, 1, 2),
        original_due_date=date(2027, 1, 1),
    )
    output = calendar_content([task], datetime(2026, 11, 26, tzinfo=UTC))
    assert output.count(b"BEGIN:VEVENT") == 3
    assert b"DTEND;VALUE=DATE:20270103" in output
    assert (str(task.id) + "-current@ocote").encode() in output
    assert "\r\nBEGIN:VEVENT" not in ical_escape("name\r\nBEGIN:VEVENT")
    folded = fold_line("SUMMARY:" + chr(0xE9) * 100)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "SUMMARY:" + chr(0xE9) * 100


@pytest.fixture
def f10_api(core):
    import os

    from sqlalchemy import select

    from app.core.vault import Vault
    from app.models.platform import DeploymentInstance

    client, factory, *_rest = core
    with factory() as db:
        instance = db.scalar(select(DeploymentInstance))
        client.app.state.vault = Vault(os.urandom(32), instance.id, instance.root_key_ref)
    return core


@pytest.mark.parametrize(
    "security,fail_tls", [("tls", False), ("starttls", False), ("starttls", True)]
)
def test_f10_smtp_pins_resolution_and_never_authenticates_before_tls(
    monkeypatch, security, fail_tls
):
    import smtplib
    import ssl

    from app.core import notifications

    events = []
    config = network(
        provider="smtp",
        host="smtp.example.invalid",
        port=587,
        security=security,
        authentication="login",
        username="synthetic",
        sender_email="synthetic@example.invalid",
        sender_name="OCOTE sintetico",
    )

    def checked(host, port, approved, private):
        assert (host, port, approved, private) == (
            config["host"],
            587,
            config["approved_addresses"],
            False,
        )
        events.append("dns")
        return ["93.184.216.34"]

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_error):
            return None

        def ehlo(self):
            events.append("ehlo")

        def starttls(self, *, context):
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            events.append("tls")
            if fail_tls:
                raise smtplib.SMTPNotSupportedError("Synthetic server rejects TLS")

        def login(self, username, credential):
            assert (username, credential) == ("synthetic", "synthetic-password")
            events.append("login")

        def send_message(self, content):
            assert content["To"] == "approved@example.invalid"
            assert notifications.TEST_MESSAGE in content.get_content()
            assert "synthetic-password" not in content.as_string()
            events.append("send")
            return {}

    def factory(settings, address):
        assert settings is config and address == "93.184.216.34"
        events.append("connect")
        return Client()

    monkeypatch.setattr(notifications, "checked_addresses", checked)
    if fail_tls:
        with pytest.raises(CommandError, match="NOTIFICATION_PROVIDER_UNAVAILABLE_OR_UNSAFE"):
            send(
                config,
                "synthetic-password",
                recipient="approved@example.invalid",
                test=True,
                smtp_factory=factory,
            )
        assert events == ["dns", "connect", "ehlo", "tls"]
    else:
        send(
            config,
            "synthetic-password",
            recipient="approved@example.invalid",
            test=True,
            smtp_factory=factory,
        )
        assert events == [
            "dns",
            "connect",
            "ehlo",
            *(["tls", "ehlo"] if security == "starttls" else []),
            "login",
            "send",
        ]


@pytest.mark.parametrize("refused", [False, True])
def test_f10_implicit_smtp_tls_uses_original_hostname_and_closes_rejected_socket(
    monkeypatch, refused
):
    from app.core import notifications

    observed = []
    connection = SimpleNamespace(
        settimeout=lambda value: observed.append(("read_timeout", value)),
        close=lambda: observed.append(("closed", True)),
    )

    def connect(target, timeout):
        assert target == ("93.184.216.34", 465) and timeout == 2
        return connection

    def wrap(candidate, *, server_hostname):
        assert candidate is connection and server_hostname == "smtp.example.invalid"
        if refused:
            raise OSError("Synthetic certificate rejection")
        return "synthetic-tls-socket"

    monkeypatch.setattr(notifications.socket, "create_connection", connect)
    monkeypatch.setattr(
        notifications.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    client = notifications.PinnedSMTPSSL.__new__(notifications.PinnedSMTPSSL)
    client.address, client.read_timeout = "93.184.216.34", 3
    if refused:
        with pytest.raises(OSError, match="Synthetic certificate rejection"):
            client._get_socket("smtp.example.invalid", 465, 2)
        assert observed == [("read_timeout", 3), ("closed", True)]
    else:
        assert client._get_socket("smtp.example.invalid", 465, 2) == "synthetic-tls-socket"
        assert observed == [("read_timeout", 3)]


def test_f10_operator_capture_uses_own_context_expiry_and_never_renews(monkeypatch, tmp_path):
    import json

    from tools import f10_local
    from tools.f8_local import OPERATOR_CONTEXT as f8_context
    from tools.f9_local import OPERATOR_CONTEXT as f9_context

    contents = {}

    class Seal:
        def __init__(self, path, context):
            assert context not in {f8_context, f9_context}
            self.path = path

        def create(self, value):
            self.path.touch(exist_ok=False)
            contents[self.path] = value

        def read(self):
            return contents[self.path]

    monkeypatch.setattr(f10_local, "OSSealedFile", Seal)
    monkeypatch.setattr(f10_local, "private_directory", lambda _path: None)
    path = tmp_path / "synthetic.dpapi"
    f10_local.save_authorization("synthetic-password", path=path, issued_at=100)
    assert f10_local.authorization(path=path, current_time=101)["expires_at"] == 3700
    with pytest.raises(CommandError, match="FRESH_F10_CAPTURE_REQUIRED_NO_RENEWAL"):
        f10_local.save_authorization("synthetic-password", path=path, issued_at=102)
    for moment in (99, 3700, float("nan"), True):
        with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
            f10_local.authorization(path=path, current_time=moment)
    payload = json.loads(contents[path])
    payload["purpose"] = "ocote-f9-local-postgres-only"
    contents[path] = json.dumps(payload).encode()
    with pytest.raises(CommandError, match="LOCAL_AUTHORIZATION_MISSING_OR_EXPIRED"):
        f10_local.authorization(path=path, current_time=101)


def test_f10_final_gates_stop_before_release_and_always_revoke(monkeypatch, tmp_path):
    import time

    from tools import f10_local

    calls = []
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setattr(
        f10_local,
        "authorization",
        lambda: {"password": "synthetic", "expires_at": time.time() + 3600},
    )
    monkeypatch.setattr(f10_local, "private_directory", lambda _path: None)
    monkeypatch.setattr(f10_local, "write_private", lambda *_args: None)
    monkeypatch.setattr(f10_local, "revoke", lambda: calls.append("revoked"))
    monkeypatch.setattr(f10_local, "drain_api", lambda: calls.append("drained"))

    def run(arguments, _payload, _output):
        calls.append(arguments)
        return 1

    monkeypatch.setattr(f10_local, "run_authorized", run)
    assert f10_local.run_final_gates(tmp_path) == 1
    assert len(calls) == 2 and calls[-1] == "revoked" and "drained" not in calls
    assert calls[0][-2].endswith("migration_noop_preservation_and_privileges")
    assert calls[0][-1].endswith("version_audit_timezone_and_runtime_protections")


def test_f10_release_requires_exact_additions_and_preserves_every_old_value():
    import copy
    import json

    from tools import f10_release

    before = {
        "tables": ["alembic_version", "transactional_outbox", "feature_flags"],
        "rows": {
            "alembic_version": [json.dumps({"version_num": f10_release.SOURCE})],
            "transactional_outbox": [json.dumps({"id": "synthetic", "payload": {}})],
            "feature_flags": [json.dumps({"code": "timeline", "enabled": True})],
        },
    }
    after = copy.deepcopy(before)
    after["tables"] += sorted(f10_release.ADDED)
    after["rows"].update({table: [] for table in f10_release.ADDED})
    after["rows"]["alembic_version"] = [json.dumps({"version_num": f10_release.HEAD})]
    after["rows"]["transactional_outbox"] = [
        json.dumps(
            {
                "id": "synthetic",
                "payload": {},
                "evaluation_id": None,
            }
        )
    ]
    f10_release.upgraded(before, after)
    mutated = copy.deepcopy(after)
    mutated["rows"]["notification_preferences"] = [json.dumps({"opt_in": True})]
    with pytest.raises(RuntimeError, match="business defaults"):
        f10_release.upgraded(before, mutated)
    mutated = copy.deepcopy(after)
    mutated["rows"]["feature_flags"] = [json.dumps({"code": "timeline", "enabled": False})]
    with pytest.raises(RuntimeError, match="Historical value changed"):
        f10_release.upgraded(before, mutated)


def test_f10_dispatch_locks_the_rule_without_requesting_update_on_append_only_outbox(monkeypatch):
    from sqlalchemy.dialects import postgresql

    from app.services import notification_worker

    statements = []
    rule = SimpleNamespace(
        id=uuid4(),
        version=1,
        trigger="assignment",
        max_age_hours=24,
        updated_at=datetime.now(UTC),
        department_id=uuid4(),
    )

    def scalar(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return rule if len(statements) == 1 else None

    monkeypatch.setattr(notification_worker.enterprise, "enabled", lambda *_args: True)
    assert (
        notification_worker.dispatch_one(
            SimpleNamespace(scalar=scalar),
            SimpleNamespace(department_ids=[rule.department_id]),
            rule.id,
            None,
        )
        is False
    )
    assert "FOR UPDATE SKIP LOCKED" in statements[0]
    assert "transactional_outbox" in statements[1] and "notification_dispatches" in statements[1]
    assert "FOR UPDATE" not in statements[1]


def synthetic_command(**changes):
    return {
        "current_password": "Synthetic-password-123!",
        "expected_version": 0,
        "reason": "Explicit synthetic UUID-only F10 operation",
        **changes,
    }


@pytest.mark.parametrize("revision", ["20261126_0009", "20261125_0008"])
def test_f10_recurrence_entry_preserves_runtime_head_and_fail_closed_flags(monkeypatch, revision):
    from contextlib import nullcontext

    from tools import f10_worker

    database = SimpleNamespace(
        scalar=lambda query: {
            "SELECT current_user": "ocote_runtime",
            "SELECT version_num FROM alembic_version": revision,
        }[str(query)]
    )
    factory = SimpleNamespace(begin=lambda: nullcontext(database))
    monkeypatch.setattr(f10_worker, "config_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(f10_worker, "enabled", lambda *_args: False)
    if revision == "20261126_0009":
        assert f10_worker.recurrence_tick(factory, 1) == {
            "processed": 0,
            "generated": 0,
            "paused": 0,
            "conflicts": 0,
            "failures": 0,
        }
    else:
        with pytest.raises(CommandError, match="F10_REVISION_REQUIRED"):
            f10_worker.recurrence_tick(factory, 1)


def test_real_f10_additive_migration_noop_preservation_and_privileges():
    import os
    import runpy
    from pathlib import Path

    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit F10 isolated PostgreSQL authorization required")
    from sqlalchemy import text

    from tools.f2_local import isolated_database, migration_engine, upgrade

    revision = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic/versions/20261126_0009_notifications.py")
    )
    with isolated_database() as name:
        upgrade(name, "20261125_0008")
        engine = migration_engine(name)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO deployment_instances(id,root_key_ref) "
                        "VALUES(:id,'synthetic-f10-preserved-root')"
                    ),
                    {"id": uuid4()},
                )
                tables = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                before = {
                    table: connection.execute(
                        text(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY to_jsonb(t)::text")
                    ).all()
                    for table in tables - {"alembic_version"}
                }
            upgrade(name, "20261126_0009")
            upgrade(name, "20261126_0009")
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "20261126_0009"
                )
                after = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                assert len(after) == 58 and after - tables == set(revision["TABLES"])
                for table in revision["TABLES"]:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                    assert not connection.scalar(
                        text("SELECT has_table_privilege('ocote_runtime',:name,'DELETE,TRUNCATE')"),
                        {"name": table},
                    )
                for table, rows in before.items():
                    projection = (
                        "to_jsonb(t)-'evaluation_id'"
                        if table == "transactional_outbox"
                        else "to_jsonb(t)"
                    )
                    assert (
                        connection.execute(
                            text(
                                f"SELECT ({projection})::text FROM {table} t "
                                f"ORDER BY ({projection})::text"
                            )
                        ).all()
                        == rows
                    )
                for table in revision["APPEND_ONLY"]:
                    assert not connection.scalar(
                        text("SELECT has_table_privilege('ocote_runtime',:name,'UPDATE')"),
                        {"name": table},
                    )
        finally:
            engine.dispose()


def test_real_f10_version_audit_timezone_and_runtime_protections(f10_api):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    client, factory, *_rest = f10_api
    response = client.patch(
        "/api/v1/notification-preferences",
        json={
            "expected_version": 0,
            "reason": "Explicit UUID-only preference protection test",
            "channels": ["in_app"],
            "opt_in": True,
            "timezone": "America/Mexico_City",
            "quiet_start": None,
            "quiet_end": None,
        },
    )
    assert response.status_code == 200, response.text
    attempts = [
        "UPDATE notification_preferences SET opt_in=false",
        "UPDATE notification_preferences SET opt_in=false,version=version+1,"
        "updated_at=clock_timestamp()",
        "UPDATE notification_preferences SET timezone='Invalid/F10',version=version+1,"
        "updated_at=clock_timestamp()",
        "UPDATE notification_preferences SET channels=ARRAY['unsafe'],version=version+1,"
        "updated_at=clock_timestamp()",
        "UPDATE notification_preferences SET quiet_start='22:00',version=version+1,"
        "updated_at=clock_timestamp()",
        "DELETE FROM notification_preferences",
        "TRUNCATE notification_preferences CASCADE",
    ]
    for statement in attempts:
        with pytest.raises(DBAPIError), factory.begin() as database:
            database.execute(text(statement))
    current = client.get("/api/v1/notification-preferences").json()
    assert current["version"] == 1 and current["opt_in"] is True


def test_real_f10_connectors_require_probe_before_activation_and_preserve_omitted_secret(f10_api):
    from sqlalchemy import text

    client, factory, *_rest = f10_api
    config = network(
        provider="slack", destination="Synthetic approved audience", audience_approved=True
    )
    credential = "https://hooks.slack.com/services/synthetic/probe"
    body = synthetic_command(
        name="Synthetic Slack",
        scope_kind="organization",
        department_id=None,
        config=config,
        credential=credential,
    )
    response = client.post("/api/v1/notification-connectors", json=body)
    assert response.status_code == 201, response.text
    connector = response.json()
    assert connector["secret_configured"] and credential not in response.text
    path = "/api/v1/notification-connectors/" + connector["id"]
    denied = client.post(
        path + "/activate", json=synthetic_command(expected_version=connector["version"])
    )
    assert denied.status_code == 409, denied.text
    calls = []

    def transport(*args, **kwargs):
        with factory() as db:
            assert (
                db.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND usename=current_user "
                        "AND state='idle in transaction'"
                    )
                )
                == 0
            )
        calls.append(True)
        return 200, {}, b"ok"

    client.app.state.notification_transport = transport
    wrong = client.post(
        path + "/tests",
        json=synthetic_command(
            expected_version=connector["version"], destination="Unapproved", confirmed=True
        ),
    )
    assert wrong.status_code == 422 and not calls
    tested = client.post(
        path + "/tests",
        json=synthetic_command(
            expected_version=connector["version"], destination=config["destination"], confirmed=True
        ),
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["passed"] and not tested.json()["is_active"] and len(calls) == 1
    active = client.post(
        path + "/activate", json=synthetic_command(expected_version=tested.json()["version"])
    )
    assert active.status_code == 200 and active.json()["is_active"], active.text
    body.pop("credential")
    body.update(name="Synthetic renamed", expected_version=active.json()["version"])
    edited = client.patch(path, json=body)
    assert edited.status_code == 200, edited.text
    assert edited.json()["secret_configured"] and not edited.json()["is_active"]
    assert edited.json()["tested_at"] is None and credential not in edited.text
    assert client.patch(path, json=body).status_code == 409


def test_real_f10_personal_preferences_feeds_and_revocation(f10_api):
    from datetime import timedelta

    client, _factory, *_rest = f10_api
    assert client.get("/api/v1/notification-preferences").json() is None
    preference = {
        "expected_version": 0,
        "reason": "Synthetic explicit personal choice",
        "channels": ["in_app"],
        "opt_in": True,
        "quiet_start": None,
        "quiet_end": None,
        "timezone": "America/Mexico_City",
    }
    saved = client.patch("/api/v1/notification-preferences", json=preference)
    assert saved.status_code == 200, saved.text
    assert client.patch("/api/v1/notification-preferences", json=preference).status_code == 409
    created = client.post(
        "/api/v1/integrations/calendar-feeds",
        json={
            "name": "Synthetic calendar",
            "expected_version": 0,
            "reason": "Synthetic private feed choice",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    feed = created.json()
    assert feed["capability"] not in client.get("/api/v1/integrations/calendar-feeds").text
    path = "/api/v1/calendar-feeds/" + feed["id"] + "/content"
    response = client.get(path, params={"capability": feed["capability"]})
    assert response.status_code == 200, response.text
    assert "BEGIN:VCALENDAR" in response.text
    assert "no-store" in {value.strip() for value in response.headers["cache-control"].split(",")}
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get(path, params={"capability": "invalid"}).status_code == 404
    revoked = client.post(
        "/api/v1/integrations/calendar-feeds/" + feed["id"] + "/revoke",
        json={"expected_version": feed["version"], "reason": "Synthetic revocation choice"},
    )
    assert revoked.status_code == 200, revoked.text
    assert client.get(path, params={"capability": feed["capability"]}).status_code == 404


@pytest.mark.parametrize(
    "role,foreign",
    [
        ("admin", False),
        ("gerente", False),
        ("lider", False),
        ("lider", True),
        ("colaborador", False),
    ],
)
def test_real_f10_signed_feeds_apply_current_server_scope_for_every_role(f10_api, role, foreign):
    from datetime import timedelta

    from test_identity import create_department, create_person, person_client

    client, _factory, task, _plan, objective, person, _terminal = f10_api
    department = create_department(client, "foreign_f10") if foreign else objective["department_id"]
    other = create_person(
        client, department=objective["department_id"], email="other-f10@example.invalid"
    )
    created = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": objective["id"],
            "assignee_id": other["id"],
            "title": "Synthetic other assignment",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert created.status_code == 201, created.text
    other_task = created.json()
    if role == "colaborador":
        email = person["email"]
    else:
        email = "viewer-f10@example.invalid"
        create_person(
            client, role=role, department=department if role == "lider" else None, email=email
        )
    with person_client(client, email) as viewer:
        expected = 200 if role == "admin" else 403
        for endpoint in (
            "notification-connectors",
            "notification-rules",
            "notifications/service-principals",
        ):
            assert viewer.get("/api/v1/" + endpoint).status_code == expected
        created_feed = viewer.post(
            "/api/v1/integrations/calendar-feeds",
            json={
                "name": "Synthetic role-scoped calendar",
                "expected_version": 0,
                "reason": "Explicit UUID-only current scope verification",
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
        assert created_feed.status_code == 201, created_feed.text
        feed = created_feed.json()
        response = viewer.get(
            "/api/v1/calendar-feeds/" + feed["id"] + "/content",
            params={"capability": feed["capability"]},
        )
        assert response.status_code == 200, response.text
        assert (task["id"] in response.text) is not foreign
        assert (other_task["id"] in response.text) is (not foreign and role != "colaborador")
        assert task["title"] not in response.text and other_task["title"] not in response.text
        assert (
            client.post(
                "/api/v1/integrations/calendar-feeds/" + feed["id"] + "/revoke",
                json={"expected_version": 1, "reason": "Synthetic non-owner revocation must fail"},
            ).status_code
            == 404
        )


def test_real_f10_outbox_dispatch_is_atomic_idempotent_and_respects_opt_in(f10_api):
    from uuid import UUID

    from sqlalchemy import func, select

    from app.models.notifications import Notification, NotificationDispatch
    from app.services.notification_worker import tick

    client, factory, _task, _plan, objective, person, _terminal = f10_api
    preference = client.patch(
        "/api/v1/notification-preferences",
        json={
            "expected_version": 0,
            "reason": "Synthetic explicit inbox consent",
            "channels": ["in_app"],
            "opt_in": True,
            "quiet_start": None,
            "quiet_end": None,
            "timezone": "America/Mexico_City",
        },
    )
    assert preference.status_code == 200, preference.text
    principal_id = uuid4()
    principal = client.put(
        "/api/v1/notifications/service-principals/" + str(principal_id),
        json=synthetic_command(
            name="Synthetic F10 runtime",
            department_ids=[objective["department_id"]],
            approved_scopes=["notifications:dispatch"],
            is_active=True,
        ),
    )
    assert principal.status_code == 200, principal.text
    rule = client.post(
        "/api/v1/notification-rules",
        json=synthetic_command(
            name="Synthetic assignment",
            department_id=objective["department_id"],
            trigger="assignment",
            recipient_mode="admins",
            channels=["in_app"],
            connector_ids=[],
            threshold_days=None,
            day_basis="natural",
            max_age_hours=24,
            max_attempts=3,
            retry_base_seconds=5,
            enabled=True,
        ),
    )
    assert rule.status_code == 201, rule.text
    created = client.post(
        "/api/v1/tasks",
        json={
            "objective_id": objective["id"],
            "assignee_id": person["id"],
            "title": "Synthetic notification trigger",
            "start_date": "2027-12-10",
            "due_date": "2028-02-20",
        },
    )
    assert created.status_code == 201, created.text
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())), app=client.app)
    assert tick(factory, principal_id, 10, request=request)["dispatched"] == 1
    assert tick(factory, principal_id, 10, request=request)["dispatched"] == 0
    response = client.get("/api/v1/notifications").json()
    assert response["unread_count"] == 1 and len(response["items"]) == 1
    notice = response["items"][0]
    read = client.post(
        "/api/v1/notifications/" + notice["id"] + "/read",
        json={"expected_version": notice["version"], "reason": "Synthetic inbox read confirmation"},
    )
    assert read.status_code == 200, read.text
    assert client.get("/api/v1/notifications").json()["unread_count"] == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert db.scalar(select(func.count()).select_from(NotificationDispatch)) == 1
        assert db.get(Notification, UUID(notice["id"])).read_at is not None
