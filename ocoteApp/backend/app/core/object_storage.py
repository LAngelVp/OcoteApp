import base64
import hashlib
import hmac
import http.client
import ipaddress
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime
from urllib.parse import quote, urlsplit
from uuid import uuid4

from app.core.errors import CommandError

MAX_BODY = 10485760


def unavailable():
    return CommandError(503, "OBJECT_PROVIDER_UNAVAILABLE_OR_UNSAFE")


def endpoint_parts(endpoint):
    try:
        parts = urlsplit(endpoint)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in {"", "/"}
                or not 1 <= (parts.port or 443) <= 65535 or len(endpoint) > 2048):
            raise ValueError
        return parts
    except ValueError:
        raise CommandError(422, "INVALID_OBJECT_ENDPOINT") from None


def checked_addresses(host, port, approved, allow_private, resolver=socket.getaddrinfo):
    try:
        entries = resolver(host, port, type=socket.SOCK_STREAM)
        addresses = sorted({str(ipaddress.ip_address(entry[4][0])) for entry in entries})
        if not addresses or len(addresses) > 32:
            raise unavailable()
        approved = {str(ipaddress.ip_address(value)) for value in approved}
        for value in addresses:
            address = ipaddress.ip_address(value)
            if (value not in approved or address.is_link_local or address.is_multicast
                    or address.is_unspecified or address.is_reserved
                    or (address.version == 6 and address.ipv4_mapped)
                    or (not address.is_global and not allow_private)):
                raise unavailable()
        return addresses
    except (OSError, ValueError):
        raise unavailable() from None


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address, connect_timeout, read_timeout, *, context=None):
        super().__init__(
            host, port, timeout=connect_timeout, context=context or ssl.create_default_context()
        )
        self.address, self.read_timeout = address, read_timeout

    def connect(self):
        connection = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
            self.sock.settimeout(self.read_timeout)
        except Exception:
            connection.close()
            raise


def https_request(
    config, host, port, method, target, headers, content=b"", limit=MAX_BODY,
    *, reject_redirects=True,
):
    addresses = checked_addresses(host, port, config["approved_addresses"],
                                  config["allow_private_endpoint"])
    options = {}
    if config.get("ca_certificates_pem"):
        options["context"] = ssl.create_default_context(cadata=config["ca_certificates_pem"])
    connection = PinnedHTTPS(host, port, addresses[0], config["connect_timeout_seconds"],
                             config["read_timeout_seconds"], **options)
    try:
        connection.request(method, target, body=content, headers=headers)
        response = connection.getresponse()
        if reject_redirects and 300 <= response.status < 400:
            raise unavailable()
        content_length = response.getheader("Content-Length")
        if content_length and (not content_length.isdigit() or int(content_length) > limit):
            raise unavailable()
        body = response.read(limit + 1)
        if len(body) > limit:
            raise unavailable()
        return response.status, {key.lower(): value for key, value in response.getheaders()}, body
    except (OSError, ValueError, http.client.HTTPException):
        raise unavailable() from None
    finally:
        connection.close()


def query_string(values):
    return "&".join(quote(str(key), safe="-_.~") + "=" + quote(str(value), safe="-_.~")
                    for key, value in sorted(values.items()))


def s3_signature(method, path, query, host, region, credentials, content, moment):
    timestamp = moment.strftime("%Y%m%dT%H%M%SZ")
    day = timestamp[:8]
    digest = hashlib.sha256(content).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": digest, "x-amz-date": timestamp}
    if credentials.get("session_token"):
        headers["x-amz-security-token"] = credentials["session_token"]
    names = ";".join(sorted(headers))
    canonical_headers = "".join(name + ":" + headers[name].strip() + "\n"
                                for name in sorted(headers))
    canonical = "\n".join((method, path, query, canonical_headers, names, digest))
    scope = f"{day}/{region}/s3/aws4_request"
    message = "\n".join(("AWS4-HMAC-SHA256", timestamp, scope,
                          hashlib.sha256(canonical.encode()).hexdigest()))
    key = ("AWS4" + credentials["secret_key"]).encode()
    for component in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, component.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={credentials['access_key']}/{scope}, "
                                 f"SignedHeaders={names}, Signature={signature}")
    return headers


def azure_signature(method, path, query, account, account_key, content, moment, extra):
    headers = {"x-ms-date": format_datetime(moment, usegmt=True), "x-ms-version": "2023-11-03",
               **extra}
    canonical_headers = "".join(name + ":" + " ".join(value.split()) + "\n"
                                for name, value in sorted(headers.items())
                                if name.startswith("x-ms-"))
    resource = "/" + account + path + "".join("\n" + name.lower() + ":" + str(value)
                                              for name, value in sorted(query.items()))
    fields = [method, "", "", str(len(content)) if content else "", "", "", "", "", "", "", "", ""]
    message = "\n".join(fields) + "\n" + canonical_headers + resource
    try:
        key = base64.b64decode(account_key, validate=True)
        if not 32 <= len(key) <= 128:
            raise ValueError
    except (ValueError, TypeError):
        raise unavailable() from None
    signature = base64.b64encode(hmac.new(key, message.encode(), hashlib.sha256).digest()).decode()
    return headers | {"authorization": f"SharedKey {account}:{signature}"}


def safe_xml(content):
    if len(content) > 262144:
        raise unavailable()
    try:
        text = content.decode("utf-8")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper() or "\x00" in text:
            raise unavailable()
        return ET.fromstring(text)
    except (UnicodeError, ET.ParseError):
        raise unavailable() from None


class ObjectClient:
    def __init__(self, config, credentials, transport=https_request):
        self.config, self.credentials, self.transport = config, credentials, transport
        self.endpoint = endpoint_parts(config["endpoint"])

    def address(self, key):
        host, port = self.endpoint.hostname, self.endpoint.port or 443
        if self.config["provider"] == "s3":
            bucket = self.config["bucket"]
            if self.config["address_style"] == "virtual_hosted":
                host, path = bucket + "." + host, "/" + key
            else:
                path = "/" + bucket + ("/" + key if key else "")
        else:
            path = "/" + self.config["container"] + ("/" + key if key else "")
        return host, port, quote(path, safe="/-_.~")

    def request(self, method, key="", *, query=None, content=b"", extra=None, limit=MAX_BODY):
        query = query or {}
        host, port, path = self.address(key)
        host_header = ("[" + host + "]") if ":" in host else host
        host_header += (":" + str(port)) if port != 443 else ""
        moment = datetime.now(UTC)
        encoded_query = query_string(query)
        if self.config["provider"] == "s3":
            headers = s3_signature(method, path, encoded_query, host_header,
                                   self.config["region"], self.credentials, content, moment)
        else:
            headers = azure_signature(method, path, query, self.config["account_name"],
                                      self.credentials["account_key"], content, moment, extra or {})
        headers["host"] = host_header
        target = path + ("?" + encoded_query if encoded_query else "")
        try:
            return self.transport(self.config, host, port, method, target, headers, content, limit)
        except (OSError, ValueError, KeyError, TypeError):
            raise unavailable() from None

    def object_key(self, key, *, probe=False):
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise unavailable()
        return self.config["isolation_prefix"].rstrip("/") + (
            "/.ocote-probes/" if probe else "/objects/"
        ) + key

    def private(self):
        if not self.config["private_access_attested"]:
            raise unavailable()
        if self.config["provider"] == "s3":
            status, _, content = self.request("GET", query={"policyStatus": ""}, limit=262144)
            if status != 200:
                raise unavailable()
            policy = safe_xml(content)
            public = [entry for entry in policy if entry.tag.split("}")[-1] == "IsPublic"]
            if (policy.tag.split("}")[-1] != "PolicyStatus" or len(public) != 1
                    or public[0].text != "false"):
                raise unavailable()
            status, _, content = self.request("GET", query={"acl": ""}, limit=262144)
            if status != 200:
                raise unavailable()
            document = safe_xml(content)
            if document.tag.split("}")[-1] != "AccessControlPolicy":
                raise unavailable()
            for entry in document.iter():
                if entry.tag.split("}")[-1] == "URI" and entry.text and any(
                    name in entry.text for name in ("AllUsers", "AuthenticatedUsers")
                ):
                    raise unavailable()
        else:
            status, headers, content = self.request("GET", query={"restype": "container",
                                                                 "comp": "acl"}, limit=262144)
            if status != 200 or headers.get("x-ms-blob-public-access"):
                raise unavailable()
            if safe_xml(content).tag.split("}")[-1] != "SignedIdentifiers":
                raise unavailable()

    def write(self, key, content, *, probe=False):
        if len(content) > min(self.config["evidence_max_bytes"], MAX_BODY):
            raise CommandError(413, "PAYLOAD_TOO_LARGE")
        extra = {"x-ms-blob-type": "BlockBlob"} if self.config["provider"] == "azure_blob" else {}
        status, _, _ = self.request("PUT", self.object_key(key, probe=probe), content=content,
                                     extra=extra, limit=262144)
        if status not in {200, 201}:
            raise unavailable()

    def read(self, key, *, probe=False, limit=MAX_BODY):
        status, _, content = self.request("GET", self.object_key(key, probe=probe), limit=limit)
        if status != 200 or len(content) > limit:
            raise unavailable()
        return content

    def remove(self, key, *, probe=False):
        status, _, _ = self.request("DELETE", self.object_key(key, probe=probe), limit=262144)
        if status not in {200, 202, 204, 404}:
            raise unavailable()

    def probe(self):
        self.private()
        identity = uuid4().hex
        content = b"OCOTE synthetic storage probe " + identity.encode()
        attempted = False
        try:
            attempted = True
            self.write(identity, content, probe=True)
            if hashlib.sha256(self.read(identity, probe=True, limit=1024)).digest() != (
                hashlib.sha256(content).digest()
            ):
                raise unavailable()
        finally:
            if attempted:
                self.remove(identity, probe=True)