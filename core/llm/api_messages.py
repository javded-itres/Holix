"""Normalize Holix conversation history for provider chat APIs."""

from __future__ import annotations

from typing import Any

_API_MESSAGE_KEYS = frozenset({"role", "content", "name", "tool_calls", "tool_call_id"})


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


def prepare_conversation_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip Holix-only fields and duplicate system turns before an API call.

    Soul blocks are injected into session storage for compression pinning, but
    the live system prompt already includes ``format_soul_block()``. Providers such
    as Groq (single system message) and Mistral (strict schema) reject extra
    ``role:system`` entries and unknown keys like ``metadata``.
    """
    from core.profile.soul import strip_soul_messages

    prepared: list[dict[str, Any]] = []
    for message in strip_soul_messages(messages):
        role = message.get("role")
        if role == "system":
            content = str(message.get("content") or "").strip()
            if content:
                prepared.append(
                    {
                        "role": "user",
                        "content": f"[Context note]\n{content}",
                    }
                )
            continue

        api_message = _to_api_message(message)
        if api_message is not None:
            prepared.append(api_message)

    return prepared