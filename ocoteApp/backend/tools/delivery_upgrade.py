import getpass
import hashlib
import hmac
import importlib
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import CommandError
from app.core.security import CONFIG_LOCK
from app.core.vault import EncryptedValue, OSSealedFile, Vault, WrappedKey
from app.schemas.installation import Connection
from app.services.installation import (
    HEAD,
    LOCK_KEY,
    canonical,
    connection_options,
    inspect_role,
    private_directory,
    role_options,
    write_private,
)
from app.services.platform import seal_path
from tools.delivery import sha, verify


def quiet(connection):
    if connection.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
        " AND pid<>pg_backend_pid() AND backend_type='client backend'",
    ).fetchone()[0]:
        raise CommandError(409, "DELIVERY_WRITERS_PRESENT")


def verify_vault(connection, root, instance):
    vault = Vault(root, instance, "windows-dpapi-v1")
    for row in connection.execute(
        "SELECT k.id,k.instance_id,k.purpose,k.epoch,k.root_key_ref,k.nonce,k.wrapped_dek,"
        "e.owner_id,e.secret_version,e.nonce,e.ciphertext,e.key_id FROM encrypted_secrets e"
        " JOIN secret_key_versions k ON k.id=e.key_id"
    ).fetchall():
        vault.decrypt(WrappedKey(*row[:7]), EncryptedValue(row[11], *row[7:11]))


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def restore_payload(encrypted, root, instance):
    target = encrypted.parent / (uuid4().hex + ".restore.dump")
    created = False
    try:
        try:
            metadata = json.loads(encrypted.with_suffix(".json").read_text())
            context = metadata["context"].encode("ascii")
            values = json.loads(context)
            if (
                metadata["algorithm"] != "AES-256-GCM"
                or values["instance"] != str(instance)
                or values["head"] != HEAD
                or values["sha256"] != metadata["plaintext_sha256"]
            ):
                raise ValueError("Invalid backup context")
            key = AESGCM(root).decrypt(
                bytes.fromhex(metadata["wrap_nonce"]),
                bytes.fromhex(metadata["wrapped_dek"]),
                context,
            )
            decryptor = Cipher(
                algorithms.AES(key),
                modes.GCM(
                    bytes.fromhex(metadata["nonce"]),
                    bytes.fromhex(metadata["tag"]),
                ),
            ).decryptor()
            decryptor.authenticate_additional_data(context)
            write_private(target, b"")
            created = True
            with encrypted.open("rb") as source, target.open("wb") as destination:
                while chunk := source.read(1048576):
                    destination.write(decryptor.update(chunk))
                destination.write(decryptor.finalize())
                destination.flush()
                os.fsync(destination.fileno())
            if file_sha(target) != metadata["plaintext_sha256"]:
                raise ValueError("Backup digest differs")
        except (InvalidTag, ValueError, TypeError, KeyError, OSError):
            raise CommandError(503, "DELIVERY_BACKUP_AUTHENTICATION_FAILED") from None
        yield target
    finally:
        if created:
            target.unlink(missing_ok=True)


def encrypt_backup(dump, root, instance):
    with dump.open("rb") as source:
        original_hash = hashlib.file_digest(source, "sha256").hexdigest()
    context = canonical({"instance": str(instance), "head": HEAD, "sha256": original_hash})
    data_key = AESGCM.generate_key(bit_length=256)
    nonce, wrap_nonce = os.urandom(12), os.urandom(12)
    wrapped = AESGCM(root).encrypt(wrap_nonce, data_key, context)
    encryptor = Cipher(algorithms.AES(data_key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(context)
    encrypted = dump.with_suffix(".dump.enc")
    write_private(encrypted, b"")
    with dump.open("rb") as source, encrypted.open("wb") as target:
        while chunk := source.read(1048576):
            target.write(encryptor.update(chunk))
        target.write(encryptor.finalize())
        target.flush()
        os.fsync(target.fileno())
    recovered_key = AESGCM(root).decrypt(wrap_nonce, wrapped, context)
    decryptor = Cipher(algorithms.AES(recovered_key), modes.GCM(nonce, encryptor.tag)).decryptor()
    decryptor.authenticate_additional_data(context)
    recovered = hashlib.sha256()
    with encrypted.open("rb") as source:
        while chunk := source.read(1048576):
            recovered.update(decryptor.update(chunk))
        recovered.update(decryptor.finalize())
    if recovered.hexdigest() != original_hash:
        raise CommandError(503, "DELIVERY_BACKUP_ENCRYPTION_FAILED")
    metadata = {
        "algorithm": "AES-256-GCM",
        "nonce": nonce.hex(),
        "tag": encryptor.tag.hex(),
        "wrapped_dek": wrapped.hex(),
        "wrap_nonce": wrap_nonce.hex(),
        "context": context.decode("ascii"),
        "plaintext_sha256": original_hash,
    }
    write_private(encrypted.with_suffix(".json"), canonical(metadata))
    return encrypted


def pg_run(executable, options, database, extra):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
    environment.update(
        PGPASSWORD=options["password"],
        PGHOSTADDR=options["hostaddr"],
        PGSSLMODE=options["sslmode"],
        PGOPTIONS="-c timezone=UTC",
    )
    if options.get("sslrootcert"):
        environment["PGSSLROOTCERT"] = options["sslrootcert"]
    result = subprocess.run(
        [
            str(executable),
            "-w",
            "-h",
            options["host"],
            "-p",
            str(options["port"]),
            "-U",
            options["user"],
            "-d",
            database,
            *extra,
        ],
        env=environment,
        capture_output=True,
        timeout=600,
    )
    if result.returncode:
        raise CommandError(503, "DELIVERY_BACKUP_OR_RESTORE_FAILED")


def upgrade(
    body, *, artifact, trusted_sha256, restore_database, pg_bin, evidence, maintenance, operator
):
    if (
        not re.fullmatch(r"[a-f0-9]{64}", trusted_sha256)
        or sha(
            Path(artifact).read_bytes(),
        )
        != trusted_sha256
    ):
        raise CommandError(409, "DELIVERY_ARTIFACT_UNTRUSTED")
    manifest = verify(artifact)
    if not re.fullmatch(r"ocote_f2_restore_[a-f0-9]{32}", restore_database):
        raise CommandError(409, "DELIVERY_ISOLATED_RESTORE_REQUIRED")
    if not operator.strip() or len(operator) > 160:
        raise CommandError(422, "DELIVERY_OPERATOR_REQUIRED")
    pg_bin, evidence, maintenance = Path(pg_bin), Path(evidence), Path(maintenance)
    if evidence.exists() or maintenance.exists():
        raise CommandError(409, "DELIVERY_EXISTING_ATTEMPT")
    for binary in ("pg_dump.exe", "pg_restore.exe"):
        if not (pg_bin / binary).is_file():
            raise CommandError(503, "DELIVERY_POSTGRES_BINARIES_REQUIRED")
    private_directory(evidence)
    private_directory(maintenance.parent)
    importlib.import_module("app.main")
    from tools import delivery_support

    comparator = (
        delivery_support.load_support()
        if hasattr(delivery_support, "load_support")
        else delivery_support
    )
    snapshotter = comparator

    with connection_options(body) as options:
        migration = role_options(options, body, "ocote_migrador")
        with psycopg.connect(**migration, autocommit=True) as source:
            for key in (LOCK_KEY, CONFIG_LOCK):
                if not source.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
                    raise CommandError(409, "DELIVERY_RELEASE_LOCKED")
            quiet(source)
            inspect_role(source, body, "ocote_migrador", virgin=False)
            if source.execute("SELECT version_num FROM alembic_version").fetchall() != [(HEAD,)]:
                raise CommandError(409, "DELIVERY_SOURCE_UNSUPPORTED")
            if source.execute(
                "SELECT count(*) FROM release_history WHERE status='running'",
            ).fetchone()[0]:
                raise CommandError(409, "DELIVERY_INCOMPLETE_RELEASE")
            instance = source.execute("SELECT id FROM deployment_instances").fetchone()[0]
            root_path = seal_path(instance)
            root = OSSealedFile(root_path, instance).read()
            verify_vault(source, root, instance)
            root_digest = sha(root_path.read_bytes())
            request_id, attempt = uuid4(), uuid4()
            marker = canonical(
                {
                    "state": "maintenance",
                    "head": HEAD,
                    "instance": str(instance),
                    "request_id": str(request_id),
                    "release": str(attempt),
                }
            )
            write_private(maintenance, marker)
            write_private(evidence / "master.dpapi", root_path.read_bytes())
            original = snapshotter.snapshot(source)
            security = comparator.security_catalog(source)

            def backup(label):
                quiet(source)
                baseline = snapshotter.snapshot(source)
                dump = evidence / f"{label}.dump"
                write_private(dump, b"")
                pg_run(
                    pg_bin / "pg_dump.exe",
                    migration,
                    body.database,
                    ["--format=custom", "--file=" + str(dump)],
                )
                encrypted = encrypt_backup(dump, root, instance)
                original_sha, original_size = file_sha(dump), dump.stat().st_size
                dump.unlink()
                with psycopg.connect(
                    **(migration | {"dbname": restore_database}), autocommit=True
                ) as destination:
                    existing = destination.execute(
                        "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
                    ).fetchone()[0]
                    if existing:
                        raise CommandError(409, "DELIVERY_RESTORE_NOT_EMPTY")
                with restore_payload(encrypted, root, instance) as restored_dump:
                    pg_run(
                        pg_bin / "pg_restore.exe",
                        migration,
                        restore_database,
                        ["--exit-on-error", str(restored_dump)],
                    )
                with psycopg.connect(
                    **(migration | {"dbname": restore_database}), autocommit=True
                ) as destination:
                    comparator.compare_restored(
                        baseline, snapshotter.snapshot(destination), source, destination
                    )
                    verify_vault(destination, root, instance)
                    if comparator.security_catalog(destination) != security:
                        raise CommandError(409, "DELIVERY_RESTORED_SECURITY_DIFFERS")
                    if source.execute(
                        "SELECT count(*) FROM pg_constraint WHERE NOT convalidated",
                    ).fetchone()[0]:
                        raise CommandError(409, "DELIVERY_CONSTRAINT_INVALID")
                receipt = {
                    "sha256": original_sha,
                    "encrypted_sha256": file_sha(encrypted),
                    "bytes": original_size,
                    "restore_input": "authenticated-decryption-of-encrypted-backup",
                    "verified_at": datetime.now(UTC).isoformat(),
                    "head": HEAD,
                }
                write_private(evidence / f"{label}-manifest.json", canonical(receipt))
                return receipt

            verified = backup("before")
            if (
                snapshotter.snapshot(source) != original
                or comparator.security_catalog(
                    source,
                )
                != security
                or sha(root_path.read_bytes()) != root_digest
            ):
                raise CommandError(409, "DELIVERY_SOURCE_CHANGED")
            timestamp = datetime.now(UTC)
            source.execute(
                "INSERT INTO release_history(id,created_at,updated_at,application_version,"
                "artifact_sha256,manifest_sha256,source_revision,target_revision,operator_ref,"
                "deployment_mode,phase,status,backup_manifest_sha256,backup_verified_at,request_id)"
                " VALUES(%s,%s,%s,'0.13.0',%s,%s,%s,%s,%s,%s,'validation','running',%s,%s,%s)",
                (
                    attempt,
                    timestamp,
                    timestamp,
                    trusted_sha256,
                    sha(canonical(manifest)),
                    HEAD,
                    HEAD,
                    operator,
                    body.mode,
                    sha(canonical(verified)),
                    timestamp,
                    request_id,
                ),
            )
            comparator.preserved(original, snapshotter.snapshot(source), ledger=True)
            if (
                source.execute(
                    "UPDATE release_history SET version=version+1,updated_at=%s,finished_at=%s,"
                    "status='succeeded',phase='complete',result_code='DELIVERY_LOCAL_VERIFIED'"
                    " WHERE id=%s AND request_id=%s AND version=1 AND status='running'",
                    (timestamp, timestamp, attempt, request_id),
                ).rowcount
                != 1
            ):
                raise CommandError(409, "DELIVERY_LEDGER_CAS_FAILED")
            comparator.preserved(original, snapshotter.snapshot(source), ledger=True)
            if comparator.security_catalog(source) != security:
                raise CommandError(409, "DELIVERY_SECURITY_CHANGED")
            completed = {
                "state": "verified_pending_reopening",
                "release": str(attempt),
                "request_id": str(request_id),
                "head": HEAD,
                "instance": str(instance),
                "backup": verified,
                "schema_change": False,
                "bootstrap_changed": False,
                "artifact_sha256": trusted_sha256,
                "manifest_sha256": sha(canonical(manifest)),
                "maintenance_sha256": sha(marker),
            }
            completed["receipt_mac"] = hmac.digest(root, canonical(completed), "sha256").hex()
            write_private(evidence / "complete.json", canonical(completed))
            shutil.copyfile(artifact, evidence / "verified-artifact.zip")
            return {
                "head": HEAD,
                "state": "verified_pending_reopening",
                "maintenance_retained": True,
            }


def interactive_upgrade(arguments):
    body = Connection(
        mode=input("PostgreSQL mode (local/managed): "),
        host=input("Approved hostname: "),
        approved_address=input("Approved IP: "),
        port=int(input("Port: ")),
        database="ocoteAppDatabase",
        runtime_role="ocote_runtime",
        migrator_role="ocote_migrador",
        runtime_password=getpass.getpass("Runtime password (not saved): "),
        migrator_password=getpass.getpass("Migrator password (not saved): "),
        sslmode=input("Transport (disable/verify-full): "),
        ca_pem=Path(input("Public CA path: ")).read_text()
        if input("Managed TLS? (yes/no): ") == "yes"
        else "",
    )
    print(
        json.dumps(
            upgrade(
                body,
                artifact=arguments.artifact,
                trusted_sha256=arguments.trusted_sha256,
                restore_database=arguments.restore_database,
                pg_bin=arguments.pg_bin,
                evidence=arguments.evidence,
                maintenance=arguments.maintenance,
                operator=arguments.operator,
            )
        )
    )
