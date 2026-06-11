"""Shared helpers for session context compression and persistence."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def compress_session_if_needed(
    agent: Any,
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Compress in-memory messages when over threshold and persist to DB."""
    cm = getattr(agent, "context_manager", None)
    if not cm:
        return messages, False

    from core.profile.soul import inject_soul_into_messages, profile_name_from_agent

    profile = profile_name_from_agent(agent)
    messages = inject_soul_into_messages(messages, profile)

    compressed, was_compressed = await cm.auto_compress_if_needed(messages)
    if not was_compressed:
        return messages, False

    compressed = inject_soul_into_messages(compressed, profile)

    try:
        count = await agent.memory.replace_conversation_messages(
            conversation_id, compressed
        )
        logger.info(
            "Compressed conversation persisted: %s messages in DB", count
        )
    except Exception as persist_err:
        logger.warning(
            "Failed to persist compressed conversation: %s", persist_err
        )
        if cm.last_summary:
            try:
                await agent.memory.save_message(
                    conversation_id,
                    "system",
                    "Context compressed. Summary of previous conversation:\n\n"
                    f"{cm.last_summary}",
                    metadata={"type": "context_compression"},
                )
            except Exception:
                pass

    return compressed, True


async def ensure_conversation_context(
    agent: Any,
    conversation_id: str,
    *,
    limit: int = 500,
) -> bool:
    """Load conversation from DB and compress if usage exceeds threshold."""
    try:
        messages = await agent.memory.get_conversation(conversation_id, limit=limit)
    except Exception:
        return False
    if not messages:
        return False
    _, was_compressed = await compress_session_if_needed(
        agent, conversation_id, messages
    )
    return was_compressed