"""Shared session preparation for all execution paths."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


async def prepare_session(
    agent: Any,
    user_input: str,
    conversation_id: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Load history, persist the user message, and apply context compression.

    Returns:
        (messages, was_compressed) — messages ready for the agent/graph loop.
    """
    messages = await agent.memory.get_conversation(conversation_id)

    messages.append({"role": "user", "content": user_input})
    await agent.memory.save_message(conversation_id, "user", user_input)

    was_compressed = False
    if hasattr(agent, "context_manager") and agent.context_manager:
        messages, was_compressed = await agent.context_manager.auto_compress_if_needed(
            messages
        )
        if was_compressed:
            try:
                count = await agent.memory.replace_conversation_messages(
                    conversation_id, messages
                )
                logger.info(
                    "Compressed conversation persisted: %s messages in DB", count
                )
            except Exception as persist_err:
                logger.warning(
                    "Failed to persist compressed conversation: %s", persist_err
                )
                if agent.context_manager.last_summary:
                    await agent.memory.save_message(
                        conversation_id,
                        "system",
                        "Context compressed. Summary of previous conversation:\n\n"
                        f"{agent.context_manager.last_summary}",
                        metadata={"type": "context_compression"},
                    )

    return messages, was_compressed