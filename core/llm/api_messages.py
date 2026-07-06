"""Normalize Holix conversation history for provider chat APIs."""

from __future__ import annotations

from typing import Any

_API_MESSAGE_KEYS = frozenset({"role", "content", "name", "tool_calls", "tool_call_id"})


def _tool_call_ids(message: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for tc in message.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        tid = tc.get("id")
        if tid:
            ids.add(str(tid))
    return ids


def _to_api_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only fields accepted by OpenAI-compatible chat APIs."""
    role = message.get("role")
    if role not in {"system", "user", "assistant", "tool"}:
        return None

    out: dict[str, Any] = {"role": role}
    content = message.get("content")
    if content is not None:
        out["content"] = content

    name = message.get("name")
    if name:
        out["name"] = name

    tool_calls = message.get("tool_calls")
    if tool_calls:
        out["tool_calls"] = tool_calls

    tool_call_id = message.get("tool_call_id")
    if tool_call_id:
        out["tool_call_id"] = tool_call_id

    return out


def _append_context_note(target: dict[str, Any], note: str) -> None:
    body = str(note or "").strip()
    if not body:
        return
    block = f"[Context note]\n{body}" if not body.startswith("[") else body
    existing = str(target.get("content") or "").strip()
    target["content"] = f"{existing}\n\n{block}".strip() if existing else block


def _prepend_context_notes(target: dict[str, Any], notes: list[str]) -> None:
    blocks = [f"[Context note]\n{note.strip()}" for note in notes if str(note or "").strip()]
    if not blocks:
        return
    prefix = "\n\n".join(blocks)
    existing = str(target.get("content") or "").strip()
    target["content"] = f"{prefix}\n\n{existing}".strip() if existing else prefix


def _strip_incomplete_tool_turn(messages: list[dict[str, Any]]) -> None:
    while messages and messages[-1].get("role") == "tool":
        messages.pop()
    if messages and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
        messages.pop()


def repair_api_message_sequence(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fix ordering rules enforced by Groq/Mistral/OpenAI-compatible APIs."""
    if not messages:
        return messages

    result: list[dict[str, Any]] = []
    pending_tool_ids: set[str] = set()

    for message in messages:
        role = message.get("role")

        if role == "assistant":
            if pending_tool_ids:
                _strip_incomplete_tool_turn(result)
                pending_tool_ids = set()
            pending_tool_ids = _tool_call_ids(message)
            result.append(message)
            continue

        if role == "tool":
            tool_id = str(message.get("tool_call_id") or "")
            if tool_id and tool_id in pending_tool_ids:
                result.append(message)
                pending_tool_ids.discard(tool_id)
                continue
            if result and result[-1].get("role") == "user":
                content = str(message.get("content") or "").strip()
                if content:
                    _append_context_note(result[-1], f"[Tool result]\n{content}")
            continue

        if role == "user":
            if pending_tool_ids:
                _strip_incomplete_tool_turn(result)
                pending_tool_ids = set()
            result.append(message)
            continue

        result.append(message)

    if pending_tool_ids:
        _strip_incomplete_tool_turn(result)

    return result


def drop_leading_orphan_tools(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Context truncation may keep tool rows without the assistant tool_calls turn."""
    trimmed = list(messages)
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed.pop(0)
    return trimmed


def finalize_api_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return repair_api_message_sequence(drop_leading_orphan_tools(messages))


def prepare_conversation_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip Holix-only fields and duplicate system turns before an API call.

    Soul blocks are injected into session storage for compression pinning, but
    the live system prompt already includes ``format_soul_block()``. Providers such
    as Groq (single system message) and Mistral (strict schema) reject extra
    ``role:system`` entries and unknown keys like ``metadata``.

    System notes are deferred while a tool-call turn is in progress so we never
    insert ``role:user`` between ``assistant.tool_calls`` and ``role:tool``.
    """
    from core.profile.soul import strip_soul_messages

    prepared: list[dict[str, Any]] = []
    deferred_notes: list[str] = []
    pending_tool_ids: set[str] = set()

    for message in strip_soul_messages(messages):
        role = message.get("role")

        if role == "system":
            content = str(message.get("content") or "").strip()
            if content:
                if pending_tool_ids:
                    deferred_notes.append(content)
                else:
                    prepared.append(
                        {"role": "user", "content": f"[Context note]\n{content}"}
                    )
            continue

        if role == "assistant":
            if pending_tool_ids:
                _strip_incomplete_tool_turn(prepared)
                pending_tool_ids = set()
            api_message = _to_api_message(message)
            if api_message is not None:
                pending_tool_ids = _tool_call_ids(api_message)
                if not pending_tool_ids and deferred_notes:
                    _prepend_context_notes(api_message, deferred_notes)
                    deferred_notes.clear()
                prepared.append(api_message)
            continue

        if role == "tool":
            api_message = _to_api_message(message)
            if api_message is None:
                continue
            tool_id = str(api_message.get("tool_call_id") or "")
            if tool_id and tool_id in pending_tool_ids:
                prepared.append(api_message)
                pending_tool_ids.discard(tool_id)
            continue

        if role == "user":
            if pending_tool_ids:
                _strip_incomplete_tool_turn(prepared)
                pending_tool_ids = set()
            api_message = _to_api_message(message)
            if api_message is None:
                continue
            if deferred_notes:
                _prepend_context_notes(api_message, deferred_notes)
                deferred_notes.clear()
            prepared.append(api_message)
            continue

        api_message = _to_api_message(message)
        if api_message is not None:
            prepared.append(api_message)

    if pending_tool_ids:
        _strip_incomplete_tool_turn(prepared)
    if deferred_notes:
        prepared.append(
            {
                "role": "user",
                "content": "[Context note]\n" + "\n\n".join(deferred_notes),
            }
        )

    return finalize_api_messages(prepared)