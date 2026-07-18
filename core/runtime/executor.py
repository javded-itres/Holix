"""Single entry point for agent execution (LangGraph or legacy loop)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

from core.agent_events import AgentEvent


async def run_holix(
    agent: Any,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
    execution_mode: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Run the agent and yield AgentEvent objects.

    Dispatches to LangGraph or the legacy loop based on ``agent._use_langgraph``.
    """
    cfg = getattr(agent, "config", None)
    mode = execution_mode or (cfg.execution_mode if cfg else "react")
    use_graph = getattr(agent, "_use_langgraph", True)

    from core.application.run_scope import enter_run_scope, run_context_from_agent

    begin = getattr(agent, "begin_run", None)
    end = getattr(agent, "end_run", None)
    stamp = getattr(agent, "stamp_event", None)
    run_ctx = run_context_from_agent(agent, conversation_id)
    container = getattr(agent, "_di_container", None)

    if begin:
        begin(conversation_id)
    try:
        async with enter_run_scope(agent, run_ctx, container=container):
            if use_graph:
                from core.graph.builder import run_graph_loop

                async with aclosing(
                    run_graph_loop(
                        agent,
                        user_input,
                        conversation_id,
                        stream=stream,
                        execution_mode=mode,
                    )
                ) as events:
                    async for event in events:
                        if stamp:
                            stamp(event)
                        yield event
            else:
                from core.agent_execution import run_agent_loop

                async with aclosing(
                    run_agent_loop(
                        agent,
                        user_input,
                        conversation_id,
                        stream=stream,
                    )
                ) as events:
                    async for event in events:
                        if stamp:
                            stamp(event)
                        yield event
    except asyncio.CancelledError:
        raise
    finally:
        if end:
            end()