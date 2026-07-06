"""Background sub-agent result delivery for Telegram chats."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.telegram.markdown import (
    plain_to_telegram_html,
    split_telegram_html,
)

logger = logging.getLogger(__name__)


def pin_subagent_agent(session: Any, agent: Any) -> None:
    """Remember which agent instance owns spawned sub-agents for this chat."""
    session.subagent_owner = agent


def resolve_subagent_agent(host: Any) -> Any:
    """Prefer the agent that spawned sub-agents; fall back to host.agent."""
    session = getattr(host, "_session", None)
    if session is not None:
        owner = getattr(session, "subagent_owner", None)
        if owner is not None:
            return owner
    return getattr(host, "agent", None)


class TelegramSubagentDeliveryHost:
    """Minimal host adapter for shared subagent_commands delivery."""

    def __init__(self, bot: Any, session: Any, agent: Any) -> None:
        self._bot = bot
        self._session = session
        self._agent = agent

    @property
    def agent(self) -> Any:
        return self._agent

    def transcript_write(self, content: object) -> None:
        from cli.shared.rich_text import content_to_plain_text

        text = content_to_plain_text(content)
        if text:
            asyncio.create_task(send_long_text(self._bot, self._session.chat_id, text))

    async def _send_split_plain(self, text: str) -> None:
        await send_long_text(self._bot, self._session.chat_id, text)


async def send_long_text(bot: Any, chat_id: int, text: str) -> bool:
    """Deliver long assistant text; HTML first, then plain fallback."""
    body = (text or "").strip()
    if not body:
        return False

    try:
        html = plain_to_telegram_html(body)
        chunks = split_telegram_html(html) or [html]
        for chunk in chunks:
            if not (chunk or "").strip():
                continue
            await bot.send_message(chat_id, chunk, parse_mode="HTML")
            await asyncio.sleep(0.06)
        return True
    except Exception as exc:
        logger.warning(
            "Telegram HTML delivery failed (chat=%s, %d chars): %s",
            chat_id,
            len(body),
            exc,
        )

    try:
        await bot.send_message(chat_id, body[:3900])
        return True
    except Exception as exc:
        logger.error(
            "Telegram plain delivery failed (chat=%s, %d chars): %s",
            chat_id,
            len(body),
            exc,
        )
        return False


def schedule_telegram_subagent_delivery(
    bot: Any,
    session: Any,
    job_id: str,
    *,
    agent: Any,
) -> None:
    """Start background wait + push for a delegated sub-agent job."""
    from cli.shared.commands.subagent_commands import _schedule_subagent_delivery

    pin_subagent_agent(session, agent)
    host = TelegramSubagentDeliveryHost(bot, session, agent)
    logger.info(
        "Scheduling Telegram sub-agent delivery (chat=%s, job=%s)",
        getattr(session, "chat_id", "?"),
        job_id,
    )
    _schedule_subagent_delivery(host, job_id)