"""
Plan Review Node — intercepts generated plans for user review before execution.

Inserted between plan_node and execute_step_node in the graph.
Emits a PlanReviewRequestEvent and blocks on an asyncio.Future until
the user (via TUI modal or API) resolves it with their choice:

- confirm_step: Proceed with execution (step-by-step confirmation in future)
- auto_execute: Execute all steps automatically
- refine: Return to plan_node with user feedback
- reject: Abort the plan

In non-interactive mode or when plan_review_enabled=False, auto-executes.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def plan_review_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Review the generated plan before execution.

    Emits a PlanReviewRequestEvent and awaits user decision via Future.
    Routes based on the user's choice:
    - confirm_step / auto_execute: proceeds to execute_step
    - refine: loops back to plan_node with feedback
    - reject: signals finalization

    In non-interactive mode or when plan_review_enabled is False,
    auto-approves with auto_execute.

    Args:
        state: Current graph state with plan_steps and plan_status.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with plan_status and optionally other fields.
    """
    agent = get_agent_from_config(config)
    plan_steps = state.get("plan_steps", [])
    conversation_id = state.get("conversation_id", "default")
    plan_status = state.get("plan_status", "pending_review")
    user_input = state.get("user_input", "")

    # If plan_status is already set (e.g., from a previous refinement pass),
    # and it's confirmed/auto_execute, skip the review
    if plan_status in ("confirmed", "auto_execute"):
        logger.info(f"Plan review: status already {plan_status}, skipping review")
        return {}

    # If no plan was generated, signal finalization
    if not plan_steps:
        return {
            "plan_status": "rejected",
            "is_final": True,
            "final_response": "No plan was generated.",
        }

    # Check config: if plan review is disabled, auto-execute
    # (this is an explicit config choice, so auto-execute is appropriate)
    try:
        cfg = getattr(agent, "config", None)
        if cfg and not cfg.plan_review_enabled:
            logger.info("Plan review: disabled in config, auto-executing")
            return {"plan_status": "auto_execute"}
    except Exception:
        pass  # If settings unavailable, proceed with review

    # Get the PlanReviewGuard
    from core.plan_review.markdown_builder import build_plan_markdown
    from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard
    guard = get_plan_review_guard()

    if guard is None:
        # No guard initialized — reject (don't auto-execute without review!)
        logger.warning("Plan review: no guard initialized, rejecting plan (will not auto-execute)")
        return {
            "plan_status": "rejected",
            "is_final": True,
            "final_response": (
                "Plan review system not available. Plan cannot be executed without review. "
                "Please try again or use /mode react for simple queries."
            ),
        }

    from core.i18n.locale import LocaleStore
    from core.profile.soul import profile_name_from_agent

    profile_name = profile_name_from_agent(agent) if agent else "default"
    ui_locale = LocaleStore(profile_name).get()

    # Build rendered Markdown for in-chat display
    rendered_markdown = build_plan_markdown(
        plan_steps=plan_steps,
        step_count=len(plan_steps),
        reasoning=_extract_reasoning(plan_steps),
        user_input=user_input,
        analysis=state.get("plan_analysis"),
        architecture=state.get("plan_architecture"),
        locale=ui_locale,
    )

    # Request review — this blocks until the user responds
    choice, feedback = await guard.request_review(
        plan_steps=plan_steps,
        conversation_id=conversation_id,
        reasoning=_extract_reasoning(plan_steps),
        user_input=user_input,
        analysis=state.get("plan_analysis"),
        architecture=state.get("plan_architecture"),
        rendered_markdown=rendered_markdown,
    )

    # Emit thinking event for logging
    if agent and hasattr(agent, "emit"):
        from core.agent_events import ThinkingEvent
        agent.emit(ThinkingEvent(
            message=f"Plan review: user chose {choice.value}",
            conversation_id=conversation_id,
        ))

    # Route based on choice
    if choice == PlanReviewChoice.CONFIRM_STEP:
        # Save the plan, proceed step-by-step
        _save_plan_if_possible(plan_steps, conversation_id, "confirmed",
                               analysis=state.get("plan_analysis"),
                               architecture=state.get("plan_architecture"))
        logger.info(f"Plan review: confirmed (step-by-step), {len(plan_steps)} steps")
        return {"plan_status": "confirmed"}

    elif choice == PlanReviewChoice.AUTO_EXECUTE:
        # Save the plan, execute all steps automatically
        _save_plan_if_possible(plan_steps, conversation_id, "auto_execute",
                               analysis=state.get("plan_analysis"),
                               architecture=state.get("plan_architecture"))
        logger.info(f"Plan review: auto-execute, {len(plan_steps)} steps")
        return {"plan_status": "auto_execute"}

    elif choice == PlanReviewChoice.REFINE:
        # Return to plan_node with feedback
        logger.info(f"Plan review: refine requested, feedback={feedback[:80]}...")
        return {
            "plan_status": "refine",
            "plan_refinement_feedback": feedback,
            "current_plan_step": 0,
        }

    else:  # REJECT or timeout fallback
        logger.info("Plan review: rejected")
        return {
            "plan_status": "rejected",
            "is_final": True,
            "final_response": (
                "Plan rejected. I'll continue in normal conversation mode. "
                "If you'd like me to create a new plan, just ask!"
            ),
        }


def _extract_reasoning(plan_steps: list) -> str:
    """Extract a brief reasoning string from plan steps."""
    if not plan_steps:
        return ""
    descriptions = [s.get("description", "") for s in plan_steps[:5]]
    return "; ".join(descriptions) if descriptions else ""


def _save_plan_if_possible(plan_steps: list, conversation_id: str, status: str,
                            analysis: dict = None, architecture: dict = None) -> None:
    """Save the plan to disk if plan_storage is available."""
    try:
        from core.plan_review.plan_storage import save_plan
        save_plan(plan_steps, conversation_id,
                  metadata={"review_status": status},
                  plan_status=status,
                  analysis=analysis,
                  architecture=architecture)
    except Exception as e:
        logger.warning(f"Failed to save plan: {e}")