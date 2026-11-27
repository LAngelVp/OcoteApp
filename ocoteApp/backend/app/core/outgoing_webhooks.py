from app.core.integration_http import exchange
from app.core.integration_security import webhook_signature
from app.schemas.integrations import OutgoingWebhookConfig


def send(config, secret, key_id, event_id, attempt_id, body, *, timestamp, transport=None):
    config = OutgoingWebhookConfig.model_validate(config)
    return exchange(
        config.endpoint, "POST", content=body, limit=65536, return_redirect=True,
        headers={
            "content-type": "application/json",
            "x-ocote-key-id": str(key_id), "x-ocote-event-id": str(event_id),
            "x-ocote-attempt-id": str(attempt_id), "x-ocote-schema-version": "1",
            "x-ocote-timestamp": str(timestamp),
            "x-ocote-signature": webhook_signature(secret.encode(), timestamp, body),
        },
        transport=transport,
    )