import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from app.services.installation import HEAD, canonical


def python_inventory(lock):
    result = []
    content = re.sub(r"\\\r?\n\s*", " ", Path(lock).read_text(encoding="utf-8"))
    for line in content.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        hashes = sorted(set(re.findall(r"--hash=sha256:([a-f0-9]{64})", value)))
        requirement = Requirement(re.sub(r"\s+--hash=sha256:[a-f0-9]{64}", "", value))
        pins = list(requirement.specifier)
        if (
            len(pins) != 1
            or pins[0].operator != "=="
            or "*" in pins[0].version
            or not hashes
            or requirement.url
        ):
            raise ValueError("Every Python component requires an exact hash-locked version")
        name, version = canonicalize_name(requirement.name), pins[0].version
        purl = "pkg:pypi/" + quote(name, safe="") + "@" + quote(version, safe="")
        properties = [{"name": "ocote:inventory", "value": "runtime-and-build-lock"}]
        if requirement.marker:
            properties.append({"name": "ocote:marker", "value": str(requirement.marker)})
        if requirement.extras:
            properties.append(
                {"name": "ocote:extras", "value": ",".join(sorted(requirement.extras))}
            )
        result.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "bom-ref": purl,
                "purl": purl,
                "hashes": [{"alg": "SHA-256", "content": digest} for digest in hashes],
                "properties": properties,
            }
        )
    return result


def npm_inventory(lock):
    document = json.loads(Path(lock).read_text(encoding="utf-8"))
    if document.get("lockfileVersion") != 3 or not isinstance(document.get("packages"), dict):
        raise ValueError("A version3 npm package lock is required")
    components = {}
    algorithms = {"sha1": "SHA-1", "sha256": "SHA-256", "sha384": "SHA-384", "sha512": "SHA-512"}
    for location, package in sorted(document["packages"].items()):
        if not location:
            continue
        name = package.get("name") or location.rsplit("node_modules/", 1)[-1]
        version = package.get("version")
        if not isinstance(version, str) or not version or package.get("link"):
            raise ValueError("Unresolved npm component in locked inventory")
        namespace, _, bare = name.rpartition("/")
        encoded = (quote(namespace, safe="") + "/" if namespace else "") + quote(bare, safe="")
        purl = "pkg:npm/" + encoded + "@" + quote(version, safe="")
        hashes = []
        for token in package.get("integrity", "").split():
            algorithm, separator, encoded_hash = token.partition("-")
            if not separator or algorithm not in algorithms:
                raise ValueError("Unsupported npm integrity algorithm")
            digest = base64.b64decode(encoded_hash.split("?", 1)[0], validate=True).hex()
            hashes.append({"alg": algorithms[algorithm], "content": digest})
        component = components.setdefault(
            purl,
            {
                "type": "library",
                "name": bare,
                "version": version,
                "bom-ref": purl,
                "purl": purl,
                "hashes": [],
                "properties": [],
            },
        )
        if namespace:
            component["group"] = namespace
        component["hashes"] = sorted(
            {canonical(entry): entry for entry in component["hashes"] + hashes}.values(),
            key=lambda entry: (entry["alg"], entry["content"]),
        )
        component["properties"].append({"name": "ocote:npm-location", "value": location})
        if package.get("dev"):
            component["properties"].append({"name": "ocote:build-dependency", "value": "true"})
    for component in components.values():
        component["properties"] = sorted(
            {canonical(entry): entry for entry in component["properties"]}.values(),
            key=lambda entry: (entry["name"], entry["value"]),
        )
    return list(components.values())


def generate(root):
    root = Path(root)
    python_lock, npm_lock = root / "backend/requirements.lock", root / "package-lock.json"
    result = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "OCOTE", "version": HEAD},
            "properties": [
                {
                    "name": "ocote:inventory-scope",
                    "value": "all-locked-runtime-and-build-dependencies",
                },
                {
                    "name": "ocote:python-lock-sha256",
                    "value": hashlib.sha256(python_lock.read_bytes()).hexdigest(),
                },
                {
                    "name": "ocote:npm-lock-sha256",
                    "value": hashlib.sha256(npm_lock.read_bytes()).hexdigest(),
                },
            ],
        },
        "components": sorted(
            python_inventory(python_lock) + npm_inventory(npm_lock),
            key=lambda component: component["bom-ref"],
        ),
    }
    validate(result)
    return result


def validate(sbom):
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.6"
        or sbom.get("version") != 1
        or not sbom.get("components")
    ):
        raise ValueError("Invalid CycloneDX inventory")
    references = set()
    lengths = {"SHA-1": 40, "SHA-256": 64, "SHA-384": 96, "SHA-512": 128}
    for component in sbom["components"]:
        reference = component["bom-ref"]
        if (
            reference in references
            or reference != component["purl"]
            or not component["name"]
            or not component["version"]
            or component["type"] != "library"
        ):
            raise ValueError("Invalid or duplicated SBOM component")
        references.add(reference)
        for digest in component.get("hashes", []):
            if not re.fullmatch(
                "[a-f0-9]{" + str(lengths.get(digest["alg"], 0)) + "}", digest["content"]
            ):
                raise ValueError("Invalid SBOM component digest")
