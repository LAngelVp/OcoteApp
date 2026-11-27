import ast
import hashlib
from pathlib import Path
from types import ModuleType


def build_worker(root):
    header = ast.parse(
        "import json, os\nfrom types import SimpleNamespace\n"
        "from uuid import UUID, uuid4, uuid5, NAMESPACE_URL\nfrom zoneinfo import ZoneInfo\n"
        "from sqlalchemy import Date, func, select, text\nfrom sqlalchemy.exc import DBAPIError\n"
        "from app.core.config import BACKEND_DIR\nfrom app.core.errors import CommandError\n"
        "from app.models.collaboration import RecurrenceSchedule\n"
        "from app.models.identity import User\n"
        "from app.schemas.collaboration import RecurrenceRun\n"
        "from app.services import collaboration, operations\n"
        "from app.services.enterprise import enabled\n"
        "from app.services.identity import config_lock\n"
        "from app.services.notification_worker import tick as notification_tick\n"
        "from app.services.webhook_worker import budget\n"
        "from app.services.webhook_worker import tick as webhook_tick\n"
    )
    hashes = {}
    for name, functions in {
        "f9_worker.py": {"idempotency_key"},
        "f12_worker.py": {"require_runtime", "recurrence_tick"},
    }.items():
        content = (Path(root) / "backend/tools" / name).read_bytes()
        selected = [
            node
            for node in ast.parse(content).body
            if isinstance(node, ast.FunctionDef) and node.name in functions
        ]
        if {node.name for node in selected} != functions:
            raise ValueError("Immutable worker support is incomplete")
        header.body.extend(selected)
        hashes[name] = hashlib.sha256(content).hexdigest()
    own = ast.parse(Path(__file__).read_text())
    header.body.extend(
        node
        for node in own.body
        if isinstance(node, ast.FunctionDef) and node.name == "worker_main"
    )
    header.body.extend(
        ast.parse(
            "WORKER_SOURCE_SHA256="
            + repr(hashes)
            + "\nif __name__=='__main__':\n raise SystemExit(worker_main())"
        ).body
    )
    return (ast.unparse(ast.fix_missing_locations(header)) + "\n").encode("utf-8")


def worker_main():
    import argparse
    import importlib
    import os
    from pathlib import Path
    from uuid import UUID

    from tools.delivery import ROOT, verify_directory
    from tools.delivery_runtime import runtime_app
    from tools.delivery_security import verify_signature

    parser = argparse.ArgumentParser(description="One signed, runtime-only worker pass")
    for field in ("state", "maintenance", "artifact", "signature", "public-key"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument(
        "--mode", choices=["recurrence", "notifications", "webhooks"], required=True
    )
    parser.add_argument("--principal", type=UUID)
    parser.add_argument("--limit", type=int, default=100)
    arguments = parser.parse_args()
    if os.environ.get("PGPASSWORD") or not 1 <= arguments.limit <= 100:
        raise ValueError("Workers require runtime identity and a bounded pass")
    trusted = verify_signature(arguments.artifact, arguments.signature, arguments.public_key)
    verify_directory(ROOT)
    import json

    from app.services.installation import canonical
    from tools.delivery import sha

    if trusted["manifest_sha256"] != sha(
        canonical(json.loads((ROOT / "manifest.json").read_text()))
    ):
        raise ValueError("Worker is not running the signed release")
    if arguments.maintenance.resolve() != (arguments.state / "maintenance.json").resolve():
        raise ValueError("Worker maintenance must match its sealed runtime state")
    if arguments.maintenance.exists():
        print('{"skipped":"maintenance","sql_connections_opened":0}')
        return 0
    if arguments.mode != "recurrence" and arguments.principal is None:
        raise ValueError("An explicitly approved technical principal is required")
    importlib.import_module("app.main")
    namespace = globals()
    if "require_runtime" not in namespace:
        namespace = ModuleType("ocote_worker_support").__dict__
        namespace["__name__"] = "ocote_worker_support"
        exec(compile(build_worker(ROOT), "<immutable-worker-support>", "exec"), namespace)
    app = runtime_app(arguments.state)
    factory = app.state.session_factory
    try:
        with factory.begin() as database:
            namespace["require_runtime"](database)
        action = (
            namespace["recurrence_tick"]
            if arguments.mode == "recurrence"
            else namespace[
                "notification_tick" if arguments.mode == "notifications" else "webhook_tick"
            ]
        )
        result = (
            action(factory, arguments.limit)
            if arguments.mode == "recurrence"
            else action(factory, arguments.principal, arguments.limit)
        )
        print(json.dumps(result))
        return int(
            any(result.get(key, 0) for key in ("failures", "failed", "rejected", "ambiguous"))
        )
    finally:
        factory.kw["bind"].dispose()


if __name__ == "__main__":
    raise SystemExit(worker_main())
