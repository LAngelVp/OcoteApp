import json
from urllib.parse import unquote, urlencode, urlsplit

import httpx
from authlib.integrations.httpx_client import OAuth2Client

from app.core.errors import CommandError
from app.core.federation import oidc_identity
from app.core.object_storage import https_request
from app.schemas.integrations import HTTPSEndpoint, OIDCConfig

MAX_BODY = 1048576


def unavailable():
    return CommandError(503, "INTEGRATION_PROVIDER_UNAVAILABLE_OR_UNSAFE")


def exchange(
    endpoint, method, *, suffix="", query=None, headers=None, content=b"",
    limit=MAX_BODY, transport=None, return_redirect=False,
):
    try:
        endpoint = HTTPSEndpoint.model_validate(endpoint)
        if (
            not endpoint.audience_approved
            or method not in {"GET", "POST"}
            or not isinstance(content, bytes)
            or len(content) > MAX_BODY
            or not 1 <= limit <= MAX_BODY
            or suffix and not suffix.startswith("/")
            or any(character in suffix for character in "?#\\\r\n\x00")
            or any(segment in {".", ".."} for segment in unquote(suffix).split("/"))
            or any(character in unquote(suffix) for character in "\\\r\n\x00")
        ):
            raise ValueError
        parts = urlsplit(endpoint.url)
        target = (parts.path.rstrip("/") + suffix if suffix else parts.path) or "/"
        if target.startswith("//"):
            raise ValueError
        if query:
            target += "?" + urlencode(query)
        options = {"reject_redirects": False} if return_redirect else {}
        status, response_headers, body = (transport or https_request)(
            endpoint.model_dump(), endpoint.host, 443, method, target,
            {"accept": "application/json", **(headers or {}), "host": endpoint.host},
            content, limit, **options,
        )
        if not isinstance(body, bytes) or len(body) > limit:
            raise ValueError
        if not return_redirect and 300 <= status < 400:
            raise ValueError
        return status, response_headers, body
    except Exception:
        raise unavailable() from None


class OAuthTransport(httpx.BaseTransport):
    def __init__(self, endpoint, transport=None):
        self.endpoint = HTTPSEndpoint.model_validate(endpoint)
        self.transport = transport

    def handle_request(self, request):
        expected, received = urlsplit(self.endpoint.url), urlsplit(str(request.url))
        if (
            received.scheme != "https"
            or received.hostname != expected.hostname
            or (received.port or 443) != 443
            or (received.path or "/") != (expected.path or "/")
            or received.query
            or received.fragment
            or received.username is not None
            or request.method != "POST"
        ):
            raise unavailable()
        status, headers, body = exchange(
            self.endpoint, "POST", headers=dict(request.headers), content=request.read(),
            transport=self.transport,
        )
        return httpx.Response(status, headers=headers, content=body)


def oidc_authorization(config, *, redirect_uri, state, nonce, verifier):
    try:
        config = OIDCConfig.model_validate(config)
        if not all(endpoint.audience_approved for endpoint in (
            config.authorization_endpoint, config.token_endpoint, config.jwks_endpoint
        )):
            raise ValueError
        with OAuth2Client(
            config.client_id, redirect_uri=redirect_uri,
            scope="openid profile email" if config.jit_enabled else "openid",
            code_challenge_method="S256",
        ) as client:
            url, returned_state = client.create_authorization_url(
                config.authorization_endpoint.url, state=state, nonce=nonce,
                code_verifier=verifier, prompt="login", max_age=0,
            )
        if returned_state != state:
            raise ValueError
        return url
    except Exception:
        raise unavailable() from None


def oidc_exchange(
    config, credential, *, redirect_uri, code, verifier, nonce, transport=None,
):
    try:
        config = OIDCConfig.model_validate(config)
        if not isinstance(code, str) or not 1 <= len(code) <= 8192:
            raise ValueError
        if not isinstance(verifier, str) or not 43 <= len(verifier) <= 128:
            raise ValueError
        if config.token_auth_method != "none" and not credential:
            raise ValueError
        with OAuth2Client(
            config.client_id, client_secret=credential, redirect_uri=redirect_uri,
            token_endpoint_auth_method=config.token_auth_method,
            transport=OAuthTransport(config.token_endpoint, transport),
            follow_redirects=False,
        ) as client:
            token = client.fetch_token(
                config.token_endpoint.url, grant_type="authorization_code", code=code,
                code_verifier=verifier, redirect_uri=redirect_uri,
            )
        status, headers, body = exchange(config.jwks_endpoint, "GET", transport=transport)
        if status != 200 or "application/json" not in headers.get("content-type", "").lower():
            raise ValueError
        jwks = json.loads(body)
        encoded = token.get("id_token")
        access_token = token.get("access_token")
        if access_token is not None and (
            not isinstance(access_token, str) or not 1 <= len(access_token) <= 16384
        ):
            raise ValueError
        return oidc_identity(
            encoded, jwks, issuer=config.issuer, client_id=config.client_id,
            nonce=nonce, access_token=access_token,
            attribute_names=config.attribute_names,
        )
    except Exception:
        raise CommandError(401, "FEDERATED_IDENTITY_INVALID") from None