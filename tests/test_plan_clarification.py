"""Tests for plan clarification flow."""

from core.plan_review.clarification import (
    build_clarification_markdown,
    needs_plan_clarification,
    parse_plan_review_response,
)
from core.plan_review.review_guard import PlanReviewChoice


class TestNeedsPlanClarification:
    def test_with_questions(self):
        analysis = {
            "needs_clarification": False,
            "clarifying_questions": ["Which database?"],
        }
        assert needs_plan_clarification(analysis) is True

    def test_with_flag_only(self):
        analysis = {"needs_clarification": True, "clarifying_questions": []}
        assert needs_plan_clarification(analysis) is True

    def test_clear_task(self):
        analysis = {
            "needs_clarification": False,
            "ambiguity_level": "low",
            "clarifying_questions": [],
        }
        assert needs_plan_clarification(analysis) is False


class TestParsePlanReviewResponse:
    def test_clarification_answer(self):
        choice, feedback = parse_plan_review_response(
            "Use PostgreSQL and FastAPI",
            phase="clarification",
        )
        assert choice == PlanReviewChoice.REFINE.value
        assert "PostgreSQL" in feedback

    def test_clarification_proceed(self):
        choice, _ = parse_plan_review_response(
            "продолжай с допущениями",
            phase="clarification",
        )
        assert choice == PlanReviewChoice.PROCEED_ASSUMPTIONS.value

    def test_approval_confirm(self):
        choice, feedback = parse_plan_review_response("да", phase="approval")
        assert choice == PlanReviewChoice.AUTO_EXECUTE.value
        assert feedback == ""


class TestClarificationMarkdown:
    def test_russian_markdown(self):
        md = build_clarification_markdown(
            ["Какой фреймворк?", "Какая БД?"],
            analysis={"clarification_reason": "Стек не указан"},
            user_input="Сделай API",
            locale="ru",
        )
        assert "Нужны уточнения" in md
        assert "Какой фреймворк?" in md
        assert "Стек не указан" in md