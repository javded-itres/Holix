"""
Execute Step Node — executes a single plan step by calling the LLM.

Used in plan_and_execute mode. Each call:
1. Reads the current plan step from state
2. Builds a prompt for that step (including context from previous steps)
3. Calls the LLM to generate a response for that step
4. Saves the response and advances the plan counter
5. If all steps are done, signals finalization
"""

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from openai import AsyncOpenAI

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


STEP_PROMPT_TEMPLATE = """You are executing step {step_num} of {total_steps} in a structured plan.

## Current Step
{description}

## Tools Available for This Step
{tools_needed}

## Expected Output
{expected_output}

## Results from Previous Steps
{previous_results}

## Instructions
Focus ONLY on completing this step. Do not try to do the entire task at once.
Use the available tools as needed. Provide a clear, complete result for this step.
"""

def _step_system_prompt(profile_name: str | None = None) -> str:
    from core.project.holix_md import append_holix_project_context, task_context_note
    from core.prompt_builder import language_instruction_block

    base = (
        "You are a helpful assistant executing a structured plan step by step. "
        "Complete the current step thoroughly and provide a clear result. "
        f"{task_context_note()}"
    )
    lang_block = language_instruction_block(profile_name=profile_name)
    return append_holix_project_context(f"{base}\n\n{lang_block}")


async def execute_step_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Execute the current plan step by calling the LLM.

    Reads the current plan step from state, builds a prompt, calls the LLM,
    and advances the plan counter. If all steps are done, signals finalization.

    Args:
        state: Current graph state with plan_steps and current_plan_step.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with step results and advanced counter.
    """
    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    agent = get_agent_from_config(config)
    conversation_id = state.get("conversation_id", "default")

    if not plan_steps or current_step_idx >= len(plan_steps):
        # Plan complete — signal finalization
        logger.info("Plan execution complete — all steps processed")
        return {
            "is_final": True,
            "final_response": state.get("final_response", "Plan execution completed."),
        }

    # Get current step
    current_step = plan_steps[current_step_idx]
    step_description = current_step.get("description", "")
    step_num = current_step.get("step", current_step_idx + 1)

    logger.info(f"Executing plan step {step_num}/{len(plan_steps)}: {step_description[:80]}...")

    # Build the step prompt
    step_prompt = _build_step_prompt(state, current_step, step_num, len(plan_steps))

    # Save step message to memory
    if agent and hasattr(agent, "memory"):
        try:
            await agent.memory.save_message(
                conversation_id, "user",
                f"[Plan Step {step_num}] {step_description}",
                metadata={"type": "plan_step", "step": step_num},
            )
        except Exception as e:
            logger.warning(f"Failed to save plan step message: {e}")

    # Call the LLM to generate a response for this step
    if agent and hasattr(agent, "client"):
        try:
            client: AsyncOpenAI = agent.client
            model = agent.model
            temperature = 0.3  # Lower temperature for plan steps

            profile_name = getattr(getattr(agent, "config", None), "profile_name", None)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _step_system_prompt(profile_name)},
                    {"role": "user", "content": step_prompt},
                ],
                temperature=temperature,
                max_tokens=2000,
            )

            step_response = response.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"LLM call failed in execute_step: {e}")
            step_response = f"Error executing step {step_num}: {str(e)}"
    else:
        step_response = f"Step {step_num}: {step_description}"

    # Save the assistant response to memory
    if agent and hasattr(agent, "memory"):
        try:
            await agent.memory.save_message(
                conversation_id, "assistant", step_response,
                metadata={"type": "plan_step", "step": step_num},
            )
        except Exception as e:
            logger.warning(f"Failed to save step response: {e}")

    # Add both messages to state
    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": f"[Plan Step {step_num}] {step_description}"})
    messages.append({"role": "assistant", "content": step_response})

    # Advance the plan counter
    new_step = current_step_idx + 1
    is_last_step = new_step >= len(plan_steps)

    # Emit step completion event
    if agent and hasattr(agent, "emit"):
        try:
            from core.agent_events import PlanStepCompletedEvent
            agent.emit(PlanStepCompletedEvent(
                step_number=step_num,
                total_steps=len(plan_steps),
                step_description=step_description[:200],
                step_response=step_response[:200],
                conversation_id=conversation_id,
            ))
        except Exception as e:
            logger.warning(f"Failed to emit PlanStepCompletedEvent: {e}")

    updates = {
        "messages": messages,
        "current_plan_step": new_step,
    }

    if is_last_step:
        # All steps done — set final response and signal finalization
        logger.info(f"Last plan step ({step_num}) completed, finalizing")

        # Emit plan completed event
        if agent and hasattr(agent, "emit"):
            try:
                from core.agent_events import PlanCompletedEvent
                agent.emit(PlanCompletedEvent(
                    total_steps=len(plan_steps),
                    conversation_id=conversation_id,
                ))
            except Exception as e:
                logger.warning(f"Failed to emit PlanCompletedEvent: {e}")

        updates["is_final"] = True
        updates["final_response"] = step_response
    else:
        logger.info(f"Plan step {step_num}/{len(plan_steps)} completed")

    return updates


def _build_step_prompt(
    state: HolixGraphState,
    step: dict[str, Any],
    step_num: int,
    total_steps: int,
) -> str:
    """Build a prompt for executing a single plan step.

    Args:
        state: Current graph state.
        step: The step dict from the plan.
        step_num: Step number (1-based).
        total_steps: Total number of steps.

    Returns:
        Formatted prompt for this step.
    """
    description = step.get("description", "")
    tools_needed = step.get("tools_needed", [])
    expected_output = step.get("expected_output", "")

    # Collect results from previous steps
    previous_results = []
    messages = state.get("messages", [])
    for msg in messages:
        meta = msg.get("metadata", {})
        if isinstance(meta, dict) and meta.get("type") == "plan_step":
            step_i = meta.get("step", 0)
            if step_i < step_num and msg.get("role") == "assistant":
                previous_results.append(f"Step {step_i}: {msg.get('content', '')[:200]}")

    return STEP_PROMPT_TEMPLATE.format(
        step_num=step_num,
        total_steps=total_steps,
        description=description,
        tools_needed=", ".join(tools_needed) if tools_needed else "All available tools",
        expected_output=expected_output if expected_output else "Complete the task described above.",
        previous_results="\n".join(previous_results) if previous_results else "None (this is the first step).",
    )