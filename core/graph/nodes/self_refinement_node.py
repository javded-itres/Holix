"""
Self-Refinement Node — graph node that triggers the self-refinement loop.

Activated when the meta-agent sets needs_refinement=True in state.
Routes back to react_node with refinement context, or to END if
iterations are exhausted.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.meta_agent import MetaAgent
from core.self_refinement.loop import SelfRefinementLoop

logger = logging.getLogger(__name__)


async def self_refinement_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Run the self-refinement loop if the meta-agent flagged it.

    This node is activated when needs_refinement=True in state.
    It evaluates the current response, and if quality is below
    threshold, appends a refinement prompt and routes back to
    the react node for another attempt.

    Args:
        state: Current graph state.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update. Either:
        - Sets refinement context and loops back to react
        - Or signals finalization if iterations exhausted
    """
    agent = get_agent_from_config(config)
    conversation_id = state.get("conversation_id", "default")
    final_response = state.get("final_response", "")
    refinement_iterations = state.get("refinement_iterations", 0)
    max_refinement_iterations = state.get("max_refinement_iterations", 2)

    # Check if we've exhausted iterations
    if refinement_iterations >= max_refinement_iterations:
        logger.info(
            f"Self-refinement: max iterations ({max_refinement_iterations}) reached, finalizing"
        )
        return {
            "needs_refinement": False,  # Stop refining
        }

    if not agent:
        logger.debug("Self-refinement: no agent available, skipping")
        return {"needs_refinement": False}

    # Initialize meta-agent and refinement loop
    meta = MetaAgent(client=agent.client, model=agent.model)
    loop = SelfRefinementLoop(
        meta_agent=meta,
        max_iterations=max_refinement_iterations - refinement_iterations,
    )

    # Run refinement
    state_dict = dict(state)
    output = await loop.refine(state_dict)

    # Save refinement experience to memory
    if hasattr(agent, "memory") and hasattr(agent.memory, "episodic"):
        user_input = state.get("user_input", "")
        await loop.save_refinement_experience(
            memory=agent.memory,
            conversation_id=conversation_id,
            output=output,
            original_task=user_input,
        )

    if output.was_improved and output.final_assessment:
        # Quality improved — update the response and signal another round
        logger.info(
            f"Self-refinement iteration {refinement_iterations + 1}: "
            f"quality {output.quality_scores[-1]:.2f} "
            f"(was {output.quality_scores[0]:.2f})"
        )

        # If quality now meets threshold, finalize
        if output.quality_scores[-1] >= loop._quality_threshold:
            return {
                "final_response": output.response,
                "refinement_iterations": refinement_iterations + 1,
                "needs_refinement": False,
            }

        # Otherwise, loop back for more refinement
        # Build refinement context as a message
        messages = list(state.get("messages", []))
        if output.final_assessment and output.final_assessment.refinement_prompt:
            messages.append({
                "role": "system",
                "content": f"[Self-Refinement] Please improve: {output.final_assessment.refinement_prompt}",
            })

        return {
            "messages": messages,
            "final_response": output.response,
            "refinement_iterations": refinement_iterations + 1,
            "is_final": False,  # Signal to continue
            "needs_refinement": True,
        }

    else:
        # No improvement possible — finalize
        logger.info("Self-refinement: no improvement possible, finalizing")
        return {
            "final_response": output.response if output.response else final_response,
            "refinement_iterations": refinement_iterations + 1,
            "needs_refinement": False,
        }