import hashlib
import hmac
import json
import re
from urllib.parse import quote

from app.core.errors import CommandError
from app.core.integration_http import MAX_BODY, exchange, unavailable
from app.schemas.integrations import DevOpsConfig, branch_identifier


def identifier(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,127}", str(value)):
        raise ValueError
    return str(value)


def repository(config, repository_id):
    matches = [item for item in config.repositories if item.repository_id == str(repository_id)]
    if len(matches) != 1:
        raise CommandError(404, "EXTERNAL_REPOSITORY_NOT_APPROVED")
    return matches[0]


def api_document(config, credential, suffix, *, transport=None):
    if not isinstance(credential, str) or not 1 <= len(credential) <= 16384:
        raise unavailable()
    status, headers, body = exchange(
        config.api_endpoint,
        "GET",
        suffix=suffix,
        headers={"authorization": "Bearer " + credential},
        transport=transport,
    )
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if status != 200 or not (media_type == "application/json" or media_type.endswith("+json")):
        raise unavailable()
    document = json.loads(body)
    if not isinstance(document, dict):
        raise unavailable()
    return document


def projection(document):
    result = {}
    for key in ("state", "title", "updated_at"):
        value = document.get(key)
        maximum = 2000 if key == "title" else 80
        if value is not None:
            if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
                raise ValueError
            result[key] = value
    return result


def verified_repository(config, credential, approved, *, transport=None):
    github = config.provider == "github"
    prefix = ("/repos/" + quote(approved.path, safe="/") if github
              else "/projects/" + approved.repository_id)
    document = api_document(config, credential, prefix, transport=transport)
    path = document.get("full_name" if github else "path_with_namespace", "")
    if identifier(document.get("id")) != approved.repository_id or (
        not isinstance(path, str) or path.casefold() != approved.path.casefold()
    ):
        raise ValueError
    return prefix


def verify_repositories(config, credential, *, transport=None):
    try:
        config = DevOpsConfig.model_validate(config)
        for approved in config.repositories:
            verified_repository(config, credential, approved, transport=transport)
    except Exception:
        raise CommandError(422, "DEVOPS_REPOSITORIES_UNVERIFIED") from None


def external_reference(config, credential, repository_id, kind, external_id, *, transport=None):
    try:
        config = DevOpsConfig.model_validate(config)
        approved = repository(config, repository_id)
        if kind == "commit":
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", external_id):
                raise ValueError
        elif kind == "branch":
            external_id = branch_identifier(external_id)
        else:
            external_id = identifier(external_id)
        if config.provider == "github":
            resources = {"issue": "issues", "pull_request": "pulls", "commit": "commits",
                         "branch": "branches"}
            public_paths = {"issue": "issues", "pull_request": "pull", "commit": "commit",
                            "branch": "tree"}
            resource = resources[kind]
            prefix = verified_repository(config, credential, approved, transport=transport)
            document = api_document(
                config,
                credential,
                prefix + "/" + resource + "/" + quote(external_id, safe=""),
                transport=transport,
            )
            if kind == "commit":
                if document.get("sha") != external_id:
                    raise ValueError
            elif kind == "branch":
                if document.get("name") != external_id:
                    raise ValueError
            elif (
                identifier(document.get("number")) != external_id
                or kind == "issue"
                and "pull_request" in document
            ):
                raise ValueError
            url = config.web_origin.rstrip("/") + "/" + approved.path
            url += "/" + public_paths[kind] + "/" + quote(external_id, safe="")
        else:
            resources = {
                "issue": "issues",
                "merge_request": "merge_requests",
                "commit": "repository/commits",
                "branch": "repository/branches",
            }
            public_paths = {
                "issue": "issues",
                "merge_request": "merge_requests",
                "commit": "commit",
                "branch": "tree",
            }
            resource = resources[kind]
            prefix = verified_repository(config, credential, approved, transport=transport)
            document = api_document(
                config,
                credential,
                prefix + "/" + resource + "/" + quote(external_id, safe=""),
                transport=transport,
            )
            if kind == "commit":
                if document.get("id") != external_id:
                    raise ValueError
            elif kind == "branch":
                if document.get("name") != external_id:
                    raise ValueError
            elif (
                identifier(document.get("iid")) != external_id
                or identifier(document.get("project_id")) != approved.repository_id
            ):
                raise ValueError
            url = config.web_origin.rstrip("/") + "/" + approved.path
            url += "/-/" + public_paths[kind] + "/" + quote(external_id, safe="")
        return {"canonical_url": url, "safe_projection": projection(document)}
    except Exception:
        raise CommandError(422, "EXTERNAL_REFERENCE_UNVERIFIED") from None


def inbound_event(config, credential, headers, body):
    try:
        config = DevOpsConfig.model_validate(config)
        if (
            not isinstance(body, bytes)
            or not 1 <= len(body) <= MAX_BODY
            or not isinstance(credential, str)
            or not 16 <= len(credential.encode()) <= 1024
        ):
            raise ValueError
        headers = {key.lower(): value for key, value in headers.items()}
        if config.provider == "github":
            expected = "sha256=" + hmac.new(credential.encode(), body, hashlib.sha256).hexdigest()
            received = headers.get("x-hub-signature-256", "")
            if not isinstance(received, str) or not hmac.compare_digest(received, expected):
                raise ValueError
            delivery = headers.get("x-github-delivery", "")
            event = headers.get("x-github-event", "")
        else:
            received = headers.get("x-gitlab-token", "")
            if not isinstance(received, str) or not hmac.compare_digest(
                received.encode(), credential.encode()
            ):
                raise ValueError
            delivery = headers.get("x-gitlab-event-uuid", "")
            event = headers.get("x-gitlab-event", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", delivery):
            raise ValueError
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError
        if config.provider == "github":
            approved = repository(config, identifier(payload["repository"]["id"]))
            if event == "issues":
                document, kind = payload["issue"], "issue"
                external_id = identifier(document["number"])
                if "pull_request" in document:
                    raise ValueError
            elif event == "pull_request":
                document, kind = payload["pull_request"], "pull_request"
                external_id = identifier(document["number"])
                if identifier(document["base"]["repo"]["id"]) != approved.repository_id:
                    raise ValueError
            elif event == "push":
                document, kind, external_id = {}, "commit", payload["after"]
            else:
                raise ValueError
        else:
            approved = repository(config, identifier(payload["project"]["id"]))
            document = payload.get("object_attributes", {})
            if event in {"Issue Hook", "Merge Request Hook"}:
                kind = "issue" if event == "Issue Hook" else "merge_request"
                external_id = identifier(document["iid"])
                if (
                    identifier(document.get("target_project_id", document.get("project_id")))
                    != approved.repository_id
                ):
                    raise ValueError
            elif event == "Push Hook":
                document, kind, external_id = {}, "commit", payload["after"]
            else:
                raise ValueError
        if kind == "commit" and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", external_id):
            raise ValueError
        return {
            "delivery_id": delivery,
            "body_hash": hashlib.sha256(body).hexdigest(),
            "event_type": event,
            "safe_projection": {
                "repository_id": approved.repository_id,
                "external_id": external_id,
                "kind": kind,
                **projection(document),
            },
        }
    except Exception:
        raise CommandError(401, "DEVOPS_EVENT_INVALID") from None
