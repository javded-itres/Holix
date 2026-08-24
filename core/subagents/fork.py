"""Seed a child sub-agent with the parent's completed conversation turns.

DeepSeek Harness fork-in-process: the child sees balanced completed parent
turns and none of the in-flight tool-calling turn. History only — tools,
PTY, todos, and permission stay on the child's own conversation id.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FORK_HISTORY_CAP = 80
_MAX_MSG_CHARS = 8_000


def completed_turn_prefix(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the open tool-calling turn so the child gets a balanced history."""
    msgs = [m for m in messages if isinstance(m, dict)]
    while msgs:
        last = msgs[-1]
        role = str(last.get("role") or "")
        if role == "tool":
            msgs.pop()
            continue
        if role == "assistant" and last.get("tool_calls"):
            msgs.pop()
            continue
        break
    if msgs and str(msgs[-1].get("role") or "") == "user":
        msgs.pop()
    return [m for m in msgs if str(m.get("role") or "") != "system"]


def snapshot_messages_for_fork(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serializable role/content rows for a child conversation seed."""
    out: list[dict[str, Any]] = []
    for msg in completed_turn_prefix(messages):
        role = str(msg.get("role") or "")
        if role not in {"user", "assistant", "tool"}:
            continue
        content = str(msg.get("content") or "")[:_MAX_MSG_CHARS]
        row: dict[str, Any] = {"role": role, "content": content}
        name = str(msg.get("name") or "").strip()
        if not name and isinstance(msg.get("metadata"), dict):
            name = str(msg["metadata"].get("tool_name") or "").strip()
        if name:
            row["name"] = name
        out.append(row)
    if len(out) > FORK_HISTORY_CAP:
        out = out[-FORK_HISTORY_CAP:]
    return out


def parent_conversation_id(parent: Any) -> str:
    try:
        from core.tools.execution_context import get_conversation_id

        cid = str(get_conversation_id() or "").strip()
        if cid:
            return cid
    except Exception:
        pass
    return str(getattr(parent, "conversation_id", None) or "default")


async def snapshot_parent_history(parent: Any) -> list[dict[str, Any]]:
    memory = getattr(parent, "memory", None)
    if memory is None or not hasattr(memory, "get_conversation"):
        return []
    cid = parent_conversation_id(parent)
    try:
        messages = await memory.get_conversation(cid, limit=200)
    except Exception:
        logger.debug("fork snapshot failed", exc_info=True)
        return []
    return snapshot_messages_for_fork(list(messages or []))


async def apply_fork_seed(memory: Any, conversation_id: str, seed: list[dict[str, Any]]) -> int:
    """Write seed rows into *conversation_id* so prepare_session loads them."""
    if memory is None or not seed:
        return 0
    n = 0
    for msg in seed:
        role = str(msg.get("role") or "")
        if role not in {"user", "assistant", "tool"}:
            continue
        meta: dict[str, Any] = {"fork_seed": True}
        name = str(msg.get("name") or "").strip()
        if name:
            meta["tool_name"] = name
        await memory.save_message(
            conversation_id,
            role,
            str(msg.get("content") or ""),
            metadata=meta,
        )
        n += 1
    return n


def insert_seed_messages(
    messages: list[dict[str, Any]],
    seed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Place seed after the system prompt and before the task user message."""
    if not seed:
        return messages
    if messages and str(messages[0].get("role") or "") == "system":
        return [messages[0], *seed, *messages[1:]]
    return [*seed, *messages]
