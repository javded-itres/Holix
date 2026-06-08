"""Cross-session memory search helpers and formatting."""

from __future__ import annotations

from typing import Any


def memory_hit_session_id(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") or {}
    return str(meta.get("conversation_id") or "")


def memory_hit_role(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") or {}
    return str(meta.get("role") or "")


def memory_hit_tool_name(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") or {}
    return str(meta.get("tool_name") or "")


def memory_hit_type(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") or {}
    return str(meta.get("type") or "")


def format_relevance(mem: dict[str, Any]) -> str:
    distance = mem.get("distance")
    if distance is None:
        return ""
    try:
        return f" (relevance: {1 - float(distance):.2f})"
    except (TypeError, ValueError):
        return ""


def format_memory_hit_line(
    mem: dict[str, Any],
    *,
    index: int | None = None,
    content_limit: int = 300,
) -> str:
    """Single search hit with session id, role, and optional tool name."""
    session = memory_hit_session_id(mem) or "unknown"
    role = memory_hit_role(mem) or "?"
    tool = memory_hit_tool_name(mem)
    msg_type = memory_hit_type(mem)
    content = (mem.get("content") or "").replace("\n", " ").strip()
    if len(content) > content_limit:
        content = content[: content_limit - 1] + "…"

    prefix = f"{index}. " if index is not None else ""
    extra = ""
    if tool:
        extra = f" · tool={tool}"
    elif msg_type == "context_compression":
        extra = " · compressed context"

    return (
        f"{prefix}[{session}] {role}{extra}{format_relevance(mem)}: {content}"
    )


def format_memory_search_results(
    results: list[dict[str, Any]],
    *,
    current_conversation_id: str | None = None,
    include_current: bool = False,
    content_limit: int = 300,
) -> str:
    if not results:
        return "No matching messages in any session."

    lines: list[str] = []
    idx = 0
    for mem in results:
        session = memory_hit_session_id(mem)
        if (
            not include_current
            and current_conversation_id
            and session == current_conversation_id
            and memory_hit_type(mem) != "context_compression"
        ):
            continue
        idx += 1
        lines.append(
            format_memory_hit_line(mem, index=idx, content_limit=content_limit)
        )

    if not lines:
        return "No matches in other sessions (try include_current=true)."
    return "\n".join(lines)


def format_session_transcript(
    conversation_id: str,
    messages: list[dict[str, Any]],
    *,
    content_limit: int = 4000,
) -> str:
    if not messages:
        return f"Session '{conversation_id}' has no messages (or does not exist)."

    lines = [f"Session: {conversation_id}", f"Messages: {len(messages)}", ""]
    used = 0
    for msg in messages:
        role = msg.get("role", "?")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        meta = msg.get("metadata") or {}
        tool_name = meta.get("tool_name") if isinstance(meta, dict) else None
        header = f"[{role}]"
        if tool_name:
            header += f" ({tool_name})"
        block = f"{header}\n{content}\n"
        if used + len(block) > content_limit:
            lines.append("… (truncated — use search_sessions for specific topics)")
            break
        lines.append(block.strip())
        used += len(block)

    return "\n\n".join(lines)