"""Normalize agent final text before delivering to messenger UIs."""

from __future__ import annotations

import re
from typing import Any

from core.llm.response_text import sanitize_assistant_visible_text
from core.presenters.subagent_tool_text import pick_best_tool_final

_PLACEHOLDER_FINALS = frozenset(
    {
        "",
        "no response generated",
    }
)

_ABORTED_FINAL_MARKERS = (
    "не ответила за",
    "error during agent step",
    "request timed out",
    "timed out",
    "no llm model configured",
    "no llm client available",
    "agent reached maximum steps",
    "превышено время выполнения",
)
# "Error: …" as a message — not "TimeoutError:" / "ValueError:" inside source dumps.
_ERROR_MESSAGE_RE = re.compile(r"(?:^|[\s])error:", re.IGNORECASE)

MESSENGER_EMPTY_FINAL_RU = (
    "Агент завершил работу без текстового ответа.\nПроверьте модель (/models) или повторите запрос."
)

UNUSABLE_TEST_DUMP_RU = (
    "Агент не сформировал текстовый ответ (часто — лимит шагов).\n"
    "Последний вывод tool — лог тестов, это не отчёт.\n"
    "{snippet}"
)

_UNSUCCESSFUL_FINAL_MARKERS = (
    "без текстового ответа",
    "без видимого ответа",
    "visible answer",
    "finished reasoning without",
    "no response generated",
)


def is_placeholder_final(content: str | None) -> bool:
    return (content or "").strip().lower() in _PLACEHOLDER_FINALS


def is_aborted_final_response(content: str | None) -> bool:
    """True when the run ended with timeout/error rather than a real answer."""
    text = (content or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if _ERROR_MESSAGE_RE.search(lowered):
        return True
    return any(marker in lowered for marker in _ABORTED_FINAL_MARKERS)


def is_unusable_final_tool_output(text: str | None) -> bool:
    """True when a tool payload must not be shown as the assistant's answer."""
    from core.runtime.test_run_signals import is_test_log_dump

    return is_test_log_dump(text or "")


def format_unusable_final(text: str | None, *, max_steps: int | None = None) -> str:
    from core.runtime.test_run_signals import failure_snippet

    snippet = failure_snippet(text or "")
    body = UNUSABLE_TEST_DUMP_RU.format(snippet=snippet or "(нет краткой строки ошибки)")
    if max_steps:
        return f"Достигнут лимит шагов ({max_steps}).\n{body}"
    return body


def coerce_usable_final_text(
    text: str | None,
    *,
    max_steps: int | None = None,
) -> str:
    """Drop pytest dumps; optionally annotate a max-steps stop."""
    raw = (text or "").strip()
    if not raw:
        if max_steps:
            return f"Достигнут лимит шагов ({max_steps}). Текстового ответа нет."
        return ""
    if is_unusable_final_tool_output(raw):
        return format_unusable_final(raw, max_steps=max_steps)
    return raw


def is_meaningful_final_response(content: str | None) -> bool:
    """True when the assistant produced a real answer worth treating as step completion."""
    text = (content or "").strip()
    if not text or is_placeholder_final(text):
        return False
    if is_aborted_final_response(text):
        return False
    if is_unusable_final_tool_output(text):
        return False
    lowered = text.lower()
    return not any(marker in lowered for marker in _UNSUCCESSFUL_FINAL_MARKERS)


def resolve_messenger_final_content(
    content: str | None,
    *,
    streamed_answer: str = "",
    last_tool_result: str = "",
    recent_tool_results: list[dict[str, Any]] | None = None,
    empty_message: str = MESSENGER_EMPTY_FINAL_RU,
) -> str:
    """Pick the best user-visible answer for Telegram/MAX delivery."""
    text = sanitize_assistant_visible_text(content or "")
    if is_placeholder_final(text):
        text = ""

    streamed = sanitize_assistant_visible_text(streamed_answer or "")
    if not text and streamed and not is_placeholder_final(streamed):
        text = streamed

    tool_text = (last_tool_result or "").strip()
    if recent_tool_results:
        picked = pick_best_tool_final(recent_tool_results)
        if picked:
            tool_text = picked
    if not text and tool_text:
        text = tool_text

    if is_unusable_final_tool_output(text):
        text = format_unusable_final(text)

    if not text:
        return empty_message
    return text
