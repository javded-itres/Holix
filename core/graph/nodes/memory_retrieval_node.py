"""
Memory Retrieval Node — the first node in every graph run.

Queries all 4 long-term memory stores in parallel and populates
relevant_memories, relevant_skills, and relevant_strategies in state.
Replaces the scattered memory retrieval currently at the top of run_agent_loop().
"""

import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def memory_retrieval_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Retrieve relevant context from all long-term memory stores.

    This is the first node in every graph run. It queries:
    - Episodic memory: past experiences with similar tasks
    - Semantic memory: relevant facts and knowledge
    - Strategic memory: applicable strategies and preferences
    - Procedural memory: skills with outcome data

    All queries run in parallel via asyncio.gather for efficiency.

    Args:
        state: Current graph state with user_input.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with memory results.
    """
    user_input = state.get("user_input", "")
    conversation_id = state.get("conversation_id", "default")

    # Get the agent reference from config (avoids msgpack serialization issues)
    agent = get_agent_from_config(config)

    relevant_memories = []
    relevant_skills = []
    relevant_strategies = []

    if agent and hasattr(agent, "memory"):
        memory = agent.memory

        try:
            # Parallel retrieval from all memory types
            if hasattr(memory, "get_relevant_context"):
                context = await memory.get_relevant_context(user_input, top_k=5)

                # Episodic memories
                for ep in context.get("episodic", []):
                    source = "past experience"
                    distance = ep.get("distance")
                    relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""
                    relevant_memories.append({
                        "type": "episodic",
                        "content": ep.get("content", "")[:500],
                        "source": source,
                        "relevance": relevance,
                        "outcome": ep.get("outcome", "unknown"),
                    })

                # Semantic facts
                for fact in context.get("semantic", []):
                    key = fact.get("key", "")
                    distance = fact.get("distance")
                    relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""
                    relevant_memories.append({
                        "type": "semantic",
                        "content": fact.get("content", "")[:500],
                        "source": f"fact: {key}" if key else "knowledge",
                        "relevance": relevance,
                    })

                # Strategic memories
                relevant_strategies = context.get("strategic", [])

        except Exception as e:
            logger.warning(f"LTM context retrieval failed: {e}")

        # Procedural memory (skills with outcome data)
        try:
            if hasattr(memory, "procedural") and memory.procedural._skills_manager:
                agent_slot = getattr(agent, "agent_slot", "main")
                skills = await memory.procedural.search(
                    user_input, top_k=3, agent_slot=agent_slot
                )
                relevant_skills = skills
        except Exception as e:
            logger.warning(f"Procedural memory search failed: {e}")

        # Also search legacy conversation memory for cross-session context
        try:
            conv_memories = await memory.search(
                query=user_input,
                top_k=5,
                conversation_id=None,  # Search across ALL conversations
            )
            for mem in conv_memories:
                meta = mem.get("metadata", {})
                mem_conv = meta.get("conversation_id", "")
                mem_type = meta.get("type", "")
                # Only include from OTHER conversations or context compression summaries
                if mem_conv != conversation_id or mem_type == "context_compression":
                    source = f"session {mem_conv[:8]}" if mem_conv else "unknown"
                    if mem_type == "context_compression":
                        source = f"compressed context ({source})"
                    distance = mem.get("distance")
                    relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""
                    relevant_memories.append({
                        "type": "conversation",
                        "content": mem.get("content", "")[:500],
                        "source": source,
                        "relevance": relevance,
                    })
        except Exception as e:
            logger.warning(f"Conversation memory search failed: {e}")

    return {
        "relevant_memories": relevant_memories,
        "relevant_skills": relevant_skills,
        "relevant_strategies": relevant_strategies,
    }