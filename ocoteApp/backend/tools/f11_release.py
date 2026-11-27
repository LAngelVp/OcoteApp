"""One-shot F11 local release with isolated restores and historical preservation."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings
from app.core.security import CONFIG_LOCK
from app.services.platform import seal_path
from tools import f1_local as local
from tools import f2_local as previous
from tools.f7_release import verify_vault
from tools.f8_release import index_signature, preserved
from tools.f10_release import verify_runtime as verify_f10_runtime

SOURCE, HEAD = "20261126_0009", "20261126_0010"
ADDED = frozenset(
    {
        "external_identities", "sso_transactions", "sso_assertion_uses", "api_keys",
        "task_external_links", "webhook_inbox", "webhook_subscriptions",
        "webhook_deliveries", "webhook_attempts",
    }
)
APPEND_ONLY = frozenset({"sso_assertion_uses", "webhook_inbox", "webhook_attempts"})
PROVIDER_KINDS = ("sso", "devops", "outgoing_webhook")
INDEX_KINDS = {
    "uq_f8_local_kind": ("local_storage", "clamav"),
    "uq_f11_provider_name_scope": PROVIDER_KINDS,
}
TRIGGER_GUARDS = {
    "guard_f11_integration": ("CREATE TRIGGER guard_f11_integration ", 23, False,
                              "guard_f11_integration"),
    "audit_f11_integration": ("CREATE CONSTRAINT TRIGGER audit_f11_integration ", 21, True,
                              "audit_f8_record"),
}


class ReleaseFailure(RuntimeError):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code = code
        self.details = details


def pg_run(arguments, password):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment["PGPASSWORD"] = password
    result = subprocess.run(arguments, env=environment, capture_output=True, timeout=120)
    if result.returncode:
        raise ReleaseFailure(
            "POSTGRESQL_COMMAND_FAILED", command=Path(arguments[0]).stem,
            exit_code=result.returncode,
            sqlstates=sorted({code.decode("ascii") for code in
                              re.findall(rb"ERROR:\s+([0-9A-Z]{5}):", result.stderr)}),
        )


@contextmanager
def verification(directory, label, step):
    local.journal(directory, "f11_verification_started", label=label, step=step)
    try:
        yield
    except Exception as error:
        local.journal(directory, "f11_verification_failed", label=label, step=step,
                      error_type=type(error).__name__,
                      diagnostic=({"code": error.code, **error.details}
                                  if isinstance(error, ReleaseFailure) else None))
        raise


def catalog_ddl(definition):
    if definition is None:
        return None
    literals = {"'" + kind + "'" for kinds in INDEX_KINDS.values() for kind in kinds}
    literals.update("'{" + ",".join(kinds) + "}'" for kinds in INDEX_KINDS.values())
    return re.sub(r"[eE]'(?:[^'\\]|\\.|'')*'|'(?:[^']|'')*'", lambda match: (
        match[0] if match[0] in literals else "'[REDACTED]'"
    ), definition)


def ddl_pair(source_def, restored_def):
    return {"source_def": catalog_ddl(source_def), "restored_def": catalog_ddl(restored_def)}


def snapshot_difference(before, recovered):
    difference = {
        "sections": sorted(key for key in before if recovered.get(key) != before[key]),
        "indexes": sorted({
            entry[0] for entry in before["indexes"] if entry not in recovered["indexes"]
        } | {
            entry[0] for entry in recovered["indexes"] if entry not in before["indexes"]
        }),
    }
    original_indexes, restored_indexes = dict(before["indexes"]), dict(recovered["indexes"])
    definitions = [
        {"index": name, **ddl_pair(original_indexes.get(name), restored_indexes.get(name))}
        for name in difference["indexes"]
        if all(definition is None or definition.startswith("CREATE ") for definition in (
            original_indexes.get(name), restored_indexes.get(name),
        ))
    ]
    if definitions:
        difference["index_definitions"] = definitions
    if "triggers" in difference["sections"]:
        difference["triggers"] = sorted({
            name for snapshot, other in ((before, recovered), (recovered, before))
            for table, definition in snapshot["triggers"]
            if (table, definition) not in other["triggers"]
            for name in [trigger_name(table, definition) or "unrecognized_trigger"]
        })
        difference["trigger_definition_hashes"] = {
            label: sorted(hashlib.sha256(local.canonical(entry)).hexdigest()
                          for entry in snapshot["triggers"] if entry not in other["triggers"])
            for label, snapshot, other in (
                ("source", before, recovered), ("restored", recovered, before),
            )
        }
        source_triggers = {
            name: definition for table, definition in before.get("triggers", [])
            if (name := trigger_name(table, definition))
        }
        restored_triggers = {
            name: definition for table, definition in recovered.get("triggers", [])
            if (name := trigger_name(table, definition))
        }
        difference["trigger_definitions"] = [
            {"trigger": name, **ddl_pair(source_triggers.get(name), restored_triggers.get(name))}
            for name in sorted(source_triggers.keys() | restored_triggers.keys())
            if source_triggers.get(name) != restored_triggers.get(name)
        ]
    return difference


def upgraded(before, after):
    if (
        set(before["tables"]) - set(after["tables"])
        or set(after["tables"]) - set(before["tables"]) != ADDED
    ):
        raise RuntimeError("Unexpected F11 table set")
    if after["rows"]["alembic_version"] != [json.dumps({"version_num": HEAD})]:
        raise RuntimeError("Unexpected F11 revision")
    if any(after["rows"][table] for table in ADDED):
        raise RuntimeError("Unsolicited F11 business defaults")
    preserved(before, after)


def verify_runtime(database):
    verify_f10_runtime(database)
    with local.role_connection(Settings().database_url.get_secret_value(), database) as connection:
        if connection.execute("SELECT current_user").fetchone()[0] != "ocote_runtime":
            raise RuntimeError("Runtime identity required")
        for table in ADDED:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                expected = privilege in {"SELECT", "INSERT"} or (
                    privilege == "UPDATE" and table not in APPEND_ONLY
                )
                actual = connection.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)
                ).fetchone()[0]
                if actual != expected:
                    raise RuntimeError("Unexpected F11 privilege: " + table + ":" + privilege)


def provider_index_signature(connection):
    shape = connection.execute(
        "SELECT i.indisunique,i.indisprimary,i.indisvalid,i.indisready,"
        "i.indnullsnotdistinct,i.indkey::text,i.indclass::text,i.indcollation::text,"
        "i.indoption::text,i.indnatts,i.indnkeyatts,am.amname,t.relname,"
        "pg_get_expr(i.indexprs,i.indrelid),i.indisexclusion,pg_get_expr(i.indpred,i.indrelid) "
        "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
        "JOIN pg_class t ON t.oid=i.indrelid JOIN pg_am am ON am.oid=c.relam "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname='uq_f11_provider_name_scope'"
    ).fetchone()
    if not shape or shape[:5] != (True, False, True, True, True) or (
        shape[9:15] != (4, 4, "btree", "integration_configs", "lower((name)::text)", False)
    ):
        raise ReleaseFailure("F11_PROVIDER_INDEX_SHAPE_INVALID")
    kinds = ("local_storage", "clamav", "object_storage", "sso", "devops", "outgoing_webhook")
    truth = tuple(connection.execute(
        sql.SQL("SELECT {} FROM (SELECT %s::varchar(30) kind) candidate").format(
            sql.SQL(shape[-1])
        ),
        (kind,),
    ).fetchone()[0] for kind in kinds)
    if truth != (False, False, False, True, True, True):
        raise ReleaseFailure("F11_PROVIDER_INDEX_PREDICATE_INVALID")
    return shape[:-1], truth


def canonical_kind_predicate(definition, kinds, *, element_casts=False):
    canonical = "'{" + ",".join(kinds) + "}'::text[]"
    arrays = [
        "(ARRAY[" + ", ".join("'" + kind + "'::character varying" for kind in kinds) + "])::text[]",
        "ARRAY[" + ", ".join("'" + kind + "'::text" for kind in kinds) + "]",
    ]
    if element_casts:
        arrays.append("ARRAY[" + ", ".join(
            "('" + kind + "'::character varying)::text" for kind in kinds
        ) + "]")
    for array in arrays:
        fragment = "= ANY (" + array + ")"
        if definition.count(fragment) == 1:
            return definition.replace(fragment, "= ANY (" + canonical + ")", 1)
    return definition


def trigger_name(table, definition):
    if table == "integration_configs":
        for name, (prefix, *_properties) in TRIGGER_GUARDS.items():
            if definition.startswith(prefix):
                return name
    return None


def index_properties(connection, name):
    properties = connection.execute(
        "SELECT i.indimmediate,i.indisexclusion,i.indislive,i.indisreplident,"
        "i.indisclustered,c.reloptions,c.reltablespace,pg_get_expr(i.indexprs,i.indrelid) "
        "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname=%s", (name,),
    ).fetchone()
    if properties is None:
        raise ReleaseFailure("RESTORED_INDEX_CATALOG_MISSING", index=name)
    return properties


def trigger_properties(connection, name):
    properties = connection.execute(
        "SELECT jsonb_build_object("
        "'table_schema',ns.nspname,'table',c.relname,'type',t.tgtype,"
        "'enabled',t.tgenabled,'deferrable',t.tgdeferrable,'deferred',t.tginitdeferred,"
        "'columns',t.tgattr::text,'argument_count',t.tgnargs,'arguments',encode(t.tgargs,'hex'),"
        "'old_table',t.tgoldtable,'new_table',t.tgnewtable,'parent',t.tgparentid<>0,"
        "'constraint',t.tgconstraint<>0,'constraint_index',t.tgconstrindid<>0,"
        "'function_schema',pn.nspname,'function_name',p.proname,"
        "'function_definition',pg_get_functiondef(p.oid),'function_owner',pg_get_userbyid(p.proowner),"
        "'security_definer',p.prosecdef,'function_config',p.proconfig,"
        "'kind_type',format_type(a.atttypid,a.atttypmod),"
        "'kind_collation',a.attcollation::regcollation::text) "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace ns ON ns.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid "
        "JOIN pg_namespace pn ON pn.oid=p.pronamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='kind' AND NOT a.attisdropped "
        "WHERE ns.nspname='public' AND c.relname='integration_configs' AND t.tgname=%s "
        "AND NOT t.tgisinternal", (name,),
    ).fetchone()
    expected_type, deferred, function = TRIGGER_GUARDS[name][1:]
    expected = {
        "table_schema": "public", "table": "integration_configs", "type": expected_type,
        "enabled": "O", "deferrable": deferred, "deferred": deferred, "columns": "",
        "argument_count": 0, "arguments": "", "old_table": None, "new_table": None,
        "parent": False, "constraint": deferred, "constraint_index": False,
        "function_schema": "public", "function_name": function,
        "kind_type": "character varying(20)",
    }
    if not properties or any(properties[0].get(key) != value for key, value in expected.items()):
        raise ReleaseFailure("RESTORED_TRIGGER_CATALOG_INVALID", trigger=name)
    return properties[0]


def compare_restored(before, recovered, source, connection):
    difference = snapshot_difference(before, recovered)
    signatures = {
        "uq_f8_local_kind": index_signature,
        "uq_f11_provider_name_scope": provider_index_signature,
    }
    if not set(difference["sections"]) <= {"indexes", "triggers"} or (
        not set(difference["indexes"]) <= signatures.keys()
    ):
        raise ReleaseFailure("RESTORED_SNAPSHOT_DIFFERS", **difference)
    original_indexes, restored_indexes = dict(before["indexes"]), dict(recovered["indexes"])
    if original_indexes.keys() != restored_indexes.keys():
        raise ReleaseFailure("RESTORED_INDEX_SET_DIFFERS")
    for name in sorted(original_indexes.keys() & signatures.keys()):
        definitions = ddl_pair(original_indexes[name], restored_indexes[name])
        if canonical_kind_predicate(original_indexes[name], INDEX_KINDS[name],
                                    element_casts=True) != (
            canonical_kind_predicate(restored_indexes[name], INDEX_KINDS[name],
                                     element_casts=True)
        ):
            raise ReleaseFailure("RESTORED_INDEX_DEFINITION_DIFFERS", index=name,
                                 **definitions)
        try:
            if signatures[name](source) != signatures[name](connection):
                raise ReleaseFailure("RESTORED_INDEX_SEMANTICS_DIFFER", index=name, **definitions)
            if index_properties(source, name) != index_properties(connection, name):
                raise ReleaseFailure("RESTORED_INDEX_CATALOG_DIFFERS", index=name, **definitions)
        except ReleaseFailure as error:
            error.details.update(index=name, **definitions)
            raise
        except RuntimeError as error:
            raise ReleaseFailure("RESTORED_INDEX_CATALOG_INVALID", index=name,
                                 **definitions) from error
    original_triggers, restored_triggers = [], []
    for snapshot, result in ((before, original_triggers), (recovered, restored_triggers)):
        for table, definition in snapshot.get("triggers", []):
            name = trigger_name(table, definition)
            result.append((table, canonical_kind_predicate(definition, PROVIDER_KINDS,
                                                          element_casts=True)
                           if name else definition))
    if sorted(original_triggers) != sorted(restored_triggers):
        raise ReleaseFailure("RESTORED_TRIGGER_DEFINITION_DIFFERS", **difference)
    names = sorted({trigger_name(table, definition) for table, definition
                    in before.get("triggers", [])} - {None})
    for name in names:
        definitions = ddl_pair(
            next(definition for table, definition in before["triggers"]
                 if trigger_name(table, definition) == name),
            next(definition for table, definition in recovered["triggers"]
                 if trigger_name(table, definition) == name),
        )
        try:
            original_properties = trigger_properties(source, name)
            restored_properties = trigger_properties(connection, name)
        except ReleaseFailure as error:
            error.details.update(definitions)
            raise
        if original_properties != restored_properties:
            raise ReleaseFailure("RESTORED_TRIGGER_CATALOG_DIFFERS", trigger=name, **definitions)
    return {"indexes": difference["indexes"], "triggers": difference.get("triggers", [])}


def security_catalog(connection):
    queries = {
        "relations": "SELECT c.relname,c.relkind,pg_get_userbyid(c.relowner),"
        "c.relrowsecurity,c.relforcerowsecurity,"
        "ARRAY(SELECT unnest(c.reloptions) ORDER BY 1) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2",
        "routines": "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
        "pg_get_userbyid(p.proowner),l.lanname,p.prosecdef,p.proleakproof,p.proisstrict,"
        "p.provolatile,p.proparallel,p.proconfig FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang "
        "WHERE n.nspname='public' ORDER BY 1,2",
        "relation_grants": "SELECT c.relname,pg_get_userbyid(a.grantor),"
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,"
        "a.privilege_type,a.is_grantable FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,"
        "acldefault(CASE WHEN c.relkind='S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,"
        "c.relowner))) a WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m','f') "
        "ORDER BY 1,2,3,4,5",
        "column_grants": "SELECT c.relname,t.attname,pg_get_userbyid(a.grantor),"
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,"
        "a.privilege_type,a.is_grantable FROM pg_attribute t "
        "JOIN pg_class c ON c.oid=t.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(t.attacl) a "
        "WHERE n.nspname='public' AND t.attnum>0 AND NOT t.attisdropped ORDER BY 1,2,3,4,5,6",
        "routine_grants": "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
        "pg_get_userbyid(a.grantor),"
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,"
        "a.privilege_type,a.is_grantable FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace "
        "CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a "
        "WHERE n.nspname='public' ORDER BY 1,2,3,4,5,6",
        "schema_grants": "SELECT n.nspname,pg_get_userbyid(n.nspowner),"
        "pg_get_userbyid(a.grantor),"
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,"
        "a.privilege_type,a.is_grantable FROM pg_namespace n "
        "CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a "
        "WHERE n.nspname='public' ORDER BY 1,2,3,4,5,6",
        "default_grants": "SELECT COALESCE(n.nspname,'*'),pg_get_userbyid(d.defaclrole),"
        "d.defaclobjtype,pg_get_userbyid(a.grantor),"
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,"
        "a.privilege_type,a.is_grantable FROM pg_default_acl d "
        "LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace "
        "CROSS JOIN LATERAL aclexplode(d.defaclacl) a "
        "WHERE n.nspname='public' OR d.defaclnamespace=0 ORDER BY 1,2,3,4,5,6,7",
        "views": "SELECT c.relname,c.relkind,pg_get_viewdef(c.oid) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('v','m') ORDER BY 1,2",
        "policies": "SELECT tablename,policyname,permissive,roles,cmd,qual,with_check "
        "FROM pg_policies WHERE schemaname='public' ORDER BY 1,2",
        "sequences": "SELECT sequencename,sequenceowner,data_type,start_value,min_value,"
        "max_value,increment_by,cycle,cache_size,last_value "
        "FROM pg_sequences WHERE schemaname='public' ORDER BY 1",
    }
    return {name: connection.execute(query).fetchall() for name, query in queries.items()}


def compare_security_catalog(source, restored):
    original, recovered = security_catalog(source), security_catalog(restored)
    if original != recovered:
        raise ReleaseFailure(
            "RESTORED_SECURITY_CATALOG_DIFFERS",
            sections=sorted(name for name in original if original[name] != recovered.get(name)),
            source_sha256=hashlib.sha256(local.canonical(original)).hexdigest(),
            restored_sha256=hashlib.sha256(local.canonical(recovered)).hexdigest(),
        )


def restored(directory, label, before, *, upgrade=False, root_seal=None):
    url = MigrationSettings().migration_database_url.get_secret_value()
    with previous.isolated_database("restore") as destination:
        with verification(directory, label, "pg_restore"):
            pg_run(
                [
                    str(local.PG_BIN / "pg_restore"), "-w", "-h", "127.0.0.1", "-p", "5432",
                    "-U", local.MIGRATOR, "-d", destination, "--exit-on-error", "--no-owner",
                    str(directory / (label + ".dump")),
                ],
                make_url(url).password,
            )
        with local.role_connection(url, destination) as connection:
            with verification(directory, label, "snapshot_compare"):
                recovered = previous.snapshot(connection)
                with local.role_connection(url) as source:
                    equivalent = compare_restored(before, recovered, source, connection)
                    compare_security_catalog(source, connection)
            if any(equivalent.values()):
                local.journal(directory, "f11_snapshot_restore_equivalent", **equivalent)
            if upgrade:
                previous.upgrade(destination, HEAD)
                after = previous.snapshot(connection)
                upgraded(before, after)
                previous.upgrade(destination, HEAD)
                if previous.snapshot(connection) != after:
                    raise RuntimeError("Restored F11 second upgrade is not a no-op")
            with verification(directory, label, "runtime_grants"):
                verify_runtime(destination)
        if root_seal is not None:
            with verification(directory, label, "vault"):
                verify_vault(destination, root_seal)
    local.journal(
        directory, "f11_restore_verified", label=label, upgraded=upgrade,
        vault_verified=root_seal is not None,
    )


def backup(admin, directory, label, *, upgrade=False, root_seal=None):
    baseline = previous.snapshot(admin)
    destination = directory / (label + ".dump")
    local.write_private(destination, b"")
    pg_run(
        [
            str(local.PG_BIN / "pg_dump"), "-w", "-h", "127.0.0.1", "-p", "5432",
            "-U", "postgres", "-d", local.DATABASE_NAME, "--format=custom",
            "--file=" + str(destination),
        ],
        os.environ["PGPASSWORD"],
    )
    restored(directory, label, baseline, upgrade=upgrade, root_seal=root_seal)
    if previous.snapshot(admin) != baseline:
        raise RuntimeError("Origin changed during F11 backup/restore")
    metadata = {
        "sha256": local.digest(destination), "bytes": destination.stat().st_size,
        "verified_at": local.now(),
        "snapshot_sha256": hashlib.sha256(local.canonical(baseline)).hexdigest(),
    }
    local.write_private(directory / (label + "-manifest.json"), local.canonical(metadata))
    return metadata


def artifact_files():
    return {
        path.relative_to(local.ROOT).as_posix(): local.digest(path)
        for folder in ("backend/app", "backend/alembic", "backend/tools", "src", "public/logos")
        for path in (local.ROOT / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def apply(artifacts):
    supplied = Path(artifacts)
    if not supplied.is_absolute() or supplied.is_symlink() or supplied.is_junction():
        raise RuntimeError("Absolute private F11 artifact directory required")
    root = supplied.resolve()
    if root == local.ROOT or root.is_relative_to(local.ROOT):
        raise RuntimeError("F11 artifacts must remain outside checkout")
    with local.admin_connection() as admin:
        local.verify_identity(admin)
        if local.MARKER.exists():
            raise RuntimeError("Existing maintenance must be investigated")
        if admin.execute("SELECT version_num FROM alembic_version").fetchall() != [(SOURCE,)]:
            raise RuntimeError("Only source0009 is authorized; never repeat apply0010")
        if not admin.execute("SELECT pg_try_advisory_lock(%s)", (local.LOCK_KEY,)).fetchone()[0]:
            raise RuntimeError("Release lock held")
        try:
            if admin.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Drain API/all writers before F11 release")
            local.private_directory(root)
            size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            if shutil.disk_usage(root).free < size * 6 + 134217728:
                raise RuntimeError("Insufficient space for verified F11 backups")
            attempt, request_id, started = uuid4(), uuid4(), local.now()
            directory = root / ("f11-" + str(attempt))
            local.private_directory(directory)
            local.write_private(directory / "events.jsonl", b"")
            local.private_directory(local.LOCAL)
            local.write_private(local.MARKER, local.canonical({"attempt": attempt, "phase": "F11"}))
            try:
                admin.execute("SELECT pg_advisory_lock(%s)", (CONFIG_LOCK,))
                before, catalog, legacy = (
                    previous.snapshot(admin), local.catalog(admin), local.legacy_catalog(admin),
                )
                if (
                    len(before["tables"]) != 58
                    or len(before["rows"]["release_history"]) != 10
                    or any(
                        json.loads(row)["status"] not in {"succeeded", "failed"}
                        for row in before["rows"]["release_history"]
                    )
                ):
                    raise RuntimeError("Exact 58-table/10-terminal-release F10 origin required")
                instance = admin.execute("SELECT id FROM deployment_instances").fetchone()[0]
                root_path = seal_path(instance)
                root_hash = local.digest(root_path)
                local.write_private(directory / "master.dpapi", root_path.read_bytes())
                files = artifact_files()
                manifest = {
                    "files": files, "source_revision": SOURCE, "target_revision": HEAD,
                    "scope": "local_only", "customer_package": False,
                }
                local.write_private(directory / "artifact-manifest.json", local.canonical(manifest))
                local.journal(directory, "f11_started", attempt=attempt, request_id=request_id)
                verified = backup(admin, directory, "before", upgrade=True, root_seal=root_path)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                migrated = previous.snapshot(admin)
                upgraded(before, migrated)
                previous.upgrade(local.DATABASE_NAME, HEAD)
                if previous.snapshot(admin) != migrated:
                    raise RuntimeError("Source F11 second upgrade changed state")
                verify_runtime(local.DATABASE_NAME)
                verify_vault(local.DATABASE_NAME, root_path)
                url = MigrationSettings().migration_database_url.get_secret_value()
                with local.role_connection(url) as connection:
                    connection.execute(
                        "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                        "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                        "deployment_mode,phase,status,backup_manifest_sha256,"
                        "backup_verified_at,request_id) "
                        "VALUES(%s,%s,%s,'0.11.0',%s,%s,%s,%s,%s,'local','validation','running',%s,%s,%s)",
                        (
                            attempt, started, local.now(),
                            hashlib.sha256(local.canonical(files)).hexdigest(),
                            local.digest(directory / "artifact-manifest.json"), SOURCE, HEAD,
                            "LUIS ANGEL VALLEJO - DESARROLLADOR",
                            local.digest(directory / "before-manifest.json"),
                            verified["verified_at"], request_id,
                        ),
                    )
                backup(admin, directory, "recorded", root_seal=root_path)
                with local.role_connection(url) as connection:
                    changed = connection.execute(
                        "UPDATE release_history SET version=version+1,updated_at=%s,"
                        "finished_at=%s,status='succeeded',phase='complete',"
                        "result_code='F11_LOCAL_VERIFIED' "
                        "WHERE id=%s AND version=1 AND status='running'",
                        (local.now(), local.now(), attempt),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("Own terminal F11 release transition failed")
                backup(admin, directory, "terminal", root_seal=root_path)
                final = previous.snapshot(admin)
                preserved(before, final, ledger=True)
                old_releases = {json.loads(row)["id"] for row in before["rows"]["release_history"]}
                final_releases = {json.loads(row)["id"] for row in final["rows"]["release_history"]}
                if final_releases - old_releases != {str(attempt)} or len(final["tables"]) != 67:
                    raise RuntimeError("Unexpected new F11 release records/table set")
                if (
                    local.catalog(admin) != catalog
                    or local.legacy_catalog(admin) != legacy
                    or local.digest(root_path) != root_hash
                ):
                    raise RuntimeError("Database identity/legacy/root changed")
                if any(final["rows"][table] for table in ADDED):
                    raise RuntimeError("F11 business defaults appeared during release")
                if artifact_files() != files:
                    raise RuntimeError("F11 artifact changed during release")
                local.journal(
                    directory, "f11_succeeded", attempt=attempt, revision=HEAD,
                    instance_id=instance, tables=67, historical_values_preserved=True,
                )
                local.MARKER.unlink()
                print("F11 verified: " + str(directory))
                return directory
            except Exception as error:
                local.journal(
                    directory, "f11_failed", error_type=type(error).__name__,
                    diagnostic=({"code": error.code, **error.details}
                                if isinstance(error, ReleaseFailure) else None),
                    maintenance_retained=True,
                )
                raise
            finally:
                admin.execute("SELECT pg_advisory_unlock(%s)", (CONFIG_LOCK,))
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s)", (local.LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        apply(arguments.artifacts)
        return 0
    except Exception as error:
        print("F11_RELEASE_FAILED_" + (
            error.code if isinstance(error, ReleaseFailure) else type(error).__name__
        ))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())