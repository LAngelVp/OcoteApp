import argparse
import importlib.util
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.services.installation import canonical, private_directory, write_private
from tools.delivery import ROOT, sha
from tools.delivery_sbom import python_inventory

LEVELS = {
    "LOW": "low",
    "MODERATE": "moderate",
    "MEDIUM": "moderate",
    "HIGH": "high",
    "CRITICAL": "critical",
}


def severity(advisory):
    value = (advisory.get("database_specific") or {}).get("severity")
    if isinstance(value, str) and value.upper() in LEVELS:
        return LEVELS[value.upper()]
    for metric in advisory.get("severity", []):
        try:
            score = float(metric.get("score", ""))
        except (ValueError, TypeError):
            continue
        return (
            "critical"
            if score >= 9
            else "high"
            if score >= 7
            else "moderate"
            if score >= 4
            else "low"
        )
    return "unknown"


def advisory_groups(advisories):
    groups = []
    rank = {name: index for index, name in enumerate(("low", "moderate", "high", "critical"))}
    for advisory in advisories:
        identities = {advisory["id"], *(advisory.get("aliases") or [])}
        matching = [group for group in groups if group["identities"] & identities]
        records = [advisory]
        for group in matching:
            identities.update(group["identities"])
            records.extend(group["records"])
            groups.remove(group)
        groups.append({"identities": identities, "records": records})
    result = []
    for group in groups:
        known = [severity(record) for record in group["records"] if severity(record) != "unknown"]
        result.append(
            {
                "aliases": sorted(group["identities"]),
                "severity": max(known, key=rank.get) if known else "unknown",
            }
        )
    return sorted(result, key=lambda group: group["aliases"])


def python_audit(client, components, directory):
    queries = [
        {"package": {"name": entry["name"], "ecosystem": "PyPI"}, "version": entry["version"]}
        for entry in components
    ]
    response = client.post("https://api.osv.dev/v1/querybatch", json={"queries": queries})
    response.raise_for_status()
    batch = response.json()
    write_private(directory / "python-osv-querybatch.json", canonical(batch))
    results = batch.get("results", [])
    if len(results) != len(components):
        raise ValueError("Incomplete OSV inventory response")
    identifiers = sorted({item["id"] for result in results for item in result.get("vulns", [])})

    def fetch(identifier):
        item = client.get("https://api.osv.dev/v1/vulns/" + identifier)
        item.raise_for_status()
        return identifier, item.json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        advisories = dict(executor.map(fetch, identifiers))
    write_private(directory / "python-osv-advisories.json", canonical(advisories))
    counts = dict.fromkeys(("critical", "high", "moderate", "low", "unknown"), 0)
    findings = []
    rank = {
        name: index for index, name in enumerate(("low", "moderate", "high", "critical", "unknown"))
    }
    for component, result in zip(components, results, strict=True):
        affected = [
            advisories[item["id"]]
            for item in result.get("vulns", [])
            if not advisories[item["id"]].get("withdrawn")
        ]
        if not affected:
            continue
        groups = advisory_groups(affected)
        level = max((item["severity"] for item in groups), key=rank.get)
        counts[level] += 1
        fixes = sorted(
            {
                event["fixed"]
                for item in affected
                for entry in item.get("affected", [])
                if entry.get("package", {}).get("name", "").lower() == component["name"]
                for interval in entry.get("ranges", [])
                for event in interval.get("events", [])
                if "fixed" in event
            }
        )
        findings.append(
            {
                "name": component["name"],
                "version": component["version"],
                "severity": level,
                "advisories": sorted(item["id"] for item in affected),
                "unique_advisory_groups": groups,
                "reported_fixed_versions_not_resolved": fixes,
            }
        )
        unique = advisory_groups(
            [item for item in advisories.values() if not item.get("withdrawn")]
        )
        advisory_counts = {
            level: sum(item["severity"] == level for item in unique) for level in counts
        }
    return {
        "status": "complete",
        "source": "OSV querybatch plus advisory details",
        "inventory_components": len(components),
        "affected_components_by_max_severity": counts,
        "advisory_records": len(advisories),
        "unique_advisories": len(unique),
        "unique_advisories_by_severity": advisory_counts,
        "findings": findings,
    }


def audit(directory):
    directory = Path(directory).absolute()
    if directory.exists():
        raise ValueError("Audit output requires a fresh evidence directory")
    private_directory(directory)
    python_lock, npm_lock = ROOT / "backend/requirements.lock", ROOT / "package-lock.json"
    before = {"python": sha(python_lock.read_bytes()), "npm": sha(npm_lock.read_bytes())}
    node = Path(shutil.which("node") or "")
    npm = node.parent / "node_modules/npm/bin/npm-cli.js"
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "lock_hashes": before,
        "historical_npm_moderate": 21,
        "exceptions_deadline": "2026-12-24",
        "exceptions_renewed": False,
        "lockfiles_changed": False,
        "pip_audit_preinstalled": importlib.util.find_spec("pip_audit") is not None,
    }
    try:
        result = subprocess.run(
            [
                str(node),
                str(npm),
                "audit",
                "--json",
                "--package-lock-only",
                "--ignore-scripts",
                "--fetch-retries=0",
                "--fetch-timeout=20000",
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=90,
        )
        write_private(directory / "npm-audit.json", result.stdout)
        document = json.loads(result.stdout)
        if document.get("error") or "vulnerabilities" not in document.get("metadata", {}):
            raise ValueError("npm advisory response incomplete")
        report["npm"] = {
            "status": "complete",
            "exit_code": result.returncode,
            "counts": document["metadata"]["vulnerabilities"],
            "findings": [
                {
                    "name": name,
                    "severity": entry["severity"],
                    "direct": entry.get("isDirect"),
                    "fix_available": entry.get("fixAvailable"),
                    "range": entry.get("range"),
                }
                for name, entry in sorted(document.get("vulnerabilities", {}).items())
            ],
        }
    except Exception as error:
        report["npm"] = {"status": "incomplete", "error_type": type(error).__name__}
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            report["python"] = python_audit(client, python_inventory(python_lock), directory)
    except Exception as error:
        report["python"] = {"status": "incomplete", "error_type": type(error).__name__}
    if before != {"python": sha(python_lock.read_bytes()), "npm": sha(npm_lock.read_bytes())}:
        raise ValueError("An audit must not modify locked dependencies")
    report["remediation_requires_separate_lock_authorization"] = True
    write_private(directory / "audit-summary.json", canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only npm/locked-Python advisory audit")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = audit(arguments.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(
        0 if all(result[name]["status"] == "complete" for name in ("npm", "python")) else 2
    )
