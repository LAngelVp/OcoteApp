import ipaddress
import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit
from uuid import UUID

from cryptography import x509
from ldap3.utils.dn import parse_dn
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from app.schemas.enterprise import Reauthenticated
from app.schemas.identity import Command, ExactSecret, Name, Reason, Version
from app.schemas.notifications import NetworkConfig
from app.schemas.operations import TaskUpdate


def https_url(value):
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.port not in (None, 443)
            or not value.isascii()
            or any(character.isspace() or ord(character) < 33 for character in value)
            or "\\" in value
            or any(segment in {".", ".."} for segment in unquote(parts.path).split("/"))
            or any(character in unquote(parts.path) for character in "\r\n\x00\\")
            or "%" in parts.netloc
        ):
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError(
            "An exact HTTPS endpoint without credentials or query is required"
        ) from None
    return value


def public_certificates(value):
    if value is None:
        return value
    try:
        certificates = x509.load_pem_x509_certificates(value.encode("ascii"))
        if not 1 <= len(certificates) <= 10 or "PRIVATE KEY" in value:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Public PEM certificates are required") from None
    return value


class ApprovedNetwork(NetworkConfig):
    allow_private_endpoint: StrictBool
    ca_certificates_pem: Annotated[str, Field(min_length=1, max_length=65536)] | None

    _certificates = field_validator("ca_certificates_pem")(public_certificates)

    @model_validator(mode="after")
    def private_network(self):
        if not self.allow_private_endpoint and any(
            not ipaddress.ip_address(address).is_global for address in self.approved_addresses
        ):
            raise ValueError("Private endpoints require explicit approval")
        if "." not in self.host or self.host.endswith("."):
            raise ValueError("An exact TLS hostname is required")
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            return self
        raise ValueError("An exact TLS hostname, not an IP literal, is required")


class HTTPSEndpoint(ApprovedNetwork):
    url: Annotated[str, Field(min_length=9, max_length=2048)]

    _url = field_validator("url")(https_url)

    @model_validator(mode="after")
    def exact_host(self):
        if urlsplit(self.url).hostname != self.host:
            raise ValueError("Endpoint hostname must match its approved network")
        return self


class JITMapping(Command):
    attribute: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:/-]+$")]
    value: Annotated[str, Field(min_length=1, max_length=512, pattern=r"^[^\r\n\x00]+$")]
    role: Literal["lider", "colaborador"]
    department_id: UUID


class SSOConfig(Command):
    emergency_admin_id: UUID
    revocation_window_seconds: Annotated[StrictInt, Field(ge=30, le=3600)]
    jit_enabled: StrictBool
    jit_mappings: Annotated[list[JITMapping], Field(max_length=20)]
    jit_email_attribute: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    jit_name_attribute: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @model_validator(mode="after")
    def explicit_jit(self):
        pairs = [(mapping.attribute, mapping.value) for mapping in self.jit_mappings]
        if self.jit_enabled != bool(pairs) or len(set(pairs)) != len(pairs):
            raise ValueError("JIT requires explicit, unique and proved department mappings")
        if self.jit_enabled and (
            self.jit_email_attribute is None or self.jit_name_attribute is None
        ):
            raise ValueError("JIT requires explicit email and display-name attribute mappings")
        return self

    @property
    def attribute_names(self):
        if not self.jit_enabled:
            return ()
        selected = {mapping.attribute for mapping in self.jit_mappings}
        selected.update(name for name in (self.jit_email_attribute, self.jit_name_attribute)
                        if name is not None)
        return tuple(sorted(selected))


class OIDCConfig(SSOConfig):
    provider: Literal["oidc"]
    issuer: Annotated[str, Field(min_length=9, max_length=512)]
    client_id: Annotated[str, Field(min_length=1, max_length=254)]
    authorization_endpoint: HTTPSEndpoint
    token_endpoint: HTTPSEndpoint
    jwks_endpoint: HTTPSEndpoint
    token_auth_method: Literal["client_secret_basic", "client_secret_post", "none"]

    _issuer = field_validator("issuer")(https_url)

    @model_validator(mode="after")
    def standard_verified_email(self):
        if self.jit_enabled and self.jit_email_attribute != "email":
            raise ValueError("OIDC JIT email must use the standard verified email claim")
        return self


class SAMLConfig(SSOConfig):
    provider: Literal["saml"]
    entity_id: Annotated[str, Field(min_length=1, max_length=512, pattern=r"^[^\s\x00]+$")]
    sso_endpoint: HTTPSEndpoint
    idp_certificate_pem: Annotated[str, Field(min_length=1, max_length=16384)]
    sp_certificate_pem: Annotated[str, Field(min_length=1, max_length=16384)]

    _certificates = field_validator("idp_certificate_pem", "sp_certificate_pem")(
        public_certificates
    )


class LDAPConfig(SSOConfig, ApprovedNetwork):
    provider: Literal["ldap"]
    port: Annotated[StrictInt, Field(ge=1, le=65535)]
    security: Literal["ldaps", "starttls"]
    bind_dn: Annotated[str, Field(min_length=1, max_length=1000)]
    user_search_base: Annotated[str, Field(min_length=1, max_length=1000)]
    username_attribute: Literal["uid", "sAMAccountName", "userPrincipalName"]
    subject_attribute: Literal["entryUUID", "objectGUID"]

    @model_validator(mode="after")
    def bounded_directory_attributes(self):
        if not set(self.attribute_names) <= {
            "memberOf", "department", "departmentNumber", "employeeType", "title", "ou",
            "userPrincipalName", "mail", "displayName", "givenName", "sn",
        }:
            raise ValueError("LDAP JIT attributes must use the fixed directory allowlist")
        return self

    @field_validator("bind_dn", "user_search_base")
    @classmethod
    def distinguished_name(cls, value):
        try:
            if not parse_dn(value, escape=True):
                raise ValueError
        except Exception:
            raise ValueError("An explicit LDAP distinguished name is required") from None
        return value


class Repository(Command):
    repository_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[1-9][0-9]*$")]
    path: Annotated[str, Field(min_length=3, max_length=512, pattern=r"^[a-zA-Z0-9_./-]+$")]

    @field_validator("path")
    @classmethod
    def exact_path(cls, value):
        segments = value.split("/")
        if len(segments) < 2 or any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("An exact repository path is required")
        return value


class DevOpsConfig(Command):
    provider: Literal["github", "gitlab"]
    api_endpoint: HTTPSEndpoint
    web_origin: Annotated[str, Field(min_length=9, max_length=512)]
    repositories: Annotated[list[Repository], Field(min_length=1, max_length=100)]

    _origin = field_validator("web_origin")(https_url)

    @model_validator(mode="after")
    def explicit_repositories(self):
        web = urlsplit(self.web_origin)
        api = urlsplit(self.api_endpoint.url)
        if web.path not in {"", "/"}:
            raise ValueError("An exact provider web origin is required")
        if self.provider == "github" and web.hostname == "github.com":
            if api.hostname != "api.github.com" or api.path not in {"", "/"}:
                raise ValueError("GitHub public API must use its official host")
            if any(repository.path.count("/") != 1 for repository in self.repositories):
                raise ValueError("GitHub repository paths require owner/repository")
        elif api.hostname != web.hostname:
            raise ValueError("Enterprise provider API and web origins must match")
        identifiers = [repository.repository_id for repository in self.repositories]
        paths = [repository.path.casefold() for repository in self.repositories]
        if len(set(identifiers)) != len(identifiers) or len(set(paths)) != len(paths):
            raise ValueError("Repository identities and paths must be unique")
        return self


class OutgoingWebhookConfig(Command):
    provider: Literal["outgoing_webhook"]
    endpoint: HTTPSEndpoint


ConnectorConfig = Annotated[
    OIDCConfig | SAMLConfig | LDAPConfig | DevOpsConfig | OutgoingWebhookConfig,
    Field(discriminator="provider"),
]


class ConnectorWrite(Reauthenticated):
    name: Name
    scope_kind: Literal["organization", "department"]
    department_id: UUID | None
    config: ConnectorConfig
    credential: Annotated[ExactSecret, Field(min_length=1, max_length=65536)] | None = None

    @model_validator(mode="after")
    def explicit_scope(self):
        if (self.scope_kind == "department") != (self.department_id is not None):
            raise ValueError("Explicit department scope required")
        return self


class ConnectorTest(Reauthenticated):
    confirmed: Literal[True]
    revocation_confirmed: StrictBool | None
    test_username: Annotated[str, Field(min_length=1, max_length=254)] | None
    test_password: Annotated[ExactSecret, Field(min_length=1, max_length=16384)] | None
    emergency_password: Annotated[ExactSecret, Field(min_length=1, max_length=128)] | None


class PrincipalWrite(Reauthenticated):
    name: Name
    department_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    approved_scopes: Annotated[list[Literal[
        "tasks:read", "tasks:create", "tasks:update_metadata", "subtasks:create",
        "notifications:dispatch",
    ]], Field(min_length=1, max_length=5)]
    is_active: StrictBool

    @model_validator(mode="after")
    def unique_delegation(self):
        if len(set(self.department_ids)) != len(self.department_ids) or len(
            set(self.approved_scopes)
        ) != len(self.approved_scopes):
            raise ValueError("Principal departments and scopes must be unique")
        return self


class APIKeyIssue(Reauthenticated):
    name: Name
    service_principal_id: UUID
    owner_user_id: UUID
    rate_per_minute: Annotated[StrictInt, Field(ge=1, le=1000)]
    scopes: Annotated[list[str], Field(min_length=1, max_length=3)]
    department_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    allowed_networks: Annotated[list[str], Field(min_length=1, max_length=100)] | None
    expires_at: datetime

    @field_validator("scopes")
    @classmethod
    def bounded_scopes(cls, values):
        from app.core.integration_security import API_SCOPES

        if len(set(values)) != len(values) or not set(values) <= API_SCOPES:
            raise ValueError("Explicit and unique service scopes required")
        return values

    @field_validator("department_ids")
    @classmethod
    def unique_departments(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Departments must be unique")
        return values

    @field_validator("allowed_networks")
    @classmethod
    def exact_networks(cls, values):
        if values is None:
            return values
        networks = [str(ipaddress.ip_network(value, strict=True)) for value in values]
        if len(set(networks)) != len(networks):
            raise ValueError("Networks must be unique")
        return networks

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware expiry required")
        return value


def branch_identifier(value):
    if (
        not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]{0,127}", value)
        or ".." in value
        or any(not part or part.startswith(".") or part.endswith((".", ".lock"))
               for part in value.split("/"))
    ):
        raise ValueError("An exact bounded branch name is required")
    return value


class ExternalLinkWrite(Command):
    expected_version: Version
    integration_id: UUID
    repository_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[1-9][0-9]*$")]
    external_id: Annotated[str, Field(min_length=1, max_length=128)]
    kind: Literal["issue", "pull_request", "merge_request", "commit", "branch"]
    reason: Reason

    @model_validator(mode="after")
    def canonical_identifier(self):
        if self.kind == "commit":
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.external_id):
                raise ValueError("An exact commit object identifier is required")
        elif self.kind == "branch":
            branch_identifier(self.external_id)
        elif not re.fullmatch(r"[1-9][0-9]*", self.external_id):
            raise ValueError("An exact positive provider identifier is required")
        return self


WebhookEvent = Literal[
    "dependency_changed", "impediment_changed", "comment_changed", "recurrence_generated",
    "assignment", "upcoming_due", "overdue", "due_date_request", "due_date_decision",
    "evaluation_finalized",
]


class WebhookSubscriptionWrite(Reauthenticated):
    integration_id: UUID
    owner_user_id: UUID
    event_types: Annotated[list[WebhookEvent], Field(min_length=1, max_length=10)]
    department_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    max_attempts: Annotated[StrictInt, Field(ge=1, le=10)]
    retry_base_seconds: Annotated[StrictInt, Field(ge=5, le=300)]
    max_delay_seconds: Annotated[StrictInt, Field(ge=300, le=86400)]
    enabled: StrictBool

    @model_validator(mode="after")
    def unique_scope(self):
        if len(set(self.event_types)) != len(self.event_types) or len(
            set(self.department_ids)
        ) != len(self.department_ids):
            raise ValueError("Explicit unique webhook events and departments required")
        return self


class WebhookReplay(Reauthenticated):
    delivery_id: UUID
    idempotency_key: UUID


class ExternalLinkDeactivate(Command):
    expected_version: Version
    reason: Reason


class ServiceTaskUpdate(TaskUpdate):
    reason: Reason


class SSOStart(Command):
    purpose: Literal["login", "bind", "probe"]
    current_password: Annotated[ExactSecret, Field(min_length=1, max_length=128)] | None

    @model_validator(mode="after")
    def binding_proof(self):
        if self.purpose in {"bind", "probe"} and self.current_password is None:
            raise ValueError("Binding requires fresh local reauthentication")
        return self


class SSOFinish(Command):
    transaction_id: UUID


class LDAPLogin(Command):
    transaction_id: UUID
    state: Annotated[str, Field(min_length=32, max_length=256)]
    username: Annotated[str, Field(min_length=1, max_length=254)]
    password: Annotated[ExactSecret, Field(min_length=1, max_length=16384)]