import json
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as XML

from app.services.installation import canonical


def task(name, executable, arguments, periodic=False):
    root = XML.Element(
        "Task", {"version": "1.4", "xmlns": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    )
    registration = XML.SubElement(root, "RegistrationInfo")
    XML.SubElement(registration, "Description").text = name + " - customer-approved template only"
    triggers = XML.SubElement(root, "Triggers")
    trigger = XML.SubElement(triggers, "TimeTrigger" if periodic else "BootTrigger")
    if periodic:
        repetition = XML.SubElement(trigger, "Repetition")
        XML.SubElement(repetition, "Interval").text = "__APPROVED_ISO_INTERVAL__"
        XML.SubElement(trigger, "StartBoundary").text = "__APPROVED_START_ISO__"
    XML.SubElement(trigger, "Enabled").text = "true"
    principals = XML.SubElement(root, "Principals")
    principal = XML.SubElement(principals, "Principal", {"id": "Operator"})
    XML.SubElement(principal, "UserId").text = "__DEDICATED_SERVICE_ACCOUNT__"
    XML.SubElement(principal, "LogonType").text = "Password"
    XML.SubElement(principal, "RunLevel").text = "LeastPrivilege"
    settings = XML.SubElement(root, "Settings")
    XML.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    XML.SubElement(settings, "StartWhenAvailable").text = "true"
    XML.SubElement(settings, "ExecutionTimeLimit").text = (
        "__APPROVED_EXECUTION_ISO_BUDGET__" if periodic else "PT0S"
    )
    restart = XML.SubElement(settings, "RestartOnFailure")
    XML.SubElement(restart, "Interval").text = "PT1M"
    XML.SubElement(restart, "Count").text = "3"
    actions = XML.SubElement(root, "Actions", {"Context": "Operator"})
    execute = XML.SubElement(actions, "Exec")
    XML.SubElement(execute, "Command").text = executable
    XML.SubElement(execute, "Arguments").text = arguments
    XML.SubElement(execute, "WorkingDirectory").text = "__IMMUTABLE_RELEASE__\\backend"
    return XML.tostring(root, encoding="utf-8", xml_declaration=True)


def templates():
    signed = (
        '--artifact "__APPROVED_ZIP__" --signature "__DETACHED_SIGNATURE__" '
        '--public-key "__INDEPENDENT_TRUST_ANCHOR__"'
    )
    values = {
        "operations/api.task.xml.template": task(
            "OCOTE API (owned portable PostgreSQL first when sealed Local)",
            "__PYTHON_EXE__",
            '-m tools.delivery runtime --state "__PRIVATE_STATE__" --port __INTERNAL_PORT__ '
            '--behind-approved-proxy --log-file "__PRIVATE_TECHNICAL_LOG_DIR__\\api.log" '
            "--log-max-bytes 10485760 --log-files __APPROVED_TECHNICAL_LOG_COUNT__ " + signed,
        )
    }
    for mode in ("recurrence", "notifications", "webhooks"):
        principal = "" if mode == "recurrence" else " --principal __APPROVED_PRINCIPAL_UUID__"
        values["operations/" + mode + ".task.xml.template"] = task(
            "OCOTE " + mode,
            "__PYTHON_EXE__",
            '-m tools.delivery_worker --state "__PRIVATE_STATE__" '
            '--maintenance "__PRIVATE_STATE__\\maintenance.json" --mode '
            + mode
            + principal
            + " --limit 100 "
            + signed,
            periodic=True,
        )
    for action in ("backup", "restore-verify"):
        values["operations/" + action + ".task.xml.template"] = task(
            "OCOTE " + action,
            "__APPROVED_OPERATIONS_AGENT_EXE__",
            action + ' --profile "__PRIVATE_AGENT_PROFILE__" '
            '--off-host "__APPROVED_OFF_HOST_UNC__" --receipt "__PRIVATE_JOB_RECEIPT__"',
            periodic=True,
        )
    values["operations/customer-profile.json.template"] = canonical(
        {
            "instance": "__SEALED_INSTANCE_UUID__",
            "primary_custodian": "__CLIENT_PRIMARY__",
            "secondary_custodian": "__CLIENT_INDEPENDENT_SECONDARY__",
            "off_host_destination": "__APPROVED_UNC_NOT_LOCAL_DISK__",
            "backup_schedule": "__APPROVED_DAILY_WINDOW__",
            "restore_schedule": "__APPROVED_MONTHLY_WINDOW_AND_EACH_RELEASE__",
            "rpo_goal_seconds": 86400,
            "rto_goal_seconds": 14400,
            "automatic_historical_purge": False,
            "service_identity": "__DEDICATED_ACCOUNT__",
            "operations_agent": "__SEPARATELY_APPROVED_BACKUP_RESTORE_AGENT__",
            "readiness_exception": "monitor-token-only; writes remain fenced by maintenance",
            "portable_postgres": {"startup": "runtime and workers ensure owned cluster first",
                                   "data_directory": "__SEALED_PRIVATE_DATA_DIRECTORY__",
                                   "initdb_at_boot": False, "superuser_in_runtime": False},
        }
    )
    values["operations/README.md"] = (
        "# Customer Operations Templates\n\n"
        "Templates only. Replace every __PLACEHOLDER__ under approved change control.\n"
        "Do not import tasks or install a service on the developer host.\n"
        "API uses native Task Scheduler with restart-on-failure and a dedicated account.\n"
        "Sealed Local portable starts its owned PostgreSQL before API and worker SQL.\n"
        "Never schedule initdb or copy a developer cluster; external PostgreSQL is not started.\n"
        "Worker passes use runtime only, bounded limits, approved principals "
        "and maintenance fencing.\n"
        "Backup/restore tasks require the separately approved operations agent "
        "and private profile;\n"
        "they are not an installed daemon or permission to run historical migration helpers.\n"
        "Keep secrets in the OS store/private credential manager, "
        "never task XML or CLI arguments.\n"
        "Use a dedicated least-privilege service account, not SYSTEM or an interactive developer.\n"
        "Import XML through Task Scheduler with credentials entered directly in its trusted UI.\n"
        "Set API --log-file/--log-max-bytes/--log-files for private rotating technical logs.\n"
        "Approve task budgets separately for workers, backups and measured restores.\n"
        "Use Event Log retention/forwarding for scheduler events; "
        "configure bounded technical logs\n"
        "with archival off-host. Never rotate/delete business audit history "
        "as technical log cleanup.\n"
        "Off-host backup must copy authenticated ciphertext, wrapped keys "
        "and consistent evidence;\n"
        "verify destination checksum, key recovery by both custodians "
        "and isolated restore receipts.\n"
        "Record backup data-as-of/incident/restore start/finish in UTC and measure RPO/RTO.\n"
        "A daily schedule alone is not proof of off-host recoverability or an achieved RPO/RTO.\n"
    ).encode("ascii")
    return values


def record_restore(proof, output, rpo_goal, rto_goal):
    record = json.loads(Path(proof).read_text())
    if record.get("restore_verified") is not True or not record.get("isolated_target_uuid"):
        raise ValueError("An actual verified isolated restore receipt is required")
    target = UUID(record["isolated_target_uuid"])
    UUID(record["instance"])
    if record.get("target_database") != "ocote_f2_restore_" + target.hex or any(
        not re.fullmatch(r"[a-f0-9]{64}", record.get(field, ""))
        for field in ("backup_sha256", "encrypted_backup_sha256")
    ):
        raise ValueError("Isolated destination and backup evidence are required")
    moments = {
        name: datetime.fromisoformat(record[name])
        for name in (
            "restore_started_at",
            "restore_finished_at",
            "incident_at",
            "recoverable_data_at",
        )
    }
    if any(value.tzinfo is None for value in moments.values()):
        raise ValueError("Restore measurements require timezone-aware timestamps")
    rto = (moments["restore_finished_at"] - moments["restore_started_at"]).total_seconds()
    rpo = (moments["incident_at"] - moments["recoverable_data_at"]).total_seconds()
    if min(rto, rpo, rpo_goal, rto_goal) < 0:
        raise ValueError("Invalid recovery measurement")
    result = {
        "instance": record["instance"],
        "isolated_target_uuid": record["isolated_target_uuid"],
        "rpo_seconds": rpo,
        "rto_seconds": rto,
        "rpo_goal_seconds": rpo_goal,
        "rto_goal_seconds": rto_goal,
        "goals_met": rpo <= rpo_goal and rto <= rto_goal,
        "measurement_source": "operator-supplied verified restore agent receipt",
    }
    with Path(output).open("xb") as stream:
        stream.write(canonical(result))
    return result
