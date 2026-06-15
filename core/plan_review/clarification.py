"""Helpers for plan clarification (questions before plan approval)."""

from __future__ import annotations

from typing import Any

from core.i18n.locale import normalize_locale
from core.i18n.messages import t

MAX_CLARIFICATION_ROUNDS = 3

PROCEED_ASSUMPTIONS_PHRASES = frozenset({
    "продолжай",
    "продолжи",
    "продолжай с допущениями",
    "с допущениями",
    "без уточнений",
    "как есть",
    "proceed",
    "proceed anyway",
    "continue",
    "assume",
    "with assumptions",
    "skip questions",
    "no questions",
})

PROCEED_ASSUMPTIONS_MARKERS = (
    "с допущениями",
    "без уточнений",
    "with assumptions",
    "proceed anyway",
    "skip questions",
)


def extract_clarifying_questions(analysis: dict[str, Any] | None) -> list[str]:
    if not analysis:
        return []
    raw = analysis.get("clarifying_questions", [])
    if not isinstance(raw, list):
        return []
    return [str(q).strip() for q in raw if str(q).strip()]


def needs_plan_clarification(
    analysis: dict[str, Any] | None,
    *,
    plan_report: dict[str, Any] | None = None,
) -> bool:
    """Return True when the planner could not resolve the task unambiguously."""
    if not analysis:
        return False

    questions = extract_clarifying_questions(analysis)
    if questions:
        return True

    if analysis.get("needs_clarification"):
        return True

    ambiguity = str(analysis.get("ambiguity_level", "")).strip().lower()
    if ambiguity in {"high", "medium"}:
        return True

    if plan_report:
        summary = plan_report.get("summary") or {}
        if isinstance(summary, dict):
            critical = summary.get("critical_risks") or []
            for item in critical:
                text = str(item).lower()
                if any(
                    marker in text
                    for marker in (
                        "неясн",
                        "ambiguous",
                        "unclear",
                        "уточн",
                        "не определ",
                        "not specified",
                    )
                ):
                    return True

    return False


def build_clarification_markdown(
    questions: list[str],
    *,
    analysis: dict[str, Any] | None = None,
    user_input: str = "",
    locale: str | None = None,
) -> str:
    loc = normalize_locale(locale)
    sections = [f"# {t('plan.clarify.title', loc)}", ""]

    if user_input:
        display = user_input[:300] + ("…" if len(user_input) > 300 else "")
        sections.append(f"> **{t('plan.task_label', loc)}** {display}\n")

    reason = ""
    if analysis:
        reason = str(analysis.get("clarification_reason", "")).strip()
    if reason:
        sections.append(f"**{t('plan.clarify.reason', loc)}** {reason}\n")

    sections.append(f"## {t('plan.clarify.questions', loc)}\n")
    for index, question in enumerate(questions, 1):
        sections.append(f"{index}. {question}")
    sections.append("")

    sections.append(f"*{t('plan.clarify.hint', loc)}*")
    return "\n".join(sections)


def is_proceed_with_assumptions(text: str) -> bool:
    cleaned = text.strip().lower().rstrip("!.,;:?!")
    if cleaned in PROCEED_ASSUMPTIONS_PHRASES:
        return True
    return any(marker in cleaned for marker in PROCEED_ASSUMPTIONS_MARKERS)


def parse_plan_review_response(
    text: str,
    *,
    phase: str = "approval",
) -> tuple[str, str]:
    """Parse user text into (PlanReviewChoice value, feedback)."""
    from core.plan_review.review_guard import PlanReviewChoice

    text_stripped = text.strip()
    text_clean = text_stripped.lower().rstrip("!.,;:?!")
    reject_words = {
        "нет", "no", "отмена", "cancel", "reject", "отклоняю",
        "стоп", "stop", "abort",
    }
    confirm_words = {
        "да", "yes", "ок", "ok", "confirm", "выполняй", "давай",
        "согласен", "подтверждаю", "запускай", "окей", "ладно",
        "хорошо", "угу", "ага", "go", "exec", "поехали",
    }

    if text_clean in reject_words:
        return PlanReviewChoice.REJECT.value, ""

    if phase == "clarification":
        if is_proceed_with_assumptions(text_stripped):
            return PlanReviewChoice.PROCEED_ASSUMPTIONS.value, ""
        return PlanReviewChoice.REFINE.value, text_stripped

    if text_clean in confirm_words:
        return PlanReviewChoice.AUTO_EXECUTE.value, ""
    return PlanReviewChoice.REFINE.value, text_stripped


def format_clarification_feedback(questions: list[str], user_answer: str) -> str:
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    return (
        "User answers to clarifying questions:\n"
        f"{numbered}\n\n"
        f"Answers:\n{user_answer.strip()}\n\n"
        "Regenerate the plan using these answers. Clear `clarifying_questions` and set "
        "`needs_clarification` to false when the task is now unambiguous."
    )