"""Extract assistant-visible text from LLM responses (incl. reasoning models)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PLACEHOLDER_FINALS = frozenset({"", "no response generated"})


def stream_delta_parts(delta: Any) -> tuple[str, str]:
    """Return ``(content_delta, reasoning_delta)`` from a streaming chunk delta."""
    if delta is None:
        return "", ""
    content = ""
    reasoning = ""
    raw = getattr(delta, "content", None)
    if raw:
        content = str(raw)
    for attr in ("reasoning_content", "reasoning"):
        raw = getattr(delta, attr, None)
        if raw:
            reasoning += str(raw)
    return content, reasoning


def assistant_message_parts(message: Any) -> tuple[str, str]:
    """Return ``(content, reasoning)`` from a chat completion message object."""
    if message is None:
        return "", ""
    content = str(getattr(message, "content", None) or "")
    reasoning = ""
    for attr in ("reasoning_content", "reasoning"):
        raw = getattr(message, attr, None)
        if raw:
            reasoning += str(raw)
    return content, reasoning


def resolve_assistant_text(
    *,
    content: str = "",
    reasoning_content: str = "",
    finish_reason: str | None = None,
    model: str | None = None,
) -> str:
    """Pick user-visible assistant text; empty string means nothing to show."""
    text = (content or "").strip()
    if text.lower() in _PLACEHOLDER_FINALS:
        text = ""

    reasoning = (reasoning_content or "").strip()
    if not text and reasoning:
        text = reasoning

    if text:
        return text

    if finish_reason == "length":
        return (
            "Ответ обрезан лимитом токенов модели. "
            "Сократите запрос или выберите модель с большим контекстом."
        )
    if finish_reason == "content_filter":
        return "Модель отклонила запрос (content filter)."

    if model:
        logger.warning(
            "LLM returned empty assistant text (model=%s, finish_reason=%s)",
            model,
            finish_reason,
        )
    return ""