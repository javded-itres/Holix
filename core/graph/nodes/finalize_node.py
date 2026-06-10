"""
Finalize Node — saves the final response, triggers self-improvement,
and optionally auto-summarizes the conversation into episodic memory.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HelixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def finalize_node(state: HelixGraphState, config: RunnableConfig) -> dict:
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
            agent.emit(FinalResponseEvent(
                content=final_response,
                steps_taken=state.get("step_count", 0),
                conversation_id=conversation_id,
            ))

        # Save the rejection message to memory
        if hasattr(agent, "memory"):
            try:
                await agent.memory.save_message(conversation_id, "assistant", final_response)
            except Exception as e:
                logger.warning(f"Failed to save rejection message: {e}")

        logger.info(f"Plan rejected for conversation {conversation_id}. Switching to react mode for next message.")

    # Self-improvement check (skip if plan was rejected — nothing to learn from)
    if plan_status != "rejected":
        try:
            await _maybe_self_improve(agent, conversation_id, messages, final_response)
        except Exception as e:
            logger.warning(f"Self-improvement check failed: {e}")

    # Auto-summarize into episodic memory
    try:
        cfg = getattr(agent, "config", None)
        if cfg and cfg.auto_summarize_conversations and hasattr(
            agent.memory, "auto_summarize_conversation"
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
    """Check if a skill should be created from this session."""
    try:
        should_create = await agent.skills.should_create_skill(messages, final_response)
        if not should_create:
            return

        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return

        task_description = user_messages[0].get("content", "")

        if hasattr(agent, "emit"):
            from core.agent_events import SelfImprovementStartedEvent
            agent.emit(SelfImprovementStartedEvent(
                conversation_id=conversation_id,
                task_description=task_description[:200],
            ))

        from core.skills.generator import SkillGenerator
        generator = SkillGenerator(agent.client, model=agent.model)
        skill_data = await generator.create_skill_from_session(messages, task_description)

        if skill_data and skill_data.get("name"):
            agent_slot = getattr(agent, "agent_slot", "main")
            filepath = agent.skills.save_skill(
                name=skill_data["name"],
                description=skill_data.get("description", ""),
                content=skill_data["content"],
                tags=skill_data.get("tags", []),
                examples=skill_data.get("examples", []),
                agent_slot=agent_slot,
            )
            if hasattr(agent, "config"):
                agent.config = agent.config.with_overrides(
                    skill_assignments=agent.skills.skill_assignments
                )

            if hasattr(agent, "emit"):
                from core.agent_events import SkillCreatedEvent
                agent.emit(SkillCreatedEvent(
                    skill_name=skill_data["name"],
                    description=skill_data.get("description", ""),
                    filepath=str(filepath),
                    tags=skill_data.get("tags", []),
                    conversation_id=conversation_id,
                ))

    except Exception as e:
        logger.warning(f"Self-improvement failed: {e}")