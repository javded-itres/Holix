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


def _ui_locale(profile_name: str | None) -> str:
    from core.i18n.locale import LocaleStore

    if profile_name:
        return LocaleStore(profile_name).get()
    return "en"


def resolve_assistant_text(
    *,
    content: str = "",
    reasoning_content: str = "",
    finish_reason: str | None = None,
    model: str | None = None,
    profile_name: str | None = None,
) -> str:
    """Pick user-visible assistant text; empty string means nothing to show."""
    from core.i18n.messages import t

    locale = _ui_locale(profile_name)
    text = (content or "").strip()
    if text.lower() in _PLACEHOLDER_FINALS:
        text = ""

    reasoning = (reasoning_content or "").strip()
    if not text and reasoning:
        logger.warning(
            "LLM returned reasoning-only text (model=%s); not exposing to user",
            model,
        )
        return t("llm.reasoning_only", locale)

    if text:
        return text

    if finish_reason == "length":
        return t("llm.truncated", locale)
    if finish_reason == "content_filter":
        return t("llm.content_filter", locale)

    if model:
        logger.warning(
            "LLM returned empty assistant text (model=%s, finish_reason=%s)",
            model,
            finish_reason,
        )
    return ""