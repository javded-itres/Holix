"""Extract assistant-visible text from LLM responses (incl. reasoning models)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PLACEHOLDER_FINALS = frozenset({"", "no response generated"})

# Models often dump chain-of-thought into content with XML-like think tags.
_THINK_BLOCK_RE = re.compile(
    r"<think(?:ing)?\b[^>]*>[\s\S]*?</think(?:ing)?>",
    re.IGNORECASE,
)
_THINK_TAG_RE = re.compile(r"</?think(?:ing)?\b[^>]*>", re.IGNORECASE)
# Some providers leak special-token style wrappers into text.
_THINK_TOKEN_RE = re.compile(
    r"<\|?(?:redacted_reasoning|thinking|think)_?(?:start|end)?\|>",
    re.IGNORECASE,
)


def strip_reasoning_markup(text: str | None) -> str:
    """Remove think/CoT markup that models sometimes embed in ``content``."""
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", str(text))
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _THINK_TOKEN_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _norm_unit(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def is_pathological_repetition(
    text: str | None,
    *,
    min_unit: int = 20,
    min_repeats: int = 4,
) -> bool:
    """True when the same phrase is repeated many times (model degeneration)."""
    s = (text or "").strip()
    if len(s) < min_unit * min_repeats:
        return False
    # Consecutive sentence/ellipsis units
    units = [
        u
        for u in re.split(r"(?<=[.!?…])\s*|\n+", s)
        if _norm_unit(u)
    ]
    if len(units) >= min_repeats:
        norms = [_norm_unit(u) for u in units]
        run = 1
        for i in range(1, len(norms)):
            if norms[i] == norms[i - 1] and len(norms[i]) >= min_unit:
                run += 1
                if run >= min_repeats:
                    return True
            else:
                run = 1
    # Cyclic prefix covering most of the string
    n = len(s)
    limit = min(n // min_repeats, 240)
    for unit_len in range(min_unit, limit + 1):
        unit = s[:unit_len]
        if not unit.strip():
            continue
        repeats = 0
        pos = 0
        while pos + unit_len <= n and s[pos : pos + unit_len] == unit:
            repeats += 1
            pos += unit_len
        if repeats >= min_repeats and pos >= int(n * 0.75):
            return True
    return False


def collapse_repetitive_text(
    text: str | None,
    *,
    max_repeats: int = 2,
    min_unit: int = 20,
) -> str:
    """Collapse model loops like «фраза…фраза…фраза…» to a short form."""
    raw = (text or "").strip()
    if len(raw) < min_unit * 3:
        return raw

    # 1) Collapse consecutive duplicate sentence / ellipsis units
    pieces = re.split(r"((?:[.!?…]+|\n+)\s*)", raw)
    # pieces = [text, sep, text, sep, ...]
    out: list[str] = []
    prev_norm = ""
    run = 0
    i = 0
    while i < len(pieces):
        chunk = pieces[i]
        sep = pieces[i + 1] if i + 1 < len(pieces) else ""
        i += 2
        norm = _norm_unit(chunk)
        if not norm:
            if chunk or sep:
                out.append(chunk + sep)
            continue
        if norm == prev_norm and len(norm) >= min_unit:
            run += 1
            if run <= max_repeats:
                out.append(chunk + sep)
            # else drop
        else:
            prev_norm = norm
            run = 1
            out.append(chunk + sep)
    collapsed = "".join(out).strip()

    # 2) Cyclic prefix (identical block glued without clear separators)
    s = collapsed
    n = len(s)
    if n >= min_unit * 3:
        best = s
        limit = min(n // 3, 240)
        for unit_len in range(min_unit, limit + 1):
            unit = s[:unit_len]
            if not unit.strip():
                continue
            repeats = 0
            pos = 0
            while pos + unit_len <= n and s[pos : pos + unit_len] == unit:
                repeats += 1
                pos += unit_len
            if repeats >= 3 and pos >= int(n * 0.75):
                candidate = (unit * max_repeats).strip()
                if len(candidate) < len(best):
                    best = candidate
        collapsed = best

    if len(collapsed) < len(raw) * 0.9 and len(raw) > 200:
        logger.warning(
            "Collapsed pathological model repetition (%d → %d chars)",
            len(raw),
            len(collapsed),
        )
    return collapsed.strip()


def sanitize_assistant_visible_text(text: str | None) -> str:
    """Strip think tags and collapse looped monologue for user-facing delivery."""
    cleaned = strip_reasoning_markup(text)
    return collapse_repetitive_text(cleaned)


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
    text = sanitize_assistant_visible_text(content or "")
    if text.lower() in _PLACEHOLDER_FINALS:
        text = ""

    reasoning = (reasoning_content or "").strip()
    if not text and reasoning:
        # Do NOT surface a user-facing error here. Callers treat empty as
        # "retry / keep going" (plan step nudge, non-streaming retry). Emitting
        # llm.reasoning_only as the final answer aborted multi-step work while
        # tools/GPU were still busy.
        logger.warning(
            "LLM returned reasoning-only text (model=%s); treating as empty for retry",
            model,
        )
        return ""

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


def reasoning_only_user_message(*, profile_name: str | None = None) -> str:
    """Localized notice when retries are exhausted (not for intermediate steps)."""
    from core.i18n.messages import t

    return t("llm.reasoning_only", _ui_locale(profile_name))