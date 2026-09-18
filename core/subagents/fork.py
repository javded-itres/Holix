"""Seed a child sub-agent with the parent's completed conversation turns.

DeepSeek Harness fork-in-process: the child sees balanced completed parent
turns and none of the in-flight tool-calling turn. History only — tools,
PTY, todos, and permission stay on the child's own conversation id.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

FORK_HISTORY_CAP = 80
_MAX_MSG_CHARS = 8_000
# Must match core.sdd.change_workspace._safe_cid (invalid ids collapse to "default").
_MAX_CID_LEN = 121
_CID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,120}$")
_CHILD_PREFIX = "subagent:"
_FRAG_RE = re.compile(r"[^a-zA-Z0-9._:-]+")


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


def _usable_cid(raw: Any, *, allow_subagent: bool = False) -> str:
    if not isinstance(raw, str):
        return ""
    cid = raw.strip()
    if not cid or cid == "default":
        return ""
    if not allow_subagent and cid.startswith(_CHILD_PREFIX):
        return ""
    return cid


def _sanitize_fragment(raw: str) -> str:
    text = _FRAG_RE.sub("-", (raw or "").strip()).strip("-._:")
    return text


def parent_conversation_id(parent: Any) -> str:
    """Conversation that launched this spawn — not a later focused tab.

    Skip ContextVar ``default`` and child ``subagent:…`` ids so a child run
    never treats itself as the parent. Prefer the live parent run context.
    """
    try:
        from core.tools.execution_context import get_conversation_id

        cid = _usable_cid(get_conversation_id())
        if cid:
            return cid
    except Exception:
        pass
    ctx = getattr(parent, "_event_context", None)
    cid = _usable_cid(getattr(ctx, "conversation_id", None))
    if cid:
        return cid
    cid = _usable_cid(getattr(parent, "conversation_id", None))
    if cid:
        return cid
    return "default"


def child_conversation_id(parent_cid: str, name: str) -> str:
    """Per-launch child cid ``subagent:{parent}:{name}`` (fits SDD ``_safe_cid``).

    Global ``subagent:{name}`` collides across Studio tabs: the last inherit
    overwrites the workspace pin for every job of that type.
    """
    parent = _sanitize_fragment(parent_cid) or "default"
    job = _sanitize_fragment(name) or "sub"
    raw = f"{_CHILD_PREFIX}{parent}:{job}"
    if _CID_RE.fullmatch(raw) and len(raw) <= _MAX_CID_LEN:
        return raw
    digest = hashlib.sha1(parent.encode("utf-8")).hexdigest()[:12]
    hashed = f"{_CHILD_PREFIX}{digest}:{job}"
    if _CID_RE.fullmatch(hashed) and len(hashed) <= _MAX_CID_LEN:
        return hashed
    overhead = len(_CHILD_PREFIX) + len(digest) + 1
    max_job = max(1, _MAX_CID_LEN - overhead)
    job = job[:max_job]
    return f"{_CHILD_PREFIX}{digest}:{job}"


def parent_from_child_conversation_id(child_cid: str) -> str:
    """Parent cid encoded in ``subagent:{parent}:{name}``; empty for legacy ids."""
    text = str(child_cid or "").strip()
    if not text.startswith(_CHILD_PREFIX):
        return ""
    rest = text[len(_CHILD_PREFIX) :]
    if ":" not in rest:
        return ""
    parent, _, _job = rest.rpartition(":")
    parent = parent.strip()
    if not parent or parent == "default":
        return ""
    # Hashed parent (12 hex) cannot be mapped back to the Studio tab.
    if len(parent) == 12 and re.fullmatch(r"[0-9a-f]{12}", parent):
        return ""
    return parent


def bind_subagent_session(
    parent: Any,
    config: Any,
    handle: Any | None = None,
) -> tuple[str, str]:
    """Capture launch session, namespace the child cid, inherit the workspace pin.

    Must run synchronously in the parent spawn path *before* the child task
    starts and *before* Studio restores ContextVars.
    """
    parent_cid = parent_conversation_id(parent)
    child_cid = child_conversation_id(parent_cid, str(getattr(config, "name", "") or ""))
    if handle is not None:
        try:
            handle.parent_conversation_id = parent_cid
            handle.conversation_id = child_cid
        except Exception:
            pass
    for obj in (config, getattr(handle, "config", None)):
        if obj is None:
            continue
        try:
            obj.parent_conversation_id = parent_cid
            obj.conversation_id = child_cid
        except Exception:
            pass
    try:
        from core.sdd.change_workspace import resolve_subagent_workspace

        parent_cfg = getattr(parent, "config", None)
        profile = str(getattr(parent_cfg, "profile_name", None) or "default")
        fallback = getattr(parent_cfg, "workspace_root", None) if parent_cfg else None
        resolve_subagent_workspace(
            profile=profile,
            parent_conversation_id=parent_cid,
            child_conversation_id=child_cid,
            fallback=str(fallback) if fallback else None,
        )
    except Exception:
        logger.debug("inherit subagent workspace failed", exc_info=True)
    return parent_cid, child_cid


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
