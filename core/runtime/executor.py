"""Single entry point for agent execution (LangGraph or legacy loop)."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from core.agent_events import AgentEvent


async def run_helix(
    agent: Any,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
    execution_mode: Optional[str] = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Run the agent and yield AgentEvent objects.

    Dispatches to LangGraph or the legacy loop based on ``agent._use_langgraph``.
    """
    cfg = getattr(agent, "config", None)
    mode = execution_mode or (cfg.execution_mode if cfg else "react")
    use_graph = getattr(agent, "_use_langgraph", True)

    begin = getattr(agent, "begin_run", None)
    end = getattr(agent, "end_run", None)
    stamp = getattr(agent, "stamp_event", None)
    if begin:
        begin(conversation_id)
    try:
        if use_graph:
            from core.graph.builder import run_graph_loop

            async for event in run_graph_loop(
                agent,
                user_input,
                conversation_id,
                stream=stream,
                execution_mode=mode,
            ):
                if stamp:
                    stamp(event)
                yield event
        else:
            from core.agent_execution import run_agent_loop

            async for event in run_agent_loop(
                agent,
                user_input,
                conversation_id,
                stream=stream,
            ):
                if stamp:
                    stamp(event)
                yield event
    finally:
        if end:
            end()