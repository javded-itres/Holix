"""Shared session preparation for all execution paths."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def prepare_session(
    agent: Any,
    user_input: str,
    conversation_id: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Load history, persist the user message, and apply context compression.

    Returns:
        (messages, was_compressed) — messages ready for the agent/graph loop.
    """
    messages = await agent.memory.get_conversation(conversation_id)

    messages.append({"role": "user", "content": user_input})
    await agent.memory.save_message(conversation_id, "user", user_input)

    from core.runtime.context_session import compress_session_if_needed

    messages, was_compressed = await compress_session_if_needed(
        agent, conversation_id, messages
    )

    return messages, was_compressed