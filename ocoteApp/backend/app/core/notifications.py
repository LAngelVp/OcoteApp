import ipaddress
import json
import logging
import re
import smtplib
import socket
import ssl
from datetime import UTC, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from app.core.errors import CommandError
from app.core.object_storage import checked_addresses, https_request

TEST_MESSAGE = "OCOTE - PRUEBA DE CONEXION. Sin datos de negocio."
NOTICE_MESSAGE = "OCOTE: tienes una nueva notificacion. Abre tu bandeja privada."


class CalendarAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            target = record.args[2]
            if isinstance(target, str) and target.startswith(
                ("/api/v1/calendar-feeds/", "/api/v1/auth/sso/")
            ):
                arguments = list(record.args)
                arguments[2] = target.partition("?")[0]
                record.args = tuple(arguments)
        return True


def unavailable():
    return CommandError(503, "NOTIFICATION_PROVIDER_UNAVAILABLE_OR_UNSAFE")


def provider_target(config, credential):
    if config["provider"] == "telegram":
        if not re.fullmatch(r"[0-9]{5,20}:[A-Za-z0-9_-]{20,128}", credential):
            raise unavailable()
        return "api.telegram.org", 443, "/bot" + credential + "/sendMessage"
    try:
        parts = urlsplit(credential)
        if (
            len(credential) > 2048
            or parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.fragment
            or parts.hostname != config["host"]
            or (parts.port or 443) != 443
            or not parts.path
            or any(value in credential for value in "\r\n\x00")
        ):
            raise ValueError
        if config["provider"] == "slack" and (
            parts.hostname != "hooks.slack.com"
            or not parts.path.startswith("/services/")
            or parts.query
        ):
            raise ValueError
        if config["provider"] == "teams" and not any(
            parts.hostname.endswith(suffix)
            for suffix in (".webhook.office.com", ".logic.azure.com", ".api.powerplatform.com")
        ):
            raise ValueError
        return parts.hostname, 443, parts.path + ("?" + parts.query if parts.query else "")
    except (ValueError, TypeError):
        raise unavailable() from None


class PinnedSMTP(smtplib.SMTP):
    def __init__(self, config, address):
        self.address, self.read_timeout = address, config["read_timeout_seconds"]
        super().__init__(config["host"], config["port"], timeout=config["connect_timeout_seconds"])

    def _get_socket(self, host, port, timeout):
        connection = socket.create_connection((self.address, port), timeout)
        connection.settimeout(self.read_timeout)
        return connection


class PinnedSMTPSSL(PinnedSMTP):
    def _get_socket(self, host, port, timeout):
        connection = super()._get_socket(host, port, timeout)
        try:
            return ssl.create_default_context().wrap_socket(connection, server_hostname=host)
        except Exception:
            connection.close()
            raise


def smtp_send(config, credential, recipient, message, smtp_factory=None):
    addresses = checked_addresses(
        config["host"],
        config["port"],
        config["approved_addresses"],
        config["allow_private_endpoint"],
    )
    if any(ipaddress.ip_address(value).is_loopback for value in addresses):
        raise unavailable()
    factory = smtp_factory or (PinnedSMTPSSL if config["security"] == "tls" else PinnedSMTP)
    content = EmailMessage()
    content["From"] = formataddr((config["sender_name"], config["sender_email"]))
    content["To"] = recipient
    content["Subject"] = "OCOTE - Prueba" if message == TEST_MESSAGE else "OCOTE - Notificacion"
    content.set_content(message)
    with factory(config, addresses[0]) as client:
        client.ehlo()
        if config["security"] == "starttls":
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if config["authentication"] == "login":
            client.login(config["username"], credential)
        if client.send_message(content):
            raise unavailable()


def send(config, credential, *, recipient=None, test=False, transport=None, smtp_factory=None):
    message = TEST_MESSAGE if test else NOTICE_MESSAGE
    try:
        if config["provider"] == "smtp":
            if recipient is None:
                raise unavailable()
            smtp_send(config, credential, recipient, message, smtp_factory)
            return
        host, port, target = provider_target(config, credential)
        payload = {"text": message}
        if config["provider"] == "telegram":
            payload["chat_id"] = config["destination"]
        status, _headers, content = (transport or https_request)(
            config,
            host,
            port,
            "POST",
            target,
            {"content-type": "application/json"},
            json.dumps(payload).encode(),
            limit=16384,
        )
        if status not in {200, 202}:
            raise unavailable()
        if config["provider"] == "slack" and content.strip() != b"ok":
            raise unavailable()
        if config["provider"] == "telegram" and json.loads(content).get("ok") is not True:
            raise unavailable()
    except (CommandError, OSError, ValueError, TypeError, KeyError, smtplib.SMTPException):
        raise unavailable() from None


def quiet_until(moment, start, end, timezone):
    if start is None:
        return moment
    zone = ZoneInfo(timezone)
    local = moment.astimezone(zone)
    begins, finishes = time.fromisoformat(start), time.fromisoformat(end)
    clock = local.time().replace(tzinfo=None)
    silent = (
        begins <= clock < finishes if begins < finishes else clock >= begins or clock < finishes
    )
    if not silent:
        return moment
    day = local.date() + timedelta(days=int(begins > finishes and clock >= begins))
    boundary = datetime.combine(day, finishes, zone)
    return max(boundary.replace(fold=fold).astimezone(UTC) for fold in (0, 1))


def ical_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def fold_line(value):
    lines, current = [], ""
    for character in value:
        if len((current + character).encode("utf-8")) > 75:
            lines.append(current)
            current = " "
        current += character
    return "\r\n".join([*lines, current])


def calendar_content(tasks, moment):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OCOTE//F10 Calendar//ES",
        "CALSCALE:GREGORIAN",
    ]
    for task in tasks:
        for kind, field, label in (
            ("start", "start_date", "Inicio"),
            ("current", "due_date", "Vencimiento vigente"),
            ("original", "original_due_date", "Vencimiento original"),
        ):
            day = getattr(task, field)
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{task.id}-{kind}@ocote",
                    "DTSTAMP:" + moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
                    "DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d"),
                    "DTEND;VALUE=DATE:" + (day + timedelta(days=1)).strftime("%Y%m%d"),
                    "SUMMARY:" + ical_escape("OCOTE - " + label),
                    "END:VEVENT",
                ]
            )
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold_line(line) for line in lines) + "\r\n").encode("utf-8")
