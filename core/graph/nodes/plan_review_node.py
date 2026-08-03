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

    # Get the PlanReviewGuard for *this* agent.
    # Studio (and multi-tab) keep a guard per HolixAgent instance; the global /
    # profile session registry only tracks the last agent per profile and is not
    # reliable for parallel conversations.
    from core.plan_review.markdown_builder import build_plan_markdown
    from core.plan_review.review_guard import PlanReviewChoice, resolve_plan_review_guard

    guard = resolve_plan_review_guard(agent)

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
    plan_reasoning = state.get("plan_reasoning") or _extract_reasoning(plan_steps)

    rendered_markdown = build_plan_markdown(
        plan_steps=plan_steps,
        step_count=len(plan_steps),
        reasoning=plan_reasoning,
        user_input=user_input,
        analysis=state.get("plan_analysis"),
        architecture=state.get("plan_architecture"),
        plan_report=state.get("plan_report"),
        locale=ui_locale,
    )

    # Request review — this blocks until the user responds
    choice, feedback = await guard.request_review(
        plan_steps=plan_steps,
        conversation_id=conversation_id,
        reasoning=plan_reasoning,
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

    # Keep a stable plan_id so confirm overwrites the draft (not a second file).
    plan_id = str(state.get("plan_id") or "").strip()
    if not plan_id:
        import uuid

        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        logger.warning(
            "Plan review: plan_id missing from graph state — minted %s "
            "(was dropped from HolixGraphState channels before fix)",
            plan_id,
        )
    if agent and hasattr(agent, "set_plan_id"):
        try:
            agent.set_plan_id(plan_id)
        except Exception:
            pass

    # Route based on choice
    save_kwargs = {
        "plan_steps": plan_steps,
        "conversation_id": conversation_id,
        "analysis": state.get("plan_analysis"),
        "architecture": state.get("plan_architecture"),
        "plan_report": state.get("plan_report"),
        "plan_reasoning": plan_reasoning,
        "user_input": user_input,
        "plan_id": plan_id,
        "rendered_markdown": rendered_markdown,
        "config": getattr(agent, "config", None) if agent else None,
    }

    if choice == PlanReviewChoice.CONFIRM_STEP:
        # Save the plan, proceed step-by-step
        saved = _save_plan_if_possible(status="confirmed", **save_kwargs)
        logger.info(
            "Plan review: confirmed (step-by-step), %s steps, saved=%s",
            len(plan_steps),
            saved,
        )
        if agent and hasattr(agent, "emit") and saved:
            from core.agent_events import ThinkingEvent

            agent.emit(
                ThinkingEvent(
                    message=f"Plan saved: {saved}",
                    conversation_id=conversation_id,
                )
            )
        return {"plan_status": "confirmed", "plan_id": plan_id}

    elif choice == PlanReviewChoice.AUTO_EXECUTE:
        # Save the plan, execute all steps automatically
        saved = _save_plan_if_possible(status="auto_execute", **save_kwargs)
        logger.info(
            "Plan review: auto-execute, %s steps, saved=%s",
            len(plan_steps),
            saved,
        )
        if agent and hasattr(agent, "emit") and saved:
            from core.agent_events import ThinkingEvent

            agent.emit(
                ThinkingEvent(
                    message=f"Plan saved: {saved}",
                    conversation_id=conversation_id,
                )
            )
        return {"plan_status": "auto_execute", "plan_id": plan_id}

    elif choice == PlanReviewChoice.REFINE:
        # Return to plan_node with feedback (keep plan_id so refine overwrites draft)
        logger.info(f"Plan review: refine requested, feedback={feedback[:80]}...")
        return {
            "plan_status": "refine",
            "plan_refinement_feedback": feedback,
            "current_plan_step": 0,
            "plan_id": plan_id,
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


def _save_plan_if_possible(
    *,
    plan_steps: list,
    conversation_id: str,
    status: str,
    analysis: dict | None = None,
    architecture: dict | None = None,
    plan_report: dict | None = None,
    plan_reasoning: str = "",
    user_input: str = "",
    plan_id: str = "",
    rendered_markdown: str = "",
    config=None,
) -> str | None:
    """Save the confirmed plan to workspace `.holix/plans/`. Returns JSON path or None."""
    try:
        from core.plan_review.plan_storage import save_plan

        md_path = save_plan(
            plan_steps,
            conversation_id,
            metadata={"review_status": status},
            plan_status=status,
            analysis=analysis,
            architecture=architecture,
            plan_report=plan_report,
            plan_reasoning=plan_reasoning,
            user_input=user_input,
            plan_id=plan_id,
            rendered_markdown=rendered_markdown,
            config=config,
        )
        json_path = md_path.with_suffix(".json") if md_path else None
        logger.info("Plan saved after review status=%s path=%s", status, json_path)
        return str(json_path) if json_path else str(md_path)
    except Exception as e:
        logger.exception("Failed to save plan after review: %s", e)
        return None