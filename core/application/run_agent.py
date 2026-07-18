"""Application use-cases for running / streaming the agent."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from core.agent_events import AgentEvent
from core.domain.run_context import RunContext
from core.runtime.executor import run_holix


async def run_agent(
    agent: Any,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
    execution_mode: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one user turn and yield agent events (presentation-agnostic)."""
    async for event in run_holix(
        agent,
        user_input,
        conversation_id,
        stream=stream,
        execution_mode=execution_mode,
    ):
        yield event


async def collect_agent_response(
    agent: Any,
    user_input: str,
    conversation_id: str = "default",
    *,
    execution_mode: str | None = None,
) -> str:
    """Run agent and return final assistant text (CLI / simple API)."""
    from core.agent_events import FinalResponseEvent

    final = ""
    async for event in run_agent(
        agent,
        user_input,
        conversation_id,
        stream=False,
        execution_mode=execution_mode,
    ):
        if isinstance(event, FinalResponseEvent):
            final = event.content or final
        elif hasattr(event, "content") and getattr(event, "type", None) == "final_response":
            final = getattr(event, "content", "") or final
    return final


def build_run_context(agent: Any, conversation_id: str) -> RunContext:
    from core.application.run_scope import run_context_from_agent

    return run_context_from_agent(agent, conversation_id)
