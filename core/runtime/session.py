"""Shared session preparation for all execution paths."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Must match Studio context bar / manual /compress (not the old default of 30).
DEFAULT_CONVERSATION_HISTORY_LIMIT = 200


def conversation_history_limit(agent: Any | None = None) -> int:
    """How many recent DB messages to load into the agent context."""
    cfg = getattr(agent, "config", None) if agent is not None else None
    raw = getattr(cfg, "conversation_history_limit", None) if cfg is not None else None
    if raw is not None:
        try:
            return max(1, min(int(raw), 500))
        except (TypeError, ValueError):
            pass
    return DEFAULT_CONVERSATION_HISTORY_LIMIT


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

    messages.append({"role": "user", "content": user_input})
    await agent.memory.save_message(conversation_id, "user", user_input)

    from core.runtime.context_session import compress_session_if_needed

    messages, was_compressed = await compress_session_if_needed(
        agent, conversation_id, messages
    )

    return messages, was_compressed