"""MAX webhook routes and gateway lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from integrations.max.client import MaxClient
from integrations.max.config import MaxSettings, load_max_settings
from integrations.max.constants import WEBHOOK_PATH, WEBHOOK_SECRET_HEADER
from integrations.max.env_store import load_max_env_files
from integrations.max.subscriptions import register_webhook, unregister_webhook
from integrations.max.webhook import MaxWebhookHandler

logger = logging.getLogger(__name__)


@dataclass
class MaxGatewayState:
    settings: MaxSettings
    handler: MaxWebhookHandler
    client: MaxClient
    subscribed: bool = False


_state: MaxGatewayState | None = None


def max_enabled(profile: str = "default") -> bool:
    load_max_env_files()
    return bool(load_max_settings(profile).access_token.strip())


def max_should_webhook(profile: str = "default") -> bool:
    load_max_env_files()
    settings = load_max_settings(profile)
    return max_enabled(profile) and settings.is_webhook_mode


def max_should_poll(profile: str = "default") -> bool:
    """True when MAX token is set and mode is polling (default outside production)."""
    load_max_env_files()
    settings = load_max_settings(profile)
    return max_enabled(profile) and not settings.is_webhook_mode


def max_gateway_state() -> MaxGatewayState | None:
    return _state


async def init_max_webhook(profile: str | None = None) -> MaxGatewayState | None:
    global _state

    load_max_env_files()
    profile = profile or os.getenv("HELIX_PROFILE", "default")
    settings = load_max_settings(profile)

    if not settings.access_token.strip():
        logger.debug("MAX webhook disabled (no access token)")
        return None

    if not settings.is_webhook_mode:
        logger.info(
            "MAX webhook disabled (mode=%s). Long Polling runs as a gateway companion.",
            settings.mode,
        )
        return None

    if not settings.webhook_url.strip():
        logger.warning(
            "MAX webhook mode enabled but HELIX_MAX_WEBHOOK_URL is empty — "
            "set URL and restart gateway"
        )
        return None

    client = MaxClient(settings.access_token)
    await client._ensure_session()
    handler = MaxWebhookHandler(settings, client=client)
    try:
        await handler._bot.warmup()
    except Exception:
        logger.exception("Failed to initialize Helix agent for MAX webhook")
        await client.close()
        raise

    try:
        from core.i18n import LocaleStore

        from integrations.max.commands import register_bot_commands

        locale = LocaleStore(profile).get()
        registered = await register_bot_commands(client, locale=locale)
        if registered:
            logger.info("MAX menu: %d commands", len(registered))
    except Exception:
        logger.exception("Failed to sync MAX command menu")
    subscribed = await register_webhook(settings, client=client)

    _state = MaxGatewayState(
        settings=settings,
        handler=handler,
        client=client,
        subscribed=subscribed,
    )
    if subscribed:
        logger.info("MAX webhook ready at %s", settings.webhook_url)
    return _state


async def shutdown_max_webhook() -> None:
    global _state
    if _state is None:
        return

    if _state.subscribed:
        await unregister_webhook(_state.settings, client=_state.client)
    await _state.handler.close()
    await _state.client.close()
    _state = None


async def reload_max_webhook(profile: str | None = None) -> dict[str, Any]:
    """Re-read MAX env and re-register webhook subscription (gateway host profile)."""
    load_max_env_files()
    profile = profile or os.getenv("HELIX_PROFILE", "default")
    settings = load_max_settings(profile)
    await shutdown_max_webhook()
    state = await init_max_webhook(profile)
    return {
        "max_configured": max_enabled(profile),
        "max_webhook": bool(state and state.subscribed),
        "max_polling": max_should_poll(profile),
        "max_mode": settings.mode,
    }


def register_max_routes(app: FastAPI) -> None:
    @app.post(WEBHOOK_PATH)
    async def max_webhook(request: Request) -> dict[str, bool]:
        state = _state
        if state is None:
            raise HTTPException(status_code=503, detail="MAX webhook is not configured")

        secret = request.headers.get(WEBHOOK_SECRET_HEADER)
        if not state.handler.verify_secret(secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")

        update: dict[str, Any] = body
        asyncio.create_task(_dispatch_update(state.handler, update))
        return {"ok": True}


async def _dispatch_update(handler: MaxWebhookHandler, update: dict[str, Any]) -> None:
    try:
        await handler.handle_update(update)
    except Exception:
        logger.exception("Failed to handle MAX webhook update")