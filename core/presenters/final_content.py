"""Normalize agent final text before delivering to messenger UIs."""

from __future__ import annotations

from typing import Any

from core.presenters.subagent_tool_text import pick_best_tool_final

_PLACEHOLDER_FINALS = frozenset(
    {
        "",
        "no response generated",
    }
)

MESSENGER_EMPTY_FINAL_RU = (
    "Агент завершил работу без текстового ответа.\n"
    "Проверьте модель (/models) или повторите запрос."
)


def is_placeholder_final(content: str | None) -> bool:
    return (content or "").strip().lower() in _PLACEHOLDER_FINALS


def resolve_messenger_final_content(
    content: str | None,
    *,
    streamed_answer: str = "",
    last_tool_result: str = "",
    recent_tool_results: list[dict[str, Any]] | None = None,
    empty_message: str = MESSENGER_EMPTY_FINAL_RU,
) -> str:
    """Pick the best user-visible answer for Telegram/MAX delivery."""
    text = (content or "").strip()
    if is_placeholder_final(text):
        text = ""

    streamed = (streamed_answer or "").strip()
    if not text and streamed and not is_placeholder_final(streamed):
        text = streamed

    tool_text = (last_tool_result or "").strip()
    if recent_tool_results:
        picked = pick_best_tool_final(recent_tool_results)
        if picked:
            tool_text = picked
    if not text and tool_text:
        text = tool_text

    if not text:
        return empty_message
    return text