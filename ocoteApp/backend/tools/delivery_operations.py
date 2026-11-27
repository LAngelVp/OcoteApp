import hmac
import json
import os
import ssl
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from app.core.evidence import private_root
from app.core.vault import OSSealedFile
from app.schemas.installation import https_origin
from app.services.installation import HEAD, canonical, write_private
from app.services.platform import seal_path
from tools.delivery import sha
from tools.delivery_runtime import read_bootstrap
from tools.delivery_security import verify_signature


def reopen(
    *,
    state,
    receipt,
    maintenance,
    expected_instance,
    origin,
    ca_file,
    artifact,
    signature,
    public_key,
    operator,
    client_factory=httpx.Client,
):
    identity = str(UUID(str(expected_instance)))
    origin = https_origin(origin)
    if not operator.strip() or len(operator) > 160:
        raise ValueError("An explicit reopening operator is required")
    state, receipt, maintenance = Path(state), Path(receipt), Path(maintenance)
    if maintenance.resolve() != (state / "maintenance.json").resolve():
        raise ValueError("Maintenance must belong to the sealed runtime state")
    private_root(state)
    private_root(receipt.parent)
    private_root(maintenance.parent)
    if any(path.is_symlink() or path.is_junction() for path in (state, receipt, maintenance)):
        raise ValueError("Linked operating state is forbidden")
    trusted = verify_signature(artifact, signature, public_key)
    bootstrap = read_bootstrap(state)
    if bootstrap["instance"] != identity or bootstrap["auth_origin"] != origin:
        raise ValueError("Reopening instance or origin differs from sealed bootstrap")
    root = OSSealedFile(seal_path(UUID(identity)), UUID(identity)).read()
    completed = json.loads(receipt.read_text())
    mac = completed.pop("receipt_mac")
    if not hmac.compare_digest(mac, hmac.digest(root, canonical(completed), "sha256").hex()):
        raise ValueError("Upgrade receipt authentication failed")
    marker = maintenance.read_bytes()
    marker_data = json.loads(marker)
    backup = completed["backup"]
    if (
        completed.get("state") != "verified_pending_reopening"
        or completed.get("head") != HEAD
        or completed.get("instance") != identity
        or not backup.get("verified_at")
        or backup.get("head") != HEAD
        or backup.get("restore_input") != "authenticated-decryption-of-encrypted-backup"
        or completed.get("artifact_sha256") != trusted["zip_sha256"]
        or completed.get("manifest_sha256") != trusted["manifest_sha256"]
        or completed.get("maintenance_sha256") != sha(marker)
        or any(
            marker_data.get(name) != completed.get(name)
            for name in ("head", "instance", "release", "request_id")
        )
    ):
        raise ValueError("Upgrade is not verified for this maintenance state")
    tls = ssl.create_default_context(cafile=str(ca_file))
    if not tls.check_hostname or tls.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("Strict TLS verification required")
    with client_factory(
        base_url=origin, verify=tls, trust_env=False, follow_redirects=False, timeout=10
    ) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get(
            "/api/v1/health/ready",
            headers={
                "X-Health-Token": bootstrap["health_token"],
            },
        )
    if (
        live.status_code != 200
        or ready.status_code != 200
        or live.json() != {"status": "alive"}
        or ready.json() != {"status": "ready"}
        or ready.headers.get("X-OCOTE-Instance") != identity
        or ready.headers.get("X-OCOTE-Head") != HEAD
        or ready.headers.get("X-OCOTE-Manifest") != trusted["manifest_sha256"]
    ):
        raise ValueError("Expected runtime is not healthy; maintenance retained")
    if (
        maintenance.read_bytes() != marker
        or json.loads(receipt.read_text()).get("receipt_mac") != mac
    ):
        raise ValueError("Operating state changed during health verification")
    report = {
        "state": "reopened",
        "reopened_at": datetime.now(UTC).isoformat(),
        "request_id": str(uuid4()),
        "instance": identity,
        "release": completed["release"],
        "upgrade_request_id": completed["request_id"],
        "operator": operator,
        "head": HEAD,
        "origin": origin,
        "artifact_sha256": trusted["zip_sha256"],
        "maintenance_sha256": sha(marker),
        "health": {"live": 200, "ready": 200},
        "tls": "CERT_REQUIRED/hostname",
        "sql_connections_opened": 0,
    }
    archived = receipt.parent / "reopened-maintenance.json"
    final = receipt.parent / "reopen.json"
    if archived.exists() or final.exists():
        raise ValueError("Reopening receipt already exists")
    write_private(
        receipt.parent / "reopen-intent.json", canonical(report | {"state": "authorized"})
    )
    os.rename(maintenance, archived)
    try:
        write_private(final, canonical(report))
    except Exception:
        os.rename(archived, maintenance)
        raise
    return report
