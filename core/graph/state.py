"""
Helix Graph State — defines the state schema for the LangGraph execution graph.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict


class HelixGraphState(TypedDict, total=False):
    """State schema for the Helix LangGraph execution graph.

    This state flows through all graph nodes and accumulates
    partial updates at each step.

    IMPORTANT: The HelixAgent instance is NOT stored in state because
    it cannot be serialized by msgpack-based checkpointers. Instead, it
    is passed via config["configurable"]["_agent"] and accessed through
    the get_agent_from_config() helper.
    """

    # Core conversation state
    messages: list[dict[str, Any]]       # Full conversation history
    user_input: str                      # Latest user message
    conversation_id: str                 # Thread identifier
    system_prompt: str                   # Assembled system prompt

    # Tool execution state
    tool_calls: list[dict[str, Any]]     # Pending tool calls from LLM
    tool_results: list[dict[str, Any]]   # Completed tool call results

    # Memory state (populated by memory_retrieval_node)
    relevant_memories: list[dict[str, Any]]   # From LTM episodic + semantic
    relevant_skills: list[dict[str, Any]]     # From procedural memory
    relevant_strategies: list[dict[str, Any]]  # From strategic memory

    # Execution control
    step_count: int
    max_steps: int
    max_steps_per_plan_step: int         # Max ReAct iterations per plan step
    execution_mode: str                  # "react" | "plan_and_execute" | "hybrid"
    is_final: bool                       # True when final response generated
    final_response: str                  # The final answer

    # Streaming support
    stream: bool                         # Whether to use LLM streaming

    # Meta-agent state (Phase 4)
    meta_decision: dict[str, Any] | None  # Strategy adjustments from meta-agent
    needs_refinement: bool               # Set by meta-agent for self-refinement

    # Self-refinement state (Phase 5)
    refinement_iterations: int
    max_refinement_iterations: int

    # Sub-agent state (Phase 4b)
    sub_agent_tasks: list[dict[str, Any]]    # Sub-tasks for sub-agents
    sub_agent_results: dict[str, Any]        # {agent_name: result}
    pending_subagent: str | None          # Job id awaiting collect_subagent_node

    # Plan state (for plan_and_execute and hybrid modes)
    plan_steps: list[dict[str, Any]]         # Ordered list of plan steps
    current_plan_step: int                    # Index of current step

    # Plan review state (for plan_and_execute and hybrid modes)
    plan_status: str                         # "pending_review" | "confirmed" | "auto_execute" | "refine" | "rejected"
    plan_review_id: str                       # Correlation ID for review request/response
    plan_refinement_feedback: str             # User feedback when refining the plan

    # Plan orchestration state (step execution within plan_and_execute)
    is_step_complete: bool                   # True when current plan step is finished (react produced no tool_calls)
    current_step_start_count: int            # step_count at the start of current plan step (for per-step limit)

    # Enriched plan data (from detailed plan_node)
    plan_analysis: dict[str, Any] | None  # Analysis: task_summary, complexity, clarifying_questions
    plan_architecture: dict[str, Any] | None  # Architecture: approach, tech_stack, structure, risks


def get_agent_from_config(config: RunnableConfig) -> Any:
    """Retrieve the HelixAgent instance from LangGraph RunnableConfig.

    The agent is passed via config["configurable"]["_agent"] to avoid
    msgpack serialization errors with checkpointers. This helper
    provides a safe, consistent way for all nodes to access it.

    Args:
        config: The RunnableConfig passed to graph nodes by LangGraph.

    Returns:
        The HelixAgent instance, or None if not available.
    """
    configurable = config.get("configurable", {})
    return configurable.get("_agent")