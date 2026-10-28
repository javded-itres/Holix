"""Shared session preparation for all execution paths."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# A long idle chat is summarized before the next message, once it is already
# in the warning band. Shorter than a provider cache TTL: the costly part is
# resuming a days-old TUI with the whole stored session.
IDLE_COMPRESS_AFTER_S = 30 * 60


def take_load_anchor(messages: list[dict[str, Any]]) -> tuple[int | None, str | None]:
    """Pop storage ids from loaded rows. Returns the oldest id and last timestamp."""
    ids: list[int] = []
    last_ts: str | None = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        row_id = message.pop("_row_id", None)
        if row_id is not None:
            try:
                ids.append(int(row_id))
            except (TypeError, ValueError):
                pass
        row_ts = message.pop("_row_ts", None)
        if row_ts:
            last_ts = str(row_ts)
    return (min(ids) if ids else None), last_ts


def message_age_seconds(timestamp: str | None, *, now: datetime | None = None) -> float | None:
    if not timestamp:
        return None
    text = str(timestamp).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return (current - parsed).total_seconds()


def remember_session_load(
    agent: Any,
    conversation_id: str,
    anchor: int | None,
    last_ts: str | None,
) -> None:
    anchors = getattr(agent, "_session_load_anchor", None)
    if not isinstance(anchors, dict):
        anchors = {}
        agent._session_load_anchor = anchors
    anchors[conversation_id] = anchor
    activity = getattr(agent, "_session_last_activity", None)
    if not isinstance(activity, dict):
        activity = {}
        agent._session_last_activity = activity
    activity[conversation_id] = last_ts


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
    anchor, last_ts = take_load_anchor(messages)
    remember_session_load(agent, conversation_id, anchor, last_ts)
    messages = inject_soul_into_messages(messages, profile)

    from core.project.init_intent import expand_user_message_for_holix_init

    loop_input = user_input
    try:
        loop_input = expand_user_message_for_holix_init(user_input, agent=agent)
    except Exception:
        logger.warning("holix init expand failed", exc_info=True)
        loop_input = user_input
    try:
        from core.hub.link_install import expand_user_message_for_share_link

        loop_input = expand_user_message_for_share_link(loop_input)
    except Exception:
        logger.warning("share-link expand failed", exc_info=True)
    messages.append({"role": "user", "content": loop_input})
    await agent.memory.save_message(conversation_id, "user", user_input)

    from core.runtime.context_session import compress_session_if_needed

    messages, was_compressed = await compress_session_if_needed(agent, conversation_id, messages)

    return messages, was_compressed
