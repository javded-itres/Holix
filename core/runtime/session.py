"""Shared session preparation for all execution paths."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def conversation_history_limit(agent: Any | None = None) -> int | None:
    """How many DB messages to load. None is the whole session, start to end.

    A profile may still set ``conversation_history_limit`` to a positive tail.
    """
    cfg = getattr(agent, "config", None) if agent is not None else None
    raw = getattr(cfg, "conversation_history_limit", None) if cfg is not None else None
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


async def prepare_session(
    agent: Any,
    user_input: str,
    conversation_id: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Load history, persist the user message, and apply context compression.

    Returns:
        (messages, was_compressed) — messages ready for the agent/graph loop.
    """
    from core.profile.soul import inject_soul_into_messages, profile_name_from_agent

    profile = profile_name_from_agent(agent)
    limit = conversation_history_limit(agent)
    messages = await agent.memory.get_conversation(conversation_id, limit=limit)
    messages = inject_soul_into_messages(messages, profile)

    from core.project.init_intent import expand_user_message_for_holix_init

    loop_input = user_input
    try:
        loop_input = expand_user_message_for_holix_init(user_input, agent=agent)
    except Exception:
        logger.warning("holix init expand failed", exc_info=True)
        loop_input = user_input
    messages.append({"role": "user", "content": loop_input})
    await agent.memory.save_message(conversation_id, "user", user_input)

    from core.runtime.context_session import compress_session_if_needed

    messages, was_compressed = await compress_session_if_needed(agent, conversation_id, messages)

    return messages, was_compressed
