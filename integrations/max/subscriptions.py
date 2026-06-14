"""MAX webhook subscription management."""

from __future__ import annotations

import logging

from integrations.max.client import MaxApiError, MaxClient
from integrations.max.config import MaxSettings
from integrations.max.constants import UPDATE_TYPES

logger = logging.getLogger(__name__)


def webhook_ready(settings: MaxSettings) -> bool:
    return (
        bool(settings.access_token.strip())
        and settings.is_webhook_mode
        and bool(settings.webhook_url.strip())
    )


async def register_webhook(settings: MaxSettings, client: MaxClient | None = None) -> bool:
    """Subscribe MAX bot to webhook updates. Returns True on success."""
    url = settings.webhook_url.strip()
    if not url:
        logger.warning("HELIX_MAX_WEBHOOK_URL is not set — webhook subscription skipped")
        return False

    owns_client = client is None
    if client is None:
        client = MaxClient(settings.access_token)
        await client._ensure_session()

    secret = settings.webhook_secret.strip() or None
    try:
        result = await client.subscribe_webhook(
            url,
            update_types=UPDATE_TYPES,
            secret=secret,
        )
        if result.get("success") is False:
            logger.error("MAX webhook subscription failed: %s", result.get("message"))
            return False
        logger.info("MAX webhook subscribed: %s", url)
        return True
    except MaxApiError as exc:
        logger.error("MAX webhook subscription error: %s", exc)
        return False
    finally:
        if owns_client:
            await client.close()


async def unregister_webhook(settings: MaxSettings, client: MaxClient | None = None) -> None:
    url = settings.webhook_url.strip()
    if not url or not settings.access_token.strip():
        return

    owns_client = client is None
    if client is None:
        client = MaxClient(settings.access_token)
        await client._ensure_session()

    try:
        await client.delete_subscription(url)
        logger.info("MAX webhook unsubscribed: %s", url)
    except MaxApiError as exc:
        logger.warning("MAX webhook unsubscribe failed: %s", exc)
    finally:
        if owns_client:
            await client.close()