import importlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings
from app.core.errors import CommandError
from app.schemas.installation import Connection, Install, secret_values

pytestmark = pytest.mark.skipif(
    os.environ.get("OCOTE_RUN_PG_TESTS") != "1",
    reason="Fresh explicit F7 delivery UUID authorization required",
)


def packaged_rehearsal():
    import psycopg

    from app.core.vault import OSSealedFile
    from app.services.installation import HEAD, Setup, connection_options, role_options
    from app.services.platform import seal_path
    from tools import delivery_support as support
    from tools.delivery import ROOT, sha, verify_directory
    from tools.delivery_upgrade import upgrade

    importlib.import_module("app.main")
    payload = json.load(sys.stdin)
    setup = None
    stage = "package-integrity"
    status = 1
    try:
        assert "PGPASSWORD" not in os.environ
        verify_directory(ROOT)
        state, evidence = Path(payload["state"]), Path(payload["evidence"])
        for field in ("database", "restore_database"):
            assert re.fullmatch(r"ocote_f2_(test|restore)_[0-9a-f]{32}", payload[field])
        body = Connection(**payload["connection"]).model_copy(
            update={"database": payload["database"]}
        )
        stage = "first-run-pairing"
        setup = Setup(state, "https://localhost:8443")
        initial = setup.code
        paired = setup.pair()["session_code"]
        with pytest.raises(CommandError, match="SETUP_CAPABILITY_INVALID"):
            setup.authorize(initial, setup.origin)
        setup.authorize(paired, setup.origin, require_pair=True)
        stage = "connection-tests"
        tested = setup.test(body)
        request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
        command = Install(
            connection=body,
            test_id=tested["test_id"],
            organization_timezone="America/Mexico_City",
            admin={
                "email": "synthetic-install@example.invalid",
                "role": "admin",
                "display_name": "Synthetic UUID installation",
                "password": "Synthetic-install-password-2026!",
                "reason": "Explicit UUID-only first administrator",
            },
        )
        stage = "schema-admin-seal"
        setup.install(command, request)
        assert setup.closed and setup.code == ""
        with pytest.raises(CommandError, match="SETUP_SEALED"):
            setup.authorize(paired, setup.origin)
        with pytest.raises(CommandError, match="SETUP_SEALED"):
            setup.install(command, request)
        with pytest.raises(CommandError, match="SETUP_EXISTING_STATE"):
            Setup(state, setup.origin)
        bootstrap = json.loads(OSSealedFile(state / "bootstrap.dpapi", setup.identity).read())
        assert "migrator_password" not in bootstrap["connection"]
        root_hash = sha(seal_path(setup.identity).read_bytes())
        bootstrap_hash = sha((state / "bootstrap.dpapi").read_bytes())
        with connection_options(body) as options:
            with psycopg.connect(
                **role_options(options, body, "ocote_migrador"), autocommit=True
            ) as db:
                before = support.snapshot(db)
                assert len(before["tables"]) == 72
                assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(HEAD,)]
                assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        stage = "encrypted-upgrade-and-restore"
        outcome = upgrade(
            body,
            artifact=Path(payload["artifact"]),
            trusted_sha256=payload["artifact_sha256"],
            restore_database=payload["restore_database"],
            pg_bin=Path(payload["pg_bin"]),
            evidence=evidence,
            maintenance=Path(payload["maintenance"]),
            operator="Synthetic UUID-only operator",
        )
        assert outcome["maintenance_retained"]
        receipt = json.loads((evidence / "before-manifest.json").read_text())
        assert receipt["restore_input"] == "authenticated-decryption-of-encrypted-backup"
        assert (evidence / "before.dump.enc").is_file()
        assert not list(evidence.glob("*.dump"))
        assert root_hash == sha(seal_path(setup.identity).read_bytes())
        assert bootstrap_hash == sha((state / "bootstrap.dpapi").read_bytes())
        with connection_options(body) as options:
            with psycopg.connect(
                **role_options(options, body, "ocote_migrador"), autocommit=True
            ) as db:
                support.preserved(before, support.snapshot(db), ledger=True)
                assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        print(
            json.dumps(
                {
                    "stage": "complete",
                    "installed_head": HEAD,
                    "no_op_verified": True,
                    "sealed_irreversibly": True,
                    "post_seal_blocked": True,
                    "package_backend_executed": True,
                    "encrypted_backup_restored": True,
                    "root_bootstrap_preserved": True,
                    "history_preserved": True,
                    "no_admin_environment": True,
                }
            ),
            flush=True,
        )
        status = 0
    except (Exception, pytest.fail.Exception) as error:
        diagnostic = getattr(error, "diag", None)
        details = {
            "stage": stage,
            "error_type": type(error).__name__,
            "code": getattr(error, "code", None),
            "sqlstate": getattr(error, "sqlstate", None),
        }
        for field in ("constraint_name", "table_name", "column_name"):
            value = getattr(diagnostic, field, None)
            details[field] = (
                value
                if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*", value)
                else None
            )
        print(json.dumps(details), flush=True)
    finally:
        if setup is not None:
            path = seal_path(setup.identity)
            path.unlink(missing_ok=True)
            if path.parent.exists():
                path.parent.rmdir()
    return status


def test_clean_setup_and_preserving_upgrade_uuid_only(tmp_path):
    from tools import f1_local as local
    from tools.delivery import sha, verify, verify_directory
    from tools.delivery_cut2 import validate_approval
    from tools.f2_local import isolated_database

    selected = os.environ.get("OCOTE_DELIVERY_APPROVAL")
    if not selected:
        pytest.skip("The F7 driver must supply its own approved distribution")
    approval_path = Path(selected)
    validate_approval(approval_path)
    approval = json.loads(approval_path.read_text())
    artifact = approval_path.parent / "ocote-windows-cut1.zip"
    assert sha(artifact.read_bytes()) == approval["package"]["sha256"]
    verify(artifact)
    unpacked = tmp_path / "distribution"
    unpacked.mkdir()
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(unpacked)
    verify_directory(unpacked)
    runtime = make_url(Settings().database_url.get_secret_value())
    migration = make_url(MigrationSettings().migration_database_url.get_secret_value())
    body = Connection(
        mode="local",
        host="127.0.0.1",
        approved_address="127.0.0.1",
        port=5432,
        database="ocoteAppDatabase",
        runtime_role="ocote_runtime",
        migrator_role="ocote_migrador",
        runtime_password=runtime.password,
        migrator_password=migration.password,
        sslmode="disable",
    )
    with isolated_database() as name, isolated_database("restore") as restored:
        with local.admin_connection(name) as administrator:
            administrator.execute("ALTER SCHEMA public OWNER TO ocote_migrador")
            administrator.execute("GRANT USAGE ON SCHEMA public TO ocote_runtime")
            administrator.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            administrator.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        payload = {
            "connection": secret_values(body),
            "database": name,
            "restore_database": restored,
            "state": str(tmp_path / "setup"),
            "evidence": str(tmp_path / "upgrade"),
            "maintenance": str(tmp_path / "maintenance"),
            "artifact": str(artifact),
            "artifact_sha256": approval["package"]["sha256"],
            "pg_bin": str(local.PG_BIN),
        }
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PG")
            and key
            not in {
                "DATABASE_URL",
                "MIGRATION_DATABASE_URL",
            }
        }
        environment["PYTHONPATH"] = str(unpacked / "backend")
        result = subprocess.run(
            [sys.executable, "-u", str(Path(__file__).resolve())],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=unpacked / "backend",
            env=environment,
            timeout=600,
        )
        reports = [
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        assert result.returncode == 0, reports or {"stage": "child-import-or-startup-failed"}
        assert reports[-1]["stage"] == "complete"


if __name__ == "__main__":
    raise SystemExit(packaged_rehearsal())
