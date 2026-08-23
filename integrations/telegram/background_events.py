"""Session-lifetime Telegram listeners for events that fire after the main turn."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.subagents.interaction_events import SubAgentQuestionEvent

logger = logging.getLogger(__name__)


def attach_telegram_background_events(bot: Any, session: Any) -> None:
    """Keep delivering sub-agent questions after agent.run() unsubscribes the live UI."""
    agent = getattr(session, "agent", None)
    if agent is None or not getattr(agent, "events", None):
        return
    old_cb = getattr(session, "_bg_event_cb", None)
    old_agent = getattr(session, "_bg_event_agent", None)
    if old_cb is not None and old_agent is not None and old_agent is agent:
        return
    if old_cb is not None and old_agent is not None:
        try:
            old_agent.events.unsubscribe(old_cb)
        except Exception:
            logger.debug("unsubscribe previous telegram background listener failed", exc_info=True)

    def on_event(event: Any) -> None:
        if not isinstance(event, SubAgentQuestionEvent):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "Telegram: no event loop for sub-agent question %s",
                getattr(event, "subagent_name", ""),
            )
            return
        loop.create_task(deliver_telegram_subagent_question(bot, session, event))

    agent.events.subscribe(on_event)
    session._bg_event_cb = on_event
    session._bg_event_agent = agent


async def deliver_telegram_subagent_question(bot: Any, session: Any, event: Any) -> None:
    """Post a dedicated chat message with job name, Russian chrome, and a Reply button."""
    from integrations.messenger.locale import messenger_locale
    from integrations.messenger.subagent_question_ui import (
        format_subagent_question_message,
        mark_question_posted,
    )
    from integrations.messenger.subagent_reply import (
        remember_question_message,
        tokens_for_jobs,
    )
    from integrations.telegram.keyboards import subagent_reply_keyboard

    request_id = str(getattr(event, "request_id", "") or "")
    if not mark_question_posted(session, request_id):
        return

    lang = messenger_locale(getattr(session, "profile", None) or "admin")
    name = str(getattr(event, "subagent_name", "") or "").strip() or "sub-agent"
    html = format_subagent_question_message(
        job_id=name,
        question=str(getattr(event, "question", "") or ""),
        context=str(getattr(event, "context", "") or ""),
        locale=lang,
        html=True,
    )
    tokens = tokens_for_jobs(session.subagent_reply_tokens, [name])
    kb = subagent_reply_keyboard(tokens, lang)
    chat_id = getattr(session, "chat_id", None)
    try:
        msg = await bot.send_message(
            chat_id,
            html,
            parse_mode="HTML",
            reply_markup=kb,
        )
        remember_question_message(session, getattr(msg, "message_id", None), name)
        logger.info(
            "Telegram sub-agent question delivered (chat=%s, job=%s, id=%s)",
            chat_id,
            name,
            request_id,
        )
        return
    except Exception:
        logger.exception(
            "Telegram HTML sub-agent question failed (chat=%s, job=%s)",
            chat_id,
            name,
        )

    plain = format_subagent_question_message(
        job_id=name,
        question=str(getattr(event, "question", "") or ""),
        context=str(getattr(event, "context", "") or ""),
        locale=lang,
        html=False,
    )
    try:
        msg = await bot.send_message(chat_id, plain[:3900], reply_markup=kb)
        remember_question_message(session, getattr(msg, "message_id", None), name)
    except Exception:
        logger.exception(
            "Telegram plain sub-agent question failed (chat=%s, job=%s)",
            chat_id,
            name,
        )
