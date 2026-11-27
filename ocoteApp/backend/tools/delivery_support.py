import ast
import hashlib
from pathlib import Path
from types import ModuleType

SOURCES = {
    "f1_local.py": {"tables", "canonical"},
    "f2_local.py": {"snapshot"},
    "f8_release.py": {"preserved", "index_signature"},
    "f11_release.py": {
        "PROVIDER_KINDS",
        "INDEX_KINDS",
        "TRIGGER_GUARDS",
        "ReleaseFailure",
        "catalog_ddl",
        "ddl_pair",
        "snapshot_difference",
        "provider_index_signature",
        "canonical_kind_predicate",
        "trigger_name",
        "index_properties",
        "trigger_properties",
        "compare_restored",
        "security_catalog",
    },
}


def build_support(root):
    header = ast.parse(
        "import hashlib\nimport json\nimport re\nfrom types import SimpleNamespace\n"
        "from psycopg import sql\nfrom app.models.identity import Base\n"
    )
    hashes = {}
    for name, required in SOURCES.items():
        path = Path(root) / "backend/tools" / name
        content = path.read_bytes()
        hashes[name] = hashlib.sha256(content).hexdigest()
        found = set()
        for node in ast.parse(content).body:
            names = (
                {node.name}
                if isinstance(node, ast.FunctionDef | ast.ClassDef)
                else {target.id for target in node.targets if isinstance(target, ast.Name)}
                if isinstance(node, ast.Assign)
                else set()
            )
            if names & required:
                if not names <= required:
                    raise ValueError("Unsupported support declaration")
                found.update(names)
                header.body.append(node)
        if found != required:
            raise ValueError("Incomplete immutable support functions")
    header.body.extend(
        ast.parse(
            "local=SimpleNamespace(canonical=canonical,tables=tables)\n"
            "SUPPORT_SOURCE_SHA256=" + repr(hashes) + "\n"
        ).body
    )
    return (ast.unparse(ast.fix_missing_locations(header)) + "\n").encode("utf-8")


def load_support():
    module = ModuleType("ocote_delivery_support")
    exec(
        compile(
            build_support(Path(__file__).resolve().parents[2]),
            "<immutable-delivery-support>",
            "exec",
        ),
        module.__dict__,
    )
    return module
