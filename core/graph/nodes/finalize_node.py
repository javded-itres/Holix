"""
Finalize Node — saves the final response, triggers self-improvement,
and optionally auto-summarizes the conversation into episodic memory.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.presenters.final_content import is_aborted_final_response

logger = logging.getLogger(__name__)


async def finalize_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Finalize the graph execution.

    1. If plan was rejected, emit a clear message and clean up plan state
    2. Triggers self-improvement (skill creation) check
    3. Auto-summarizes conversation into episodic memory (if enabled)

    This node always leads to END.

    Args:
        state: Current graph state with final_response.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Empty partial state (no further updates needed).
    """
    agent = get_agent_from_config(config)
    conversation_id = state.get("conversation_id", "default")
    messages = state.get("messages", [])
    final_response = state.get("final_response", "")
    plan_status = state.get("plan_status", "")

    if not agent:
        return {}

    if is_aborted_final_response(final_response):
        logger.info(
            "Skipping post-finalize work for aborted run (conversation=%s)",
            conversation_id,
        )
        return {}

    # Disable plan execution auto-approve since we're finalizing
    guard = getattr(getattr(agent, "tools", None), "_action_guard", None)
    if guard is not None:
        guard._auto_approve_plan_execution = False

    # If plan was rejected, ensure final response is informative
    if plan_status == "rejected":
        if not final_response or final_response == "Plan rejected by user.":
            final_response = (
                "Plan rejected. I'll continue in normal conversation mode. "
                "If you'd like me to create a new plan, just ask!"
            )

        # Emit the final response as a regular message
        if hasattr(agent, "emit"):
            from core.agent_events import FinalResponseEvent

            agent.emit(
                FinalResponseEvent(
                    content=final_response,
                    steps_taken=state.get("step_count", 0),
                    conversation_id=conversation_id,
                )
            )

        # Save the rejection message to memory
        if hasattr(agent, "memory"):
            try:
                await agent.memory.save_message(conversation_id, "assistant", final_response)
            except Exception as e:
                logger.warning(f"Failed to save rejection message: {e}")

        logger.info(
            f"Plan rejected for conversation {conversation_id}. Switching to react mode for next message."
        )

    # Self-improvement check (skip if plan was rejected — nothing to learn from)
    if plan_status != "rejected":
        try:
            await _maybe_self_improve(agent, conversation_id, messages, final_response)
        except Exception as e:
            logger.warning(f"Self-improvement check failed: {e}")

    # Auto-summarize into episodic memory
    try:
        cfg = getattr(agent, "config", None)
        if (
            cfg
            and cfg.auto_summarize_conversations
            and hasattr(agent.memory, "auto_summarize_conversation")
        ):
            await agent.memory.auto_summarize_conversation(
                conversation_id=conversation_id,
                messages=messages,
                llm_client=agent.client,
                model=agent.model,
            )
    except Exception as e:
        logger.warning(f"Auto-summarization failed: {e}")

    return {}


async def _maybe_self_improve(agent, conversation_id, messages, final_response):
    """Stage a skill proposal from this session (does not write live skills)."""
    try:
        from core.skills.self_improve import maybe_propose_skill

        await maybe_propose_skill(agent, conversation_id, messages, final_response)
    except Exception as e:
        logger.warning(f"Self-improvement failed: {e}")
