import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from app.services.installation import HEAD, canonical

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {
    ".venv",
    ".env",
    ".local",
    "node_modules",
    "__pycache__",
    "tests",
    "logs",
    "backups",
    "database",
    ".git",
    ".angular",
    "test-results",
    "coverage",
}
EXAMPLE = b"# Generated secrets and SQL credentials belong in the OS-sealed bootstrap.\n"
EXAMPLE += b"# Start the setup entrypoint with an explicit private state and HTTPS origin.\n"
EXAMPLE += b"# No developer database, fallback credential or business defaults are distributed.\n"


def allowed(name):
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and "\\" not in name
        and ":" not in name
        and all(part not in {"", ".", ".."} for part in name.split("/"))
        and not any(part.lower() in FORBIDDEN for part in path.parts)
        and path.suffix.lower() not in {".log", ".dump", ".dpapi", ".pem", ".key", ".pyc"}
        and not any(
            part.lower().startswith(".env") and part != ".env.example" for part in path.parts
        )
    )


def sha(content):
    return hashlib.sha256(content).hexdigest()


def inventory(root, build):
    root, build = Path(root), Path(build)
    receipt = json.loads((build.parent / "architect-result.json").read_text())
    if receipt.get("success") is not True or receipt.get("configuration") != "production":
        raise ValueError("An official successful production Architect result is required")
    actual = {
        source.relative_to(build).as_posix(): sha(source.read_bytes())
        for source in build.rglob("*")
        if source.is_file()
    }
    if receipt.get("files") != actual:
        raise ValueError("Frontend output differs from the successful Architect receipt")
    values = {}

    def add(source, destination):
        if source.is_symlink() or source.is_junction() or not allowed(destination):
            raise ValueError("Unsafe package input")
        if destination in values:
            raise ValueError("Duplicate package input")
        values[destination] = source.read_bytes()

    for folder in ("backend/app", "backend/alembic", "backend/tools", "docs"):
        for source in sorted((root / folder).rglob("*")):
            relative = source.relative_to(root).as_posix()
            if folder == "backend/tools" and source.name not in {
                "delivery.py",
                "delivery_runtime.py",
                "delivery_upgrade.py",
            }:
                continue
            if source.is_file() and source.suffix in {".py", ".mako", ".txt", ".md"}:
                if "__pycache__" not in source.parts:
                    add(source, relative)
    for name in (
        "backend/alembic.ini",
        "backend/pyproject.toml",
        "backend/requirements.lock",
        "backend/README.md",
        "README.md",
    ):
        add(root / name, name)
    if not (build / "index.html").is_file():
        raise ValueError("Missing production frontend")
    for source in sorted(build.rglob("*")):
        if source.is_file():
            add(source, "frontend/" + source.relative_to(build).as_posix())
    add(build.parent / "3rdpartylicenses.txt", "frontend/3rdpartylicenses.txt")
    from tools.delivery_support import build_support

    values["backend/tools/delivery_support.py"] = build_support(root)
    values[".env.example"] = EXAMPLE
    values["frontend/architect-result.json"] = canonical(receipt)
    for name, body in {
        "install.cmd": "@echo off\r\ncd /d %~dp0backend\r\npython -m tools.delivery setup %*\r\n",
        "start.cmd": "@echo off\r\ncd /d %~dp0backend\r\npython -m tools.delivery runtime %*\r\n",
        "update.cmd": "@echo off\r\ncd /d %~dp0backend\r\npython -m tools.delivery upgrade %*\r\n",
        "dependencies.cmd": (
            "@echo off\r\ncd /d %~dp0backend\r\n"
            "python -m pip install --require-hashes -r requirements.lock\r\n"
        ),
    }.items():
        values[name] = body.encode("ascii")
    return values


def package(root, build, destination):
    values = inventory(root, build)
    manifest = {
        "format": 1,
        "application": "OCOTE",
        "target": "windows-x64",
        "python": "3.12",
        "postgresql_major": 18,
        "head": HEAD,
        "compatible_source_revisions": [HEAD],
        "new_installation": True,
        "files": {
            name: {"sha256": sha(content), "bytes": len(content)}
            for name, content in sorted(values.items())
        },
    }
    values["manifest.json"] = canonical(manifest)
    with (
        Path(destination).open("xb") as output,
        zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive,
    ):
        for name, content in sorted(values.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, content, compresslevel=9)
    verify(destination)
    return manifest


def verify(artifact):
    with zipfile.ZipFile(artifact) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(names) != len(set(name.casefold() for name in names))
            or "manifest.json" not in names
            or any(not allowed(name) for name in names)
            or sum(entry.file_size for entry in entries) > 268435456
            or any(
                stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1 for entry in entries
            )
        ):
            raise ValueError("Unsafe package structure")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("head") != HEAD or manifest.get("format") != 1:
            raise ValueError("Unsupported artifact")
        if set(names) != set(manifest["files"]) | {"manifest.json"}:
            raise ValueError("Manifest does not cover the complete package")
        for name, entry in manifest["files"].items():
            content = archive.read(name)
            if len(content) != entry["bytes"] or sha(content) != entry["sha256"]:
                raise ValueError("Package integrity failure")
        migrations = [name for name in names if name.startswith("backend/alembic/versions/")]
        if len(migrations) != 11 or not any("0011_" in name for name in migrations):
            raise ValueError("The complete immutable migration chain is required")
        return manifest


def verify_directory(root):
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("head") != HEAD:
        raise ValueError("Unsupported extracted distribution")
    for name, metadata in manifest["files"].items():
        candidate = root / name
        if (
            not allowed(name)
            or candidate.is_symlink()
            or not candidate.resolve().is_relative_to(root.resolve())
            or sha(candidate.read_bytes()) != metadata["sha256"]
        ):
            raise ValueError("Extracted distribution integrity failure")


def start_server(arguments):
    import uvicorn
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    from app.core.evidence import private_root
    from tools.delivery_runtime import runtime_app

    if "PGPASSWORD" in os.environ:
        raise ValueError("Runtime/bootstrap must not inherit administrative credentials")
    if not arguments.behind_approved_proxy:
        if not arguments.tls_cert or not arguments.tls_key:
            raise ValueError("Explicit TLS or an approved HTTPS proxy is required")
        private_root(arguments.tls_key.resolve().parent)
    verify_directory(ROOT)
    if arguments.action == "setup":
        from app.routers.setup import create_setup_app
        from app.services.installation import Setup

        setup = Setup(arguments.state, arguments.origin)
        print("Local one-use setup capability (15min; never URL/chat):", setup.code, flush=True)
        app = create_setup_app(setup)
        app.state.activate_runtime = lambda: runtime_app(arguments.state)
    else:
        app = runtime_app(arguments.state)
    frontend = ROOT / "frontend"

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa(spa_path: str):
        if spa_path == "api" or spa_path.startswith("api/"):
            raise HTTPException(404)
        candidate = (frontend / spa_path).resolve()
        if not candidate.is_relative_to(frontend.resolve()):
            raise HTTPException(404)
        return FileResponse(candidate if candidate.is_file() else frontend / "index.html")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=arguments.port,
        access_log=False,
        proxy_headers=False,
        ssl_certfile=str(arguments.tls_cert) if arguments.tls_cert else None,
        ssl_keyfile=str(arguments.tls_key) if arguments.tls_key else None,
    )


def main():
    parser = argparse.ArgumentParser(description="OCOTE explicit distribution tools")
    commands = parser.add_subparsers(dest="action", required=True)
    pack = commands.add_parser("package")
    pack.add_argument("--build", type=Path, default=ROOT / "dist/ocote-app/browser")
    pack.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("artifact", type=Path)
    for action in ("setup", "runtime"):
        serve = commands.add_parser(action)
        serve.add_argument("--state", type=Path, required=True)
        serve.add_argument("--port", type=int, default=8000)
        serve.add_argument("--tls-cert", type=Path)
        serve.add_argument("--tls-key", type=Path)
        serve.add_argument("--behind-approved-proxy", action="store_true")
        if action == "setup":
            serve.add_argument("--origin", required=True)
    update = commands.add_parser("upgrade")
    for name in ("artifact", "pg-bin", "evidence", "maintenance"):
        update.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-sha256", "restore-database", "operator"):
        update.add_argument("--" + name, required=True)
    update.add_argument("--writers-stopped", action="store_true", required=True)
    update.add_argument("--execute", action="store_true", required=True)
    arguments = parser.parse_args()
    if arguments.action == "package":
        result = package(ROOT, arguments.build, arguments.output)
        print(
            json.dumps(
                {
                    "files": len(result["files"]),
                    "head": result["head"],
                    "sha256": sha(arguments.output.read_bytes()),
                }
            )
        )
    elif arguments.action == "verify":
        print(json.dumps({"head": verify(arguments.artifact)["head"], "verified": True}))
    elif arguments.action == "upgrade":
        from tools.delivery_upgrade import interactive_upgrade

        interactive_upgrade(arguments)
    else:
        start_server(arguments)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("OCOTE distribution stopped safely; no secrets printed.", file=sys.stderr)
        raise SystemExit(1) from None
