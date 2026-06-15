"""
Step Orchestrate Node — manages transitions between plan steps.

Inserted between plan_review and react in the plan_and_execute graph.
For each plan step:
1. Injects the step description as a user message for react_node
2. Sets is_step_complete=False and tracks step start
3. After react_node completes the step (is_step_complete=True or no tool_calls):
   - Emits PlanStepCompletedEvent
   - Advances current_plan_step
   - If all steps done → finalize
   - If more steps → injects next step description

This replaces the old execute_step_node which couldn't call tools.
Now each plan step is executed through react_node + tool_execution_node,
giving the agent full tool-calling capability within each step.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def step_orchestrate_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Orchestrate plan step execution.

    Manages transitions between plan steps by injecting step context
    into the conversation, detecting step completion, and advancing
    the plan counter.

    Args:
        state: Current graph state with plan_steps and current_plan_step.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with step context or finalization signal.
    """
    agent = get_agent_from_config(config)
    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    conversation_id = state.get("conversation_id", "default")
    step_count = state.get("step_count", 0)
    is_step_complete = state.get("is_step_complete", False)

    # If no plan steps or index out of range, finalize
    if not plan_steps or current_step_idx >= len(plan_steps):
        logger.info("Step orchestrate: all steps complete or no plan, finalizing")
        return {
            "is_final": True,
            "final_response": state.get("final_response", "Plan execution completed."),
        }

    current_step = plan_steps[current_step_idx]
    step_description = current_step.get("description", "")
    step_num = current_step.get("step", current_step_idx + 1)
    success_criteria = current_step.get("success_criteria", "")

    # Check if the previous step just completed
    if is_step_complete and current_step_idx > 0:
        # Emit completion event for the previous step
        prev_idx = current_step_idx - 1
        prev_step = plan_steps[prev_idx] if prev_idx < len(plan_steps) else None
        if agent and hasattr(agent, "emit") and prev_step:
            from core.agent_events import PlanStepCompletedEvent
            agent.emit(PlanStepCompletedEvent(
                step_number=prev_step.get("step", prev_idx + 1),
                total_steps=len(plan_steps),
                step_description=prev_step.get("description", "")[:200],
                conversation_id=conversation_id,
            ))

    # Check if current step has been completed by react
    if is_step_complete:
        wave_indices = state.get("subagent_wave_step_indices") or []
        if wave_indices:
            new_step_idx = max(wave_indices) + 1
        else:
            new_step_idx = current_step_idx + 1

        # Check for per-step step limit
        try:
            from config import settings
            getattr(settings, "max_steps_per_plan_step", 5)
        except Exception:
            pass

        # Emit completion event for current step
        if agent and hasattr(agent, "emit"):
            from core.agent_events import PlanStepCompletedEvent
            agent.emit(PlanStepCompletedEvent(
                step_number=step_num,
                total_steps=len(plan_steps),
                step_description=step_description[:200],
                conversation_id=conversation_id,
            ))

        logger.info(f"Step orchestrate: step {step_num}/{len(plan_steps)} complete, advancing to step {new_step_idx + 1 if new_step_idx < len(plan_steps) else 'final'}")

        # Check if all steps are done
        if new_step_idx >= len(plan_steps):
            # All steps complete — finalize
            # Disable auto-approve since plan execution is done
            if agent and hasattr(agent, "tools") and hasattr(agent.tools, "_action_guard"):
                agent.tools._action_guard._auto_approve_plan_execution = False
            if agent and hasattr(agent, "emit"):
                from core.agent_events import PlanCompletedEvent
                agent.emit(PlanCompletedEvent(
                    total_steps=len(plan_steps),
                    conversation_id=conversation_id,
                ))

            clear_orch: dict = {
                "subagent_orchestration": None,
                "subagent_delegate_next": False,
                "subagent_awaiting_synthesis": False,
                "subagent_wave_step_indices": None,
            }
            return {
                "current_plan_step": new_step_idx,
                "is_step_complete": False,
                "is_final": True,
                "final_response": state.get("final_response", f"Plan completed: all {len(plan_steps)} steps executed."),
                **clear_orch,
            }

        # Inject next step description as a user message
        next_step = plan_steps[new_step_idx]
        next_desc = next_step.get("description", "")
        next_tools = ", ".join(next_step.get("tools_needed", [])) or "all available tools"
        next_expected = next_step.get("expected_output", "")
        next_criteria = next_step.get("success_criteria", "")

        next_step_msg = (
            f"[Plan Step {new_step_idx + 1}/{len(plan_steps)}] {next_desc}\n"
            f"Tools: {next_tools}\n"
            f"Expected: {next_expected}\n"
            f"Success criteria: {next_criteria}"
        )

        messages = list(state.get("messages", []))
        messages.append({"role": "user", "content": next_step_msg})

        # Save to memory
        if agent and hasattr(agent, "memory"):
            try:
                await agent.memory.save_message(
                    conversation_id, "user",
                    f"[Plan Step {new_step_idx + 1}] {next_desc}",
                    metadata={"type": "plan_step", "step": new_step_idx + 1},
                )
            except Exception as e:
                logger.warning(f"Failed to save plan step message: {e}")

        orch_updates: dict = {
            "subagent_awaiting_synthesis": False,
            "subagent_wave_step_indices": None,
        }
        raw_orch = state.get("subagent_orchestration")
        if raw_orch:
            from core.subagents.orchestrator import OrchestrationPlan

            orch_plan = OrchestrationPlan.from_dict(raw_orch)
            if int(state.get("current_subagent_wave", 0)) >= len(orch_plan.waves):
                orch_updates["subagent_orchestration"] = None
                orch_updates["subagent_delegate_next"] = False

        return {
            "current_plan_step": new_step_idx,
            "is_step_complete": False,
            "current_step_start_count": step_count,
            "messages": messages,
            **orch_updates,
        }

    cfg = getattr(agent, "config", None) if agent else None
    from core.config_utils import is_subagents_enabled

    if (
        is_subagents_enabled(cfg)
        and not state.get("subagent_orchestration")
        and not state.get("subagent_awaiting_synthesis")
    ):
        from core.subagents.orchestrator import build_orchestration_plan

        orch_plan = build_orchestration_plan(
            plan_analysis=state.get("plan_analysis"),
            plan_steps=plan_steps,
            current_step_index=current_step_idx,
            enable_subagents=True,
            max_concurrent=int(getattr(cfg, "subagent_max_concurrent", 4) or 4),
        )
        if orch_plan.enabled:
            return {
                "subagent_orchestration": orch_plan.to_dict(),
                "current_subagent_wave": 0,
                "subagent_delegate_next": True,
                "is_step_complete": False,
                "current_step_start_count": step_count,
            }

    # First entry for this step — inject step context
    step_context_msg = (
        f"[Plan Step {step_num}/{len(plan_steps)}] {step_description}\n"
        f"Tools: {', '.join(current_step.get('tools_needed', [])) or 'all available tools'}\n"
        f"Expected: {current_step.get('expected_output', '')}\n"
        f"Success criteria: {success_criteria}"
    )

    messages = list(state.get("messages", []))

    # Check if step context is already injected (avoid duplicate injection)
    already_injected = any(
        msg.get("role") == "user" and f"[Plan Step {step_num}/" in msg.get("content", "")
        for msg in messages[-5:]  # Check last 5 messages
    )

    if not already_injected:
        messages.append({"role": "user", "content": step_context_msg})

        # Save to memory
        if agent and hasattr(agent, "memory"):
            try:
                await agent.memory.save_message(
                    conversation_id, "user",
                    f"[Plan Step {step_num}] {step_description}",
                    metadata={"type": "plan_step", "step": step_num},
                )
            except Exception as e:
                logger.warning(f"Failed to save plan step message: {e}")

    # Log step start
    logger.info(f"Step orchestrate: starting step {step_num}/{len(plan_steps)}: {step_description[:80]}...")

    # Enable auto-approve for plan execution — tools within plan steps
    # don't require individual confirmation since the plan was already approved
    if agent and hasattr(agent, "tools") and hasattr(agent.tools, "_action_guard"):
        agent.tools._action_guard._auto_approve_plan_execution = True

    return {
        "is_step_complete": False,
        "current_step_start_count": step_count,
        "messages": messages,
    }


from core.graph.routers import (  # noqa: E402, F401
    route_after_react_plan,
    route_after_step_orchestrate,
)

