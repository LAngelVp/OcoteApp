import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from multiprocessing.connection import Client
from uuid import UUID, uuid4

from app.core.errors import CommandError

MAX_MESSAGE = 16384


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def envelope(payload, secret):
    if not isinstance(secret, bytes) or not 32 <= len(secret) <= 256:
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    message = canonical(payload)
    result = canonical({"payload": payload,
                        "mac": hmac.new(secret, message, hashlib.sha256).hexdigest()})
    if len(result) > MAX_MESSAGE:
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    return result


def decode(content, secret):
    try:
        if not isinstance(content, bytes) or len(content) > MAX_MESSAGE:
            raise ValueError
        value = json.loads(content)
        if set(value) != {"payload", "mac"} or not isinstance(value["payload"], dict):
            raise ValueError
        expected = hmac.new(secret, canonical(value["payload"]), hashlib.sha256).hexdigest()
        if not isinstance(value["mac"], str) or not hmac.compare_digest(expected, value["mac"]):
            raise ValueError
        return value["payload"]
    except (ValueError, TypeError, UnicodeError, KeyError):
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE") from None


def pipe_address(instance_id):
    return "\\\\.\\pipe\\OCOTE-operations-" + str(UUID(str(instance_id)))


def probe(instance_id, secret):
    if os.name != "nt":
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE")
    nonce = str(uuid4())
    payload = {"protocol_version": 1, "command": "probe", "instance_id": str(instance_id),
               "nonce": nonce, "issued_at": datetime.now(UTC).isoformat()}
    try:
        with Client(pipe_address(instance_id), family="AF_PIPE", authkey=None) as connection:
            connection.send_bytes(envelope(payload, secret))
            if not connection.poll(5):
                raise ValueError
            response = decode(connection.recv_bytes(MAX_MESSAGE), secret)
        if set(response) != {"protocol_version", "instance_id", "nonce", "capabilities"} or (
            response["protocol_version"] != 1 or response["instance_id"] != str(instance_id)
            or response["nonce"] != nonce or not isinstance(response["capabilities"], list)
            or not set(response["capabilities"]) <= {"backup", "restore_verify"}
        ):
            raise ValueError
        return response["capabilities"]
    except (OSError, EOFError, ValueError, TypeError):
        raise CommandError(503, "OPERATIONS_AGENT_UNAVAILABLE") from None