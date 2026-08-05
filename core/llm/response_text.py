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


# Split sentences, but do **not** break on ``file.py`` / ``bot.py`` (dot mid-token).
# Models glue «…Поняла» without space after ellipsis — allow zero whitespace after ….
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=…)\s*"  # ellipsis always ends a unit (even with no following space)
    r"|(?<=[!?])\s*"  # ! ? always
    r"|(?<=\.)\s+"  # period only when whitespace follows (not file.py)
    r"|\n+"
)


def _sentence_units(text: str) -> list[str]:
    return [u.strip() for u in _SENTENCE_SPLIT_RE.split(text or "") if _norm_unit(u)]


def _find_sentence_cycle(
    units: list[str],
    *,
    min_repeats: int = 4,
) -> tuple[int, int, int] | None:
    """Find a repeating sentence cycle.

    Returns ``(start_index, period, run_count)`` when a block of ``period``
    sentences (period 1–6) repeats ``run_count`` times and covers most units.

    Catches patterns like::
        A A A A
        A B A B A B
        (with optional different prefix before the loop)
    including short fillers («Поняла.») alternating with longer monologue,
    and 4-unit cycles when a prior split broke ``bot.py`` into two pieces.
    """
    n = len(units)
    if n < min_repeats:
        return None
    norms = [_norm_unit(u) for u in units]

    for period in (1, 2, 3, 4, 5, 6):
        if n < period * min_repeats:
            continue
        # Allow the loop to start after a short non-looping prefix.
        max_start = min(period + 2, n - period * min_repeats + 1)
        for start in range(max(0, max_start)):
            block = tuple(norms[start : start + period])
            if not block or any(not b for b in block):
                continue
            # Require enough signal: one long sentence, or a multi-unit block
            # whose total length is meaningful (ABAB with short "Поняла.").
            total_len = sum(len(b) for b in block)
            longest = max(len(b) for b in block)
            if period == 1 and longest < 12:
                continue
            if period > 1 and longest < 10 and total_len < 20:
                continue
            run = 0
            i = start
            while i + period <= n and tuple(norms[i : i + period]) == block:
                run += 1
                i += period
            covered = run * period
            if run >= min_repeats and covered >= max(min_repeats, int(n * 0.55)):
                return start, period, run
    return None


def _find_char_cycle(
    s: str,
    *,
    min_unit: int = 16,
    min_repeats: int = 4,
) -> tuple[str, int] | None:
    """Find a character-level cycle starting at any offset (not only s[0]).

    Tolerates rare mid-loop mutations (e.g. one ``bot_bot`` typo): counts
    non-consecutive matches of the unit, not only a pure prefix run.
    """
    n = len(s)
    if n < min_unit * min_repeats:
        return None
    # Prefer longer units; cap search for performance on huge degenerations.
    max_unit = min(n // min_repeats, 280)
    # Sample start offsets: 0 and after first sentence-ish break.
    starts = {0}
    for m in re.finditer(r"(?:…|[.!?]\s+)", s[: min(n, 400)]):
        starts.add(m.end())
        if len(starts) >= 12:
            break
    # Also try after leading ellipsis glued to text («…Поняла»).
    if s.startswith("…") and len(s) > 1:
        starts.add(0)

    best: tuple[str, int] | None = None
    for start in sorted(starts):
        if start >= n // 2:
            continue
        tail = s[start:]
        tn = len(tail)
        limit = min(tn // min_repeats, max_unit)
        for unit_len in range(min_unit, limit + 1):
            unit = tail[:unit_len]
            if not unit.strip():
                continue
            # Pure consecutive run from start of tail.
            repeats = 0
            pos = 0
            while pos + unit_len <= tn and tail[pos : pos + unit_len] == unit:
                repeats += 1
                pos += unit_len
            covered = pos
            # If a rare mutation breaks the run early, fall back to global count.
            if repeats < min_repeats or covered < int(tn * 0.7):
                global_hits = _count_phrase_runs(s, unit)
                if global_hits >= min_repeats and global_hits * unit_len >= int(n * 0.55):
                    repeats = global_hits
                    covered = global_hits * unit_len
                else:
                    continue
            if repeats >= min_repeats and covered >= int(tn * 0.55):
                if best is None or repeats * unit_len > len(best[0]) * best[1]:
                    best = (unit, repeats)
    return best


def _collapse_by_ellipsis_segments(s: str, *, max_repeats: int = 1) -> str | None:
    """Collapse «…phrase…phrase…» when segments are near-identical.

    Handles rare one-off mutations (``bot_bot``) by keeping the dominant segment.
    """
    if "…" not in s:
        return None
    segs = [p for p in re.split(r"(?=…)", s) if p]
    if len(segs) < 4:
        return None
    from collections import Counter

    counts = Counter(segs)
    top, top_n = counts.most_common(1)[0]
    if top_n < 4 or top_n < len(segs) * 0.5 or len(top.strip()) < 16:
        # Dominant by length-normalized form (ignore one-char typos in middle).
        def _soft(x: str) -> str:
            return re.sub(r"[_\s]+", "", _norm_unit(x))[:80]

        soft_counts: Counter[str] = Counter()
        soft_example: dict[str, str] = {}
        for seg in segs:
            key = _soft(seg)
            if len(key) < 12:
                continue
            soft_counts[key] += 1
            soft_example.setdefault(key, seg)
        if not soft_counts:
            return None
        key, top_n = soft_counts.most_common(1)[0]
        if top_n < 4 or top_n < len(segs) * 0.5:
            return None
        top = soft_example[key]
    keep = max(1, max_repeats)
    prefix: list[str] = []
    for seg in segs:
        if seg == top or _norm_unit(seg) == _norm_unit(top):
            break
        # Soft match prefix end
        if len(seg) >= 16 and _norm_unit(seg)[:40] == _norm_unit(top)[:40]:
            break
        prefix.append(seg)
    return ("".join(prefix) + top * keep).strip() or None


def _hard_trim_loop(s: str, *, max_len: int = 220) -> str:
    """Last-resort: keep the first sensible chunk of a looped monologue."""
    text = (s or "").strip()
    if len(text) <= max_len:
        return text
    # Prefer first ellipsis-delimited segment.
    if "…" in text[1:]:
        first = text.split("…", 1)[0]
        if text.startswith("…"):
            # «…phrase…phrase» → keep first full segment
            segs = [p for p in re.split(r"(?=…)", text) if p]
            if segs:
                first = segs[0]
        if 16 <= len(first) <= max_len:
            return first.strip()
    cut = text[:max_len]
    m = re.search(r"[.!?…]\s*", cut[::-1])
    if m:
        cut = cut[: len(cut) - m.start()]
    return cut.rstrip() + "…"


def _count_phrase_runs(s: str, phrase: str) -> int:
    if not phrase or len(phrase) < 8:
        return 0
    # Overlapping-safe count
    count = 0
    start = 0
    while True:
        i = s.find(phrase, start)
        if i < 0:
            break
        count += 1
        start = i + max(1, len(phrase) // 2)
    return count


def is_pathological_repetition(
    text: str | None,
    *,
    min_unit: int = 16,
    min_repeats: int = 4,
) -> bool:
    """True when the same phrase/cycle is repeated many times (model degeneration)."""
    s = (text or "").strip()
    if len(s) < min_unit * min_repeats:
        return False

    units = _sentence_units(s)
    if _find_sentence_cycle(units, min_repeats=min_repeats) is not None:
        return True

    if _find_char_cycle(s, min_unit=min_unit, min_repeats=min_repeats) is not None:
        return True

    # High-frequency mid-string phrase (covers prefix mismatch cases).
    # Take a candidate window from the middle of the text.
    if len(s) >= min_unit * min_repeats:
        mid = len(s) // 3
        for win in (40, 60, 80, 100, 120):
            if mid + win > len(s):
                continue
            cand = s[mid : mid + win]
            # Align candidate to a sentence-ish start inside window
            m = re.search(r"[.!?…]\s*", cand)
            if m and m.end() < len(cand) - 12:
                cand = cand[m.end() :]
            cand = cand.strip()
            if len(cand) < min_unit:
                continue
            if _count_phrase_runs(s, cand) >= min_repeats:
                return True
    return False


def collapse_repetitive_text(
    text: str | None,
    *,
    max_repeats: int = 1,
    min_unit: int = 16,
) -> str:
    """Collapse model loops like «фраза…фраза…фраза…» to a short form.

    Default ``max_repeats=1`` keeps a single copy of a detected cycle so users
    never see monologue spam in messengers.

    Robust to:
    - dots inside identifiers (``bot.py``)
    - rare mid-loop mutations (``bot_bot`` typo once)
    - ellipsis-glued monologues without spaces
    """
    raw = (text or "").strip()
    if len(raw) < min_unit * 3:
        return raw

    collapsed = raw
    units = _sentence_units(raw)
    cycle = _find_sentence_cycle(units, min_repeats=3)
    if cycle is not None:
        start, period, run = cycle
        keep = max(1, min(max_repeats, run))
        # Preserve optional non-looping prefix sentences.
        prefix = units[:start]
        block = units[start : start + period]
        kept_units = prefix + block * keep
        # Prefer original separators lightly by joining with space after period.
        collapsed = " ".join(kept_units).strip()
        # If prefix was empty and we still have a huge string, fall through
        # to char cycle as a secondary pass.
        if len(collapsed) <= len(raw) * 0.5 or run >= 4:
            pass  # good enough
        else:
            collapsed = raw

    # Character-level cycle (prefix or mid-string after first break)
    if len(collapsed) > min_unit * 4:
        found = _find_char_cycle(collapsed, min_unit=min_unit, min_repeats=3)
        if found is not None:
            unit, repeats = found
            keep = max(1, min(max_repeats, repeats))
            # If cycle starts mid-string, keep the unique prefix once.
            idx = collapsed.find(unit)
            prefix = collapsed[:idx] if idx > 0 else ""
            # Avoid stacking a near-duplicate first sentence with the loop unit.
            candidate = (prefix + unit * keep).strip()
            if len(candidate) < len(collapsed):
                collapsed = candidate

    # Ellipsis-segment mode: dominant «…phrase» even with one mutated copy.
    if len(collapsed) > min_unit * 6 and "…" in collapsed:
        seg = _collapse_by_ellipsis_segments(collapsed, max_repeats=max_repeats)
        if seg is not None and len(seg) < len(collapsed) * 0.5:
            collapsed = seg

    # Consecutive identical sentence units (period-1 residual)
    if len(collapsed) >= min_unit * 3:
        pieces = re.split(r"((?:…+|[!?]+|\.\s+|\n+)\s*)", collapsed)
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
            if norm == prev_norm and len(norm) >= min(12, min_unit):
                run += 1
                if run <= max_repeats:
                    out.append(chunk + sep)
            else:
                prev_norm = norm
                run = 1
                out.append(chunk + sep)
        collapsed = "".join(out).strip()

    # Hard safety: still pathological and long → first segment only.
    if len(collapsed) > min_unit * 8 and is_pathological_repetition(
        collapsed, min_unit=min_unit, min_repeats=3
    ):
        trimmed = _hard_trim_loop(collapsed)
        if len(trimmed) < len(collapsed):
            collapsed = trimmed

    if len(collapsed) < len(raw) * 0.9 and len(raw) > 120:
        logger.warning(
            "Collapsed pathological model repetition (%d → %d chars)",
            len(raw),
            len(collapsed),
        )
        try:
            from core.monitoring.metrics import metrics

            metrics.increment("content_loop_collapsed")
            metrics.record("content_loop_chars_in", float(len(raw)))
            metrics.record("content_loop_chars_out", float(len(collapsed)))
        except Exception:
            pass
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
    agent_pipeline: str | None = None,
) -> str:
    """Pick user-visible assistant text; empty string means nothing to show."""
    from core.agent_pipeline import is_classic_pipeline, is_modern_pipeline
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

    if finish_reason == "length":
        # Classic (≈1.0.2): deliver collapsed text only — no system truncation wall.
        if is_classic_pipeline(agent_pipeline):
            if not text:
                return t("llm.truncated", locale)
            if is_pathological_repetition(text, min_repeats=3):
                collapsed = collapse_repetitive_text(text) or text
                # Never ship multi-KB monologue spam even if detectors disagree.
                if len(collapsed) > 400 and is_pathological_repetition(
                    collapsed, min_repeats=3
                ):
                    collapsed = _hard_trim_loop(collapsed)
                return collapsed
            return text
        # Modern: explicit truncation notice (anti-spam UX).
        notice = t("llm.truncated", locale)
        if not text:
            return notice
        if is_pathological_repetition(text, min_repeats=3):
            collapsed = collapse_repetitive_text(text)
            if collapsed and len(collapsed) <= 200:
                return f"{collapsed}\n\n{notice}"
            return notice
        short = text if len(text) <= 500 else text[:500].rstrip() + "…"
        return f"{short}\n\n{notice}"
    # Any finish reason: never deliver multi-KB glued monologue.
    if text and len(text) > 400 and is_pathological_repetition(text, min_repeats=3):
        collapsed = collapse_repetitive_text(text) or text
        if len(collapsed) > 400 and is_pathological_repetition(collapsed, min_repeats=3):
            collapsed = _hard_trim_loop(collapsed)
        return collapsed
    if text:
        return text
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