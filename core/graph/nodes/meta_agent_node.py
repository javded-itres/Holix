"""
Meta-Agent Node — graph node that wraps the MetaAgent for pre-thinking analysis.

This node is inserted into the graph conditionally (when
enable_meta_agent=True) between memory_retrieval and react.
It reviews the task and context, and provides strategic guidance
that subsequent nodes can use.
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HelixGraphState, get_agent_from_config
from core.meta_agent import MetaAgent

logger = logging.getLogger(__name__)


async def meta_agent_node(state: HelixGraphState, config: RunnableConfig) -> dict:
    """Meta-agent advisory node for pre-thinking analysis.

    Reviews the user's input and retrieved context, then provides
    strategic guidance that subsequent nodes can use.

    This node is optional and adds ~200 tokens + 1 LLM call per turn.

    Args:
        state: Current graph state with user_input and memories.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with meta_decision.
    """
    agent = get_agent_from_config(config)
    user_input = state.get("user_input", "")

    if not agent or not hasattr(agent, "client"):
        logger.debug("Meta-agent: no agent/client available, skipping")
        return {"meta_decision": None}

    # Initialize meta-agent
    meta = MetaAgent(client=agent.client, model=agent.model)

    # Build context from state
    context = {
        "execution_mode": state.get("execution_mode", "react"),
        "step_count": state.get("step_count", 0),
    }

    # Build memories dict for the meta-agent
    memories = {
        "episodic": state.get("relevant_memories", [])[:2],
        "semantic": state.get("relevant_memories", [])[:2],
        "strategic": state.get("relevant_strategies", [])[:2],
    }

    # Run analysis
    try:
        decision = await meta.analyze_task(
            user_input=user_input,
            context=context,
            memories=memories,
        )

        logger.info(
            f"Meta-agent decision: mode={decision.suggested_mode}, "
            f"confidence={decision.confidence:.2f}, "
            f"hint={decision.context_hint[:50]}..."
        )

        # If meta-agent suggests a different mode, we could adjust
        # but for now we just record the decision for reference
        return {"meta_decision": {
            "suggested_mode": decision.suggested_mode,
            "context_hint": decision.context_hint,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
        }}

    except Exception as e:
        logger.warning(f"Meta-agent node failed: {e}")
        return {"meta_decision": None}