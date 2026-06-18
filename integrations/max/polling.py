"""Long Polling worker for MAX (dev/test only)."""

from __future__ import annotations

import asyncio
import logging

from integrations.max.bot import HelixMaxBot
from integrations.max.client import MaxApiError, MaxClient
from integrations.max.config import MaxSettings, load_max_settings

logger = logging.getLogger(__name__)

POLL_TYPES = [
    "bot_started",
    "message_created",
    "message_callback",
]


async def run_polling(settings: MaxSettings | None = None, *, profile: str = "default") -> None:
    settings = settings or load_max_settings(profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not set. Run: holix max setup")
    if not settings.can_start_without_allowlist() and not settings.allowed_user_ids.strip():
        raise RuntimeError(
            "Set HOLIX_MAX_ALLOWED_USERS or enable HOLIX_MAX_ACCESS_REQUESTS / HOLIX_MAX_ALLOW_ALL"
        )

    bot = HelixMaxBot(settings, profile=profile)
    marker: int | None = None

    # Separate clients: long-poll must not block send/edit during agent runs.
    async with MaxClient(token) as poll_client, MaxClient(token) as api_client:
        try:
            await bot.warmup()
        except Exception:
            logger.exception("Failed to initialize Helix agent")
            raise

        try:
            import asyncio

            from integrations.messenger.locale import (
                bootstrap_messenger_locales,
                messenger_locale,
            )
            from integrations.messenger.platforms import MAX_PLATFORM

            from integrations.max.commands import register_bot_commands

            await asyncio.to_thread(
                bootstrap_messenger_locales,
                MAX_PLATFORM,
                settings.profile,
            )
            locale = messenger_locale(settings.profile)
            registered = await register_bot_commands(api_client, locale=locale)
            if registered:
                logger.info("MAX menu: %d commands", len(registered))
        except Exception:
            logger.exception("Failed to sync MAX command menu")

        logger.info("MAX Long Polling started (profile=%s)", settings.profile)
        while True:
            try:
                payload = await poll_client.get_updates(
                    marker=marker,
                    limit=100,
                    timeout=settings.poll_timeout_s,
                    types=POLL_TYPES,
                )
            except MaxApiError as exc:
                logger.warning("MAX polling error: %s", exc)
                await asyncio.sleep(2.0)
                continue

            next_marker = payload.get("marker")
            if isinstance(next_marker, int):
                marker = next_marker

            updates = payload.get("updates")
            if not isinstance(updates, list):
                continue
            if updates:
                logger.info("MAX received %d update(s)", len(updates))
            for update in updates:
                if isinstance(update, dict):
                    try:
                        await bot.handle_update(api_client, update)
                    except Exception:
                        logger.exception("Failed to handle MAX update")