"""Session-lifetime MAX listeners for events that fire after the main turn."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.subagents.interaction_events import SubAgentQuestionEvent

logger = logging.getLogger(__name__)


def attach_max_background_events(client: Any, session: Any) -> None:
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
            logger.debug("unsubscribe previous MAX background listener failed", exc_info=True)

    def on_event(event: Any) -> None:
        if not isinstance(event, SubAgentQuestionEvent):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "MAX: no event loop for sub-agent question %s",
                getattr(event, "subagent_name", ""),
            )
            return
        loop.create_task(deliver_max_subagent_question(client, session, event))

    agent.events.subscribe(on_event)
    session._bg_event_cb = on_event
    session._bg_event_agent = agent


async def deliver_max_subagent_question(client: Any, session: Any, event: Any) -> None:
    from integrations.max.keyboards import subagent_reply_keyboard
    from integrations.max.models import message_id_from_response, reply_kwargs_for_session
    from integrations.messenger.locale import messenger_locale
    from integrations.messenger.subagent_question_ui import (
        format_subagent_question_message,
        mark_question_posted,
    )
    from integrations.messenger.subagent_reply import (
        remember_question_message,
        tokens_for_jobs,
    )

    request_id = str(getattr(event, "request_id", "") or "")
    if not mark_question_posted(session, request_id):
        return

    lang = messenger_locale(getattr(session, "profile", None) or "admin")
    name = str(getattr(event, "subagent_name", "") or "").strip() or "sub-agent"
    text = format_subagent_question_message(
        job_id=name,
        question=str(getattr(event, "question", "") or ""),
        context=str(getattr(event, "context", "") or ""),
        locale=lang,
        html=False,
    )
    tokens = tokens_for_jobs(session.subagent_reply_tokens, [name])
    kb = subagent_reply_keyboard(tokens, lang)
    try:
        payload = await client.send_message(
            text,
            attachments=[kb] if kb else None,
            **reply_kwargs_for_session(session),
        )
        remember_question_message(session, message_id_from_response(payload), name)
        logger.info("MAX sub-agent question delivered (job=%s, id=%s)", name, request_id)
    except Exception:
        logger.exception("MAX sub-agent question failed (job=%s)", name)
