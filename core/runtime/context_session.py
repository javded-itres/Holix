"""Shared helpers for session context compression and persistence."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)


def _load_anchor(agent: Any, conversation_id: str) -> int | None:
    anchors = getattr(agent, "_session_load_anchor", None)
    if not isinstance(anchors, dict):
        return None
    anchor = anchors.get(conversation_id)
    if anchor is None:
        return None
    try:
        return int(anchor)
    except (TypeError, ValueError):
        return None


def _touch_activity(agent: Any, conversation_id: str) -> None:
    """One idle check per quiet gap, not once per tool step of the resumed turn."""
    from datetime import datetime

    activity = getattr(agent, "_session_last_activity", None)
    if not isinstance(activity, dict):
        activity = {}
        agent._session_last_activity = activity
    activity[conversation_id] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


async def _idle_compress(
    agent: Any,
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Summarize a warning-band session that has been idle, before the next turn."""
    from core.runtime.session import IDLE_COMPRESS_AFTER_S, message_age_seconds

    cm = getattr(agent, "context_manager", None)
    activity = getattr(agent, "_session_last_activity", None)
    last_ts = activity.get(conversation_id) if isinstance(activity, dict) else None
    age = message_age_seconds(last_ts)
    if age is None or age < IDLE_COMPRESS_AFTER_S or len(messages) < 4:
        return messages, False
    _touch_activity(agent, conversation_id)
    usage = cm.get_usage(messages, conversation_id=conversation_id, include_system_reserve=True)
    if float(usage.get("percent") or 0) < float(cm.warning_threshold) * 100:
        return messages, False
    compressed, was_compressed = await cm.compress_context(messages)
    if was_compressed:
        logger.info(
            "Idle compression for %s after %.0f minutes",
            conversation_id,
            age / 60,
        )
    return compressed, was_compressed


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

    messages, idle_compressed = await _idle_compress(agent, conversation_id, messages)
    compressed, was_compressed = await cm.auto_compress_if_needed(
        messages,
        conversation_id=conversation_id,
    )
    was_compressed = was_compressed or idle_compressed
    if was_compressed:
        cm.invalidate_usage_cache(conversation_id)
    if not was_compressed:
        return messages, False

    compressed = inject_soul_into_messages(compressed, profile)

    try:
        from core.memory.conversation import is_stored_honesty_nudge

        to_store = [
            m
            for m in compressed
            if not (
                isinstance(m, dict) and is_stored_honesty_nudge(m.get("role"), m.get("content"))
            )
        ]
        count = await agent.memory.replace_conversation_messages(
            conversation_id,
            to_store,
            from_row_id=_load_anchor(agent, conversation_id),
        )
        logger.info("Compressed conversation persisted: %s messages in DB", count)
    except Exception as persist_err:
        logger.warning("Failed to persist compressed conversation: %s", persist_err)
        if cm.last_summary:
            try:
                await agent.memory.save_message(
                    conversation_id,
                    "system",
                    f"Context compressed. Summary of previous conversation:\n\n{cm.last_summary}",
                    metadata={"type": "context_compression"},
                )
            except Exception:
                pass

    return compressed, True


async def ensure_conversation_context(
    agent: Any,
    conversation_id: str,
    *,
    limit: int | None = None,
) -> bool:
    """Load the whole session from DB and compress if usage exceeds threshold."""
    try:
        messages = await agent.memory.get_conversation(conversation_id, limit=limit)
    except Exception:
        return False
    if not messages:
        return False
    _, was_compressed = await compress_session_if_needed(agent, conversation_id, messages)
    return was_compressed
