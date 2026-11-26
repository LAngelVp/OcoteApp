import io

import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError
from test_f7 import platform_api as platform_api
from test_identity import api as api
from test_identity import tokens as tokens

from app.core.branding import contrast, recode_logo, validate_palette
from app.core.errors import CommandError
from app.schemas.enterprise import CalendarWrite, FlagWrite, PolicyValues


def policy_values(**changes):
    return {
        "password_min_length": 12,
        "require_upper": False,
        "require_lower": False,
        "require_digit": False,
        "require_symbol": False,
        "access_ttl_seconds": 600,
        "refresh_absolute_seconds": 604800,
        "idle_timeout_seconds": 3600,
        "failed_attempt_threshold": 10,
        "failed_window_seconds": 60,
        "lockout_seconds": 60,
        "page_sizes": [5, 10, 20, 50],
        "import_max_rows": 1000,
        "import_max_bytes": 10485760,
        "export_max_bytes": 16777216,
        **changes,
    }


def command(**changes):
    return {
        "current_password": " synthetic authorization ",
        "expected_version": 0,
        "reason": "Synthetic configuration only",
        **changes,
    }


def test_f8_reauthentication_denials_use_existing_audit_event_and_persist(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace
    from uuid import uuid4

    from pydantic import SecretStr

    from app.services import enterprise

    events = []
    actor = SimpleNamespace(
        id=uuid4(), password_hash="synthetic", version=1,
        failed_attempt_count=0, failed_window_at=None, locked_until=None,
    )
    database = SimpleNamespace(
        info={"f8_policy": SimpleNamespace(**policy_values())},
        refresh=lambda record, **options: None, add=events.append,
    )
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    body = SimpleNamespace(current_password=SecretStr("incorrect"))
    monkeypatch.setattr(enterprise, "verify_password", lambda hashed, password: False)
    for attempt in range(10):
        with pytest.raises(CommandError) as failure:
            enterprise.reauthenticate(database, actor, body, request)
        assert failure.value.status == 401 and failure.value.persist
        assert actor.failed_attempt_count == attempt + 1
        assert events[-1].after_data == {"code": "REAUTHENTICATION_REQUIRED"}
    with pytest.raises(CommandError) as failure:
        enterprise.reauthenticate(database, actor, body, request)
    assert failure.value.status == 429 and failure.value.persist
    assert events[-1].after_data == {"code": "REAUTHENTICATION_LOCKED"}
    assert len(events) == 11
    assert all(event.event_type == "security_denied" and event.outcome == "denied"
               and event.entity_id == actor.id for event in events)

    actor.locked_until = enterprise.now() - timedelta(seconds=1)
    flushed = []
    database.flush = lambda: flushed.append((
        actor.version, actor.failed_attempt_count, actor.failed_window_at, actor.locked_until,
    ))
    monkeypatch.setattr(enterprise, "verify_password", lambda hashed, password: True)
    version = actor.version
    enterprise.reauthenticate(database, actor, body, request)
    assert flushed == [(version + 1, 0, None, None)]
    enterprise.touch(actor)
    database.flush()
    assert [state[0] for state in flushed] == [version + 1, version + 2]


def test_f8_compromised_passwords_are_offline_and_case_insensitive():
    from types import SimpleNamespace

    from app.core.security import compromised_passwords
    from app.services.enterprise import validate_password

    assert len(compromised_passwords()) == 97747
    database = SimpleNamespace(info={"f8_policy": SimpleNamespace(**policy_values())})
    with pytest.raises(CommandError):
        validate_password(database, "Password123456")
    validate_password(database, "Synthetic-unique-F8-credential-573947!")


def test_f8_missing_or_modified_blocklist_fails_closed(monkeypatch, tmp_path):
    from app.core import security

    security.compromised_passwords.cache_clear()
    try:
        missing = tmp_path / "absent.txt"
        monkeypatch.setattr(security, "PASSWORD_BLOCKLIST", missing)
        with pytest.raises(CommandError):
            security.compromised_passwords()
        missing.write_text("untrusted", encoding="utf-8")
        with pytest.raises(CommandError):
            security.compromised_passwords()
    finally:
        security.compromised_passwords.cache_clear()


def test_f8_wcag_uses_srgb_linearization_and_does_not_round_to_pass():
    assert contrast("#000000", "#FFFFFF") == 21
    assert contrast("#FFFFFF", "#FFFFFF") == 1
    assert contrast("#777777", "#FFFFFF") < 4.5
    assert all(value >= 4.5 for value in validate_palette({}).values())
    for palette in (
        {"primary": "#FFFFFF"},
        {"focus": "#AAAAAA"},
        {"danger": "#000000"},
        {"primary": "red"},
        {"primary-dark": "#FFFFFF"},
    ):
        with pytest.raises(CommandError):
            validate_palette(palette)


@pytest.mark.parametrize(
    "name,value",
    [
        ("password_min_length", 11),
        ("password_min_length", 65),
        ("access_ttl_seconds", 601),
        ("refresh_absolute_seconds", 604801),
        ("idle_timeout_seconds", 0),
        ("failed_attempt_threshold", 2),
        ("failed_window_seconds", 901),
        ("lockout_seconds", 3601),
        ("page_sizes", [10]),
        ("page_sizes", [5, 5]),
        ("page_sizes", [5, 100]),
        ("import_max_rows", 1001),
        ("export_max_bytes", 16777217),
        ("password_min_length", True),
        ("require_upper", 1),
    ],
)
def test_f8_security_policy_rejects_out_of_registry_values(name, value):
    with pytest.raises(ValidationError):
        PolicyValues(**policy_values(**{name: value}))


def test_f8_flags_cannot_activate_future_code_or_disable_core_invariants():
    for code in ("comments", "dependencies", "custom_fields", "tags", "csrf", "audit", "score"):
        with pytest.raises(ValidationError):
            FlagWrite(**command(code=code, enabled=True))
    assert FlagWrite(**command(code="subtasks", enabled=False)).enabled is False


def test_f8_calendar_requires_explicit_scope_and_workdays():
    values = command(
        name="Synthetic calendar",
        scope_kind="organization",
        department_id=None,
        weekday_mask=31,
        inheritance="replace",
    )
    assert CalendarWrite(**values).weekday_mask == 31
    for changes in ({"weekday_mask": 0}, {"inheritance": "inherit"}, {"scope_kind": "department"}):
        with pytest.raises(ValidationError):
            CalendarWrite(**(values | changes))


def test_f8_logo_is_scanned_reencoded_and_metadata_removed():
    original = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("untrusted", "metadata must not survive")
    Image.new("RGB", (40, 20), "#2E5A44").save(original, format="PNG", pnginfo=metadata)
    scans = []

    def scanner(content):
        scans.append(content)
        return "ClamAV synthetic scanner fixture"

    content, media, width, height, version = recode_logo(original.getvalue(), "image/png", scanner)
    assert (media, width, height) == ("image/png", 40, 20)
    assert len(scans) == 2 and version.startswith("ClamAV ")
    with Image.open(io.BytesIO(content)) as image:
        assert "untrusted" not in image.info
    with pytest.raises(CommandError):
        recode_logo(original.getvalue(), "image/jpeg", scanner)
    with pytest.raises(CommandError):
        recode_logo(b"<svg/>", "image/svg+xml", scanner)


def test_f8_logo_scanner_failure_never_decodes_or_publishes():
    def unavailable(content):
        raise CommandError(503, "SYNTHETIC_SCANNER_UNAVAILABLE")

    with pytest.raises(CommandError) as error:
        recode_logo(b"synthetic", "image/png", unavailable)
    assert error.value.status == 503


def object_config(provider="s3", **changes):
    shared = {
        "provider": provider,
        "endpoint": "https://storage.example.invalid",
        "isolation_prefix": "synthetic-ocote",
        "connect_timeout_seconds": 1,
        "read_timeout_seconds": 2,
        "evidence_max_bytes": 1048576,
        "allowed_mime": ["image/png"],
        "retention_days": None,
        "private_access_attested": True,
        "approved_addresses": ["93.184.216.34"],
        "allow_private_endpoint": False,
    }
    return (
        shared
        | (
            {"bucket": "synthetic-bucket", "region": "us-east-1", "address_style": "path"}
            if provider == "s3"
            else {
                "container": "synthetic-container",
                "account_name": "syntheticaccount",
                "auth": "shared_key",
            }
        )
        | changes
    )


@pytest.mark.parametrize("provider", ["s3", "azure_blob"])
def test_f8_object_probe_is_signed_private_isolated_and_cleaned(provider):
    import base64

    from app.core.object_storage import ObjectClient

    objects, requests = {}, []

    def transport(config, host, port, method, target, headers, content, limit):
        requests.append((method, target, headers))
        assert host == "storage.example.invalid" and port == 443
        assert headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 " if provider == "s3" else "SharedKey "
        )
        if "policyStatus" in target:
            return (
                200,
                {},
                (
                    b'<PolicyStatus xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                    b"<IsPublic>false</IsPublic></PolicyStatus>"
                ),
            )
        if "acl=" in target or "comp=acl" in target:
            return (
                200,
                {},
                (b"<AccessControlPolicy/>" if provider == "s3" else b"<SignedIdentifiers/>"),
            )
        assert "/.ocote-probes/" in target and "/objects/" not in target
        if method == "PUT":
            objects[target] = content
            return 201, {}, b""
        if method == "DELETE":
            del objects[target]
            return 204, {}, b""
        return 200, {}, objects[target]

    credentials = (
        {"access_key": "synthetic-access", "secret_key": "synthetic-secret"}
        if provider == "s3"
        else {"account_key": base64.b64encode(b"s" * 32).decode()}
    )
    ObjectClient(object_config(provider), credentials, transport).probe()
    assert not objects and requests[-1][0] == "DELETE"


def test_f8_dns_rebinding_metadata_and_private_destinations_fail_closed():
    import socket

    from app.core.object_storage import checked_addresses

    def resolver(address):
        return lambda *arguments, **keywords: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        ]

    assert checked_addresses(
        "synthetic.invalid", 443, ["93.184.216.34"], False, resolver("93.184.216.34")
    ) == ["93.184.216.34"]
    for address, approved, private in (
        ("93.184.216.35", ["93.184.216.34"], False),
        ("169.254.169.254", ["169.254.169.254"], True),
        ("10.1.1.1", ["10.1.1.1"], False),
    ):
        with pytest.raises(CommandError):
            checked_addresses("synthetic.invalid", 443, approved, private, resolver(address))


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "http://127.0.0.1"},
        {"endpoint": "https://user:secret@storage.invalid"},
        {"endpoint": "https://storage.invalid/?token=secret"},
        {"isolation_prefix": "../escape"},
        {"approved_addresses": ["169.254.169.254"], "allow_private_endpoint": True},
        {"private_access_attested": False},
        {"read_timeout_seconds": 31},
    ],
)
def test_f8_object_configuration_rejects_unapproved_fetch_and_escape(changes):
    from app.schemas.enterprise import S3Config

    with pytest.raises((ValidationError, CommandError)):
        S3Config(**object_config(**changes))


def test_f8_object_public_bucket_never_receives_probe():
    from app.core.object_storage import ObjectClient

    requests = []

    def transport(*arguments):
        requests.append(arguments[3])
        return 200, {}, b"<PolicyStatus><IsPublic>true</IsPublic></PolicyStatus>"

    with pytest.raises(CommandError):
        ObjectClient(
            object_config(), {"access_key": "synthetic", "secret_key": "synthetic"}, transport
        ).probe()
    assert requests == ["GET"]


def test_f8_calendar_business_days_cross_year_without_rewriting_dates():
    from datetime import date

    from app.services.enterprise import working_offset

    start = date(2026, 12, 24)
    holidays = {date(2026, 12, 25), date(2027, 1, 1)}
    assert working_offset(start, 1, 31, holidays, "business") == date(2026, 12, 28)
    assert working_offset(start, 6, 31, holidays, "business") == date(2027, 1, 5)
    assert working_offset(start, 1, 31, holidays, "natural") == date(2026, 12, 25)
    assert start == date(2026, 12, 24)
    assert working_offset(date(2028, 2, 28), 1, 127, set(), "business") == date(2028, 2, 29)
    assert working_offset(date.max, 0, 31, set(), "business") == date.max
    for mode in ("natural", "business"):
        with pytest.raises(CommandError):
            working_offset(date.max, 1, 31, set(), mode)
    with pytest.raises(CommandError):
        working_offset(date(9999, 12, 30), 1, 1, set(), "business")


def test_f8_remote_evidence_requires_scan_before_network_and_checks_download_hash():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.object_integrations import RemoteEvidenceStore

    calls = []
    client = SimpleNamespace(
        config={"allowed_mime": ["image/png"]},
        private=lambda: calls.append("private"),
        write=lambda *args: calls.append("write"),
        remove=lambda *args: calls.append("remove"),
        read=lambda *args, **kwargs: b"tampered",
    )
    record = SimpleNamespace(id=uuid4(), config_revision=3)

    def unavailable_scan(content):
        raise CommandError(503, "SYNTHETIC_SCANNER_UNAVAILABLE")

    with pytest.raises(CommandError):
        RemoteEvidenceStore(client, unavailable_scan, record).publish(b"synthetic")
    assert calls == []
    store = RemoteEvidenceStore(client, lambda content: "ClamAV synthetic", record)
    key, digest, version = store.publish(b"synthetic")
    assert len(key) == 32 and calls == ["private", "write"] and version.startswith("ClamAV ")
    assert store.configuration_id == record.id and store.configuration_version == 3
    with pytest.raises(CommandError):
        store.available(key, 9, digest)


@pytest.mark.parametrize(
    "content",
    [
        b'{"PolicyStatus":{"IsPublic":false}}',
        b"<PolicyStatus><IsPublic>false</IsPublic><IsPublic>true</IsPublic></PolicyStatus>",
        b'<!DOCTYPE PolicyStatus [<!ENTITY flag "false">]>'
        b"<PolicyStatus><IsPublic>&flag;</IsPublic></PolicyStatus>",
        '<!DOCTYPE x [<!ENTITY a "false">]><x>&a;</x>'.encode("utf-16"),
    ],
)
def test_f8_s3_private_check_rejects_non_protocol_and_ambiguous_documents(content):
    from app.core.object_storage import ObjectClient

    def transport(*args):
        return 200, {}, content

    client = ObjectClient(
        object_config("s3"), {"access_key": "synthetic", "secret_key": "synthetic"}, transport
    )
    with pytest.raises(CommandError):
        client.private()


def test_f8_operator_handoff_has_separate_context_and_expires(tmp_path):
    import os

    from tools import f7_local, f8_local

    if os.name != "nt":
        pytest.skip("Windows DPAPI platform-specific test")
    path = tmp_path / "operator-f8" / "administrator.dpapi"
    password = " synthetic F8 administrative input "
    f8_local.save_authorization(password, path=path, issued_at=1000)
    assert password.encode() not in path.read_bytes()
    assert f8_local.authorized_password(path=path, current_time=1001) == password
    assert f7_local.OPERATOR_CONTEXT != f8_local.OPERATOR_CONTEXT
    with pytest.raises(CommandError):
        f7_local.authorized_password(path=path, current_time=1001)
    with pytest.raises(CommandError):
        f8_local.authorized_password(path=path, current_time=4600)
    with pytest.raises(CommandError):
        f8_local.save_authorization("replacement synthetic input", path=path, issued_at=1001)


def test_real_f8_additive_migration_and_permissions():
    import os

    if os.environ.get("OCOTE_RUN_PG_TESTS") != "1":
        pytest.skip("Explicit F8 local PG authorization required")
    from uuid import uuid4

    from sqlalchemy import text

    from tools.f2_local import isolated_database, migration_engine, upgrade

    added = {
        "security_policies",
        "feature_flags",
        "private_assets",
        "organization_profiles",
        "calendar_configs",
        "calendar_holidays",
    }
    with isolated_database() as name:
        assert name.startswith("ocote_f2_test_")
        upgrade(name, "20261125_0006")
        engine = migration_engine(name)
        try:
            with engine.begin() as connection:
                identity = uuid4()
                connection.execute(
                    text(
                        "INSERT INTO deployment_instances(id,root_key_ref) "
                        "VALUES(:id,'synthetic-f8-preserved-root')"
                    ),
                    {"id": identity},
                )
                original = connection.execute(text("SELECT * FROM deployment_instances")).one()
                before = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
            upgrade(name, "20261125_0007")
            upgrade(name, "20261125_0007")
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "20261125_0007"
                )
                assert (
                    connection.execute(text("SELECT * FROM deployment_instances")).one() == original
                )
                after = set(
                    connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                assert after - before == added and len(after) == 32
                for table in added:
                    assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
                    assert not connection.scalar(
                        text("SELECT has_table_privilege('ocote_runtime',:name,'DELETE,TRUNCATE')"),
                        {"name": table},
                    )
                assert not connection.scalar(
                    text("SELECT has_table_privilege('ocote_runtime','private_assets','UPDATE')")
                )
        finally:
            engine.dispose()


def test_real_f8_configuration_calendar_and_branding_transactions(platform_api):
    import base64

    from test_f7 import authenticate

    client, factory = platform_api
    authenticate(client)
    password = "Synthetic-password-123!"
    configuration = client.get("/api/v1/admin/configuration")
    assert configuration.status_code == 200, configuration.text
    assert configuration.json()["security_policy"]["version"] == 1
    body = command(
        current_password=password, expected_version=1, values=policy_values(access_ttl_seconds=300)
    )
    result = client.put("/api/v1/admin/security-policy", json=body)
    assert result.status_code == 200, result.text
    assert client.put("/api/v1/admin/security-policy", json=body).status_code == 409
    body = command(
        current_password=password,
        name="Synthetic F8 calendar",
        scope_kind="organization",
        department_id=None,
        weekday_mask=31,
        inheritance="replace",
    )
    calendar = client.post("/api/v1/admin/calendars", json=body)
    assert calendar.status_code == 201, calendar.text
    identity = calendar.json()["id"]
    holiday = client.post(
        "/api/v1/admin/calendars/" + identity + "/holidays",
        json=command(
            current_password=password,
            holiday_date="2026-12-25",
            name="Synthetic holiday",
            is_active=True,
        ),
    )
    assert holiday.status_code == 201, holiday.text
    preview = client.post(
        "/api/v1/admin/calendar-preview",
        json={"department_id": None, "start_date": "2026-12-24", "days": 1, "mode": "business"},
    )
    assert preview.status_code == 200, preview.text
    assert "2026-12-28" in preview.text
    client.app.state.logo_scanner = lambda content: "ClamAV synthetic F8 test"
    output = io.BytesIO()
    Image.new("RGB", (40, 20), "green").save(output, format="PNG")
    logo = client.post(
        "/api/v1/admin/branding/logo",
        json=command(
            current_password=password,
            media_type="image/png",
            content=base64.b64encode(output.getvalue()).decode(),
        ),
    )
    assert logo.status_code == 201, logo.text
    branding = client.put(
        "/api/v1/admin/branding",
        json=command(
            current_password=password,
            organization_name="Synthetic F8 identity",
            organization_name_version=0,
            welcome_text="Synthetic welcome",
            footer_text="Synthetic footer",
            token_overrides={},
            logo_asset_id=logo.json()["id"],
        ),
    )
    assert branding.status_code == 200, branding.text
    downloaded = client.get("/api/v1/branding/logo/" + logo.json()["id"])
    assert downloaded.status_code == 200 and downloaded.headers["content-type"] == "image/png"
    assert downloaded.headers["cache-control"] == "no-store"
    rejected = client.put(
        "/api/v1/admin/branding",
        json=command(
            current_password=password,
            expected_version=1,
            organization_name_version=1,
            organization_name="Synthetic F8 identity",
            welcome_text="",
            footer_text="",
            token_overrides={"primary": "#FFFFFF"},
            logo_asset_id=None,
        ),
    )
    assert rejected.status_code == 422
    denied = command(
        current_password="Incorrect-synthetic-password!", expected_version=1, values=policy_values()
    )
    for _ in range(10):
        assert client.put("/api/v1/admin/security-policy", json=denied).status_code == 401
    denied["current_password"] = password
    assert client.put("/api/v1/admin/security-policy", json=denied).status_code == 429
    with factory() as db:
        from sqlalchemy import text

        assert db.scalar(text("SELECT count(*) FROM configuration_revisions")) >= 15


def test_real_f8_object_credentials_write_only_probe_and_activation(platform_api):
    from test_f7 import authenticate

    client, _ = platform_api
    authenticate(client)
    password = "Synthetic-password-123!"
    objects = {}

    def transport(config, host, port, method, target, headers, content, limit):
        assert headers["authorization"].startswith("AWS4-HMAC-SHA256 ")
        if "policyStatus" in target:
            return 200, {}, b"<PolicyStatus><IsPublic>false</IsPublic></PolicyStatus>"
        if "acl" in target:
            return 200, {}, b"<AccessControlPolicy><AccessControlList/></AccessControlPolicy>"
        assert "/.ocote-probes/" in target
        if method == "PUT":
            objects[target] = content
            return 200, {}, b""
        if method == "GET":
            return 200, {}, objects[target]
        objects.pop(target)
        return 204, {}, b""

    client.app.state.object_transport = transport
    client.app.state.logo_scanner = lambda content: "ClamAV synthetic F8 test"
    created = client.post(
        "/api/v1/admin/object-storage",
        json=command(
            current_password=password,
            name="Synthetic S3 private",
            scope_kind="organization",
            department_id=None,
            config=object_config("s3"),
            credentials={
                "access_key": "SYNTHETICACCESSKEY",
                "secret_key": "SyntheticStorageSecretNeverReturned123!",
                "session_token": None,
            },
        ),
    )
    assert created.status_code == 201, created.text
    assert "SyntheticStorageSecret" not in created.text and "ciphertext" not in created.text
    identity = created.json()["id"]
    activated = client.post(
        "/api/v1/admin/object-storage/" + identity + "/activation",
        json=command(current_password=password, expected_version=1, is_active=True),
    )
    assert activated.status_code == 409
    tested = client.post(
        "/api/v1/admin/object-storage/" + identity + "/test",
        json=command(current_password=password, expected_version=1),
    )
    assert tested.status_code == 200 and tested.json()["passed"], tested.text
    assert objects == {} and tested.json()["is_active"] is False
    activated = client.post(
        "/api/v1/admin/object-storage/" + identity + "/activation",
        json=command(
            current_password=password, expected_version=tested.json()["version"], is_active=True
        ),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True
