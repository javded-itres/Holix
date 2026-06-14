"""Localized strings for messenger live progress UIs."""

from __future__ import annotations

import re

from core.i18n.locale import LocaleStore
from core.i18n.messages import t

_HOLIX_THINKING_RE = re.compile(
    r"^Holix is thinking\.{3}\s*\(mode:\s*(.+?)\)\s*$",
    re.IGNORECASE,
)
_THINKING_STEP_RE = re.compile(r"^Thinking \(step (\d+)\)", re.IGNORECASE)
_GENERATING_PLAN_RE = re.compile(
    r"^Generating execution plan \(timeout:\s*(\d+)s\)",
    re.IGNORECASE,
)


def locale_for_profile(profile: str | None) -> str:
    name = (profile or "default").strip() or "default"
    return LocaleStore(name).get()


def live_thinking_label(profile: str | None, *, fallback: str | None = None) -> str:
    loc = locale_for_profile(profile)
    text = (fallback or "").strip()
    if not text:
        return t("live.thinking", loc)
    lower = text.lower()
    if lower in {"thinking…", "thinking...", "thinking"}:
        return t("live.thinking", loc)
    match = _HOLIX_THINKING_RE.match(text)
    if match:
        return t("live.holix_thinking", loc, mode=match.group(1).strip())
    match = _THINKING_STEP_RE.match(text)
    if match:
        return t("live.thinking_step", loc, step=int(match.group(1)))
    match = _GENERATING_PLAN_RE.match(text)
    if match:
        return t("live.generating_plan", loc, timeout=match.group(1))
    if lower.startswith("model is reasoning"):
        return t("live.reasoning", loc)
    if "размышляет" in lower or "думает" in lower or "размышление" in lower:
        return text
    if "формирую план" in lower or "проверка плана" in lower:
        return text
    return text


def live_working_label(profile: str | None) -> str:
    return t("live.working", locale_for_profile(profile))


def live_reasoning_label(profile: str | None) -> str:
    return t("live.reasoning", locale_for_profile(profile))


def live_thinking_step_label(profile: str | None, step: int) -> str:
    return t("live.thinking_step", locale_for_profile(profile), step=step)


def live_holix_thinking_label(profile: str | None, mode: str) -> str:
    return t("live.holix_thinking", locale_for_profile(profile), mode=mode)


def live_processing_label(profile: str | None) -> str:
    return t("live.processing", locale_for_profile(profile))


def live_still_working_label(profile: str | None) -> str:
    return t("live.still_working", locale_for_profile(profile))


def live_generating_plan_label(profile: str | None, *, timeout: int) -> str:
    return t("live.generating_plan", locale_for_profile(profile), timeout=timeout)


def live_plan_review_label(profile: str | None, *, step_count: int) -> str:
    return t("live.plan_review", locale_for_profile(profile), count=step_count)


def live_answer_sent_label(profile: str | None) -> str:
    return t("live.answer_sent", locale_for_profile(profile))