"""Helpers around OpenAI-shaped chat completions."""

from __future__ import annotations

from typing import Any

EMPTY_LLM_ERROR = "empty LLM response (no choices)"
EMPTY_FINAL_CONTINUE = (
    "SUPERVISOR GUIDANCE: Your last reply was empty (no text and no tools). "
    "That is not a finished step. Continue the assigned work now: "
    "call the next tool or write a concrete result of what you already did. "
    "Do not end the turn with an empty message."
)
_BLANK_FINALS = frozenset(
    {
        "",
        "no response",
        "no response generated",
        "none",
        "...",
        "…",
    }
)


def first_choice_message(response: Any) -> Any | None:
    """Return ``choices[0].message`` or None when LiteLLM sent an empty body."""
    if response is None:
        return None
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    return message


def is_empty_llm_response(response: Any) -> bool:
    return first_choice_message(response) is None


def is_blank_final_text(text: str | None) -> bool:
    """True when a 'final' assistant message has no usable content."""
    return (text or "").strip().lower() in _BLANK_FINALS
