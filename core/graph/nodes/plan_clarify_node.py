"""
Plan Clarify Node — asks the user clarifying questions before plan approval.

When the planner cannot resolve the task unambiguously, this node blocks and
collects answers. Answers are fed back into plan_node; once resolved (or the
user chooses to proceed with assumptions), execution continues to plan_review.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.plan_review.clarification import (
    MAX_CLARIFICATION_ROUNDS,
    build_clarification_markdown,
    extract_clarifying_questions,
    format_clarification_feedback,
    is_proceed_with_assumptions,
    needs_plan_clarification,
)
from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard

logger = logging.getLogger(__name__)


async def plan_clarify_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Ask clarifying questions when the generated plan is ambiguous."""
    agent = get_agent_from_config(config)
    analysis = state.get("plan_analysis")
    plan_report = state.get("plan_report")
    conversation_id = state.get("conversation_id", "default")
    user_input = state.get("user_input", "")
    clarification_rounds = int(state.get("plan_clarification_rounds", 0) or 0)

    if not needs_plan_clarification(analysis, plan_report=plan_report):
        return {"plan_status": "pending_review"}

    questions = extract_clarifying_questions(analysis)
    if not questions and analysis:
        reason = str(analysis.get("clarification_reason", "")).strip()
        fallback = t_fallback(agent, "plan.clarify.default_question")
        questions = [reason or fallback]

    if clarification_rounds >= MAX_CLARIFICATION_ROUNDS:
        logger.warning(
            "Plan clarification: max rounds (%s) reached, proceeding to review",
            MAX_CLARIFICATION_ROUNDS,
        )
        return {"plan_status": "pending_review"}

    try:
        cfg = getattr(agent, "config", None)
        if cfg and (not cfg.plan_review_enabled or cfg.non_interactive):
            logger.info("Plan clarification: non-interactive, skipping questions")
            return {"plan_status": "pending_review"}
    except Exception:
        pass

    guard = get_plan_review_guard()
    if guard is None:
        return {"plan_status": "pending_review"}

    from core.i18n.locale import LocaleStore
    from core.profile.soul import profile_name_from_agent

    profile_name = profile_name_from_agent(agent) if agent else "default"
    ui_locale = LocaleStore(profile_name).get()
    rendered_markdown = build_clarification_markdown(
        questions,
        analysis=analysis,
        user_input=user_input,
        locale=ui_locale,
    )

    choice, feedback = await guard.request_review(
        plan_steps=state.get("plan_steps", []),
        conversation_id=conversation_id,
        user_input=user_input,
        analysis=analysis,
        rendered_markdown=rendered_markdown,
        phase="clarification",
        clarifying_questions=questions,
    )

    if choice == PlanReviewChoice.REJECT:
        return {
            "plan_status": "rejected",
            "is_final": True,
            "final_response": t_fallback(agent, "plan.clarify.rejected"),
        }

    if choice == PlanReviewChoice.PROCEED_ASSUMPTIONS:
        logger.info("Plan clarification: user chose to proceed with assumptions")
        return {"plan_status": "pending_review"}

    if choice == PlanReviewChoice.REFINE and feedback.strip():
        logger.info("Plan clarification: answers received (%s chars)", len(feedback))
        return {
            "plan_status": "refine",
            "plan_refinement_feedback": format_clarification_feedback(questions, feedback),
            "plan_clarification_rounds": clarification_rounds + 1,
            "current_plan_step": 0,
        }

    return {"plan_status": "pending_review"}


def t_fallback(agent, key: str) -> str:
    from core.i18n.locale import LocaleStore
    from core.profile.soul import profile_name_from_agent
    from core.i18n.messages import t

    profile_name = profile_name_from_agent(agent) if agent else "default"
    return t(key, LocaleStore(profile_name).get())