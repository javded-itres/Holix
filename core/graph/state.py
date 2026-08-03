"""
Holix Graph State — defines the state schema for the LangGraph execution graph.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict


class HolixGraphState(TypedDict, total=False):
    """State schema for the Holix LangGraph execution graph.

    This state flows through all graph nodes and accumulates
    partial updates at each step.

    IMPORTANT: The HolixAgent instance is NOT stored in state because
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
    base_max_steps: int                  # Original max_steps before auto-extensions
    step_budget_extensions: int          # How many times max_steps was auto-extended
    max_steps_per_plan_step: int         # Max ReAct iterations per plan step
    execution_mode: str                  # "react" | "plan_and_execute" | "hybrid"
    is_final: bool                       # True when final response generated
    final_response: str                  # The final answer

    # Streaming support
    stream: bool                         # Whether to use LLM streaming

    # Meta-agent state (Phase 4)
    meta_decision: dict[str, Any] | None  # Strategy adjustments from meta-agent
    needs_refinement: bool               # Set by meta-agent for self-refinement

    # Self-refinement / Reflexion state
    refinement_iterations: int
    max_refinement_iterations: int
    reflection_count: int                    # Reflexion retries this turn
    reflection_log: list[dict[str, Any]]     # Verbal reflections + quality scores

    # Sub-agent state (Phase 4b)
    sub_agent_tasks: list[dict[str, Any]]    # Sub-tasks for sub-agents
    sub_agent_results: dict[str, Any]        # {agent_name: result}
    pending_subagent: str | None          # Legacy single job id (use pending_subagents)
    pending_subagents: list[str]          # Active wave job ids
    subagent_orchestration: dict[str, Any] | None  # Serialized OrchestrationPlan
    current_subagent_wave: int            # Next wave index to run
    subagent_wave_results: dict[str, Any]  # {wave_id: {job_id: result}}
    subagent_task_meta: dict[str, Any]     # {job_id: task metadata}
    subagent_wave_step_indices: list[int] | None  # Plan indices finished in last wave
    subagent_awaiting_synthesis: bool     # True after collect, before react synthesis
    subagent_delegate_next: bool           # Router hint to spawn the next wave

    # Graph-native supervisor (post-wave rework cycle)
    supervisor_needs_rework: bool          # Router: supervisor → delegate again
    supervisor_rework_tasks: list[dict[str, Any]]  # Tasks with guidance for same types
    supervisor_rework_round: int           # How many graph rework rounds this turn
    supervisor_log: list[dict[str, Any]]   # Audit trail of interventions
    supervisor_last_diagnosis: dict[str, Any] | None

    # Plan state (for plan_and_execute and hybrid modes)
    plan_steps: list[dict[str, Any]]         # Ordered list of plan steps
    current_plan_step: int                    # Index of current step
    # Stable id for .holix/plans filenames (must be a graph channel or it is dropped).
    plan_id: str

    # Plan review state (for plan_and_execute and hybrid modes)
    plan_status: str                         # "pending_review" | "confirmed" | "auto_execute" | "refine" | "rejected"
    plan_review_id: str                       # Correlation ID for review request/response
    plan_refinement_feedback: str             # User feedback when refining the plan
    plan_clarification_rounds: int            # How many clarification Q&A rounds occurred

    # Plan orchestration state (step execution within plan_and_execute)
    is_step_complete: bool                   # True when current plan step is finished (react produced no tool_calls)
    current_step_start_count: int            # step_count at the start of current plan step (for per-step limit)

    # Action honesty: block "done" claims without successful tool evidence
    honesty_nudge_count: int                 # How many false-completion nudges this turn

    # Enriched plan data (from detailed plan_node)
    plan_analysis: dict[str, Any] | None  # Analysis: task_summary, complexity, clarifying_questions
    plan_architecture: dict[str, Any] | None  # Architecture: approach, tech_stack, structure, risks
    plan_report: dict[str, Any] | None  # BA-style development report for approval
    plan_reasoning: str  # LLM reasoning for plan ordering


def get_agent_from_config(config: RunnableConfig) -> Any:
    """Retrieve the HolixAgent instance from LangGraph RunnableConfig.

    The agent is passed via config["configurable"]["_agent"] to avoid
    msgpack serialization errors with checkpointers. This helper
    provides a safe, consistent way for all nodes to access it.

    Args:
        config: The RunnableConfig passed to graph nodes by LangGraph.

    Returns:
        The HolixAgent instance, or None if not available.
    """
    runtime = get_graph_runtime_from_config(config)
    if runtime is not None and runtime.agent is not None:
        return runtime.agent
    configurable = config.get("configurable", {})
    return configurable.get("_agent")


def get_graph_runtime_from_config(config: RunnableConfig):
    """Retrieve GraphRuntime from LangGraph RunnableConfig."""
    from core.domain.graph_runtime import GraphRuntime

    configurable = config.get("configurable", {})
    runtime = configurable.get("_runtime")
    if isinstance(runtime, GraphRuntime):
        return runtime
    agent = configurable.get("_agent")
    if agent is not None:
        return GraphRuntime.from_agent(agent)
    return None