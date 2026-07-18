"""Narrow runtime surface exposed to LangGraph nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from core.agent_events import AgentEventBus
    from core.context import ContextManager
    from core.memory.facade import MemoryFacade
    from core.skills.manager import SkillsManager
    from core.tools.registry import ToolRegistry


@dataclass(slots=True)
class GraphRuntime:
    """Dependencies graph nodes need — without full HolixAgent surface."""

    client: AsyncOpenAI
    model: str
    config: Any
    memory: MemoryFacade
    tools: ToolRegistry
    skills: SkillsManager
    context_manager: ContextManager
    events: AgentEventBus
    agent: Any | None = None

    @classmethod
    def from_agent(cls, agent: Any) -> GraphRuntime:
        return cls(
            client=agent.client,
            model=agent.model,
            config=agent.config,
            memory=agent.memory,
            tools=agent.tools,
            skills=agent.skills,
            context_manager=agent.context_manager,
            events=agent.events,
            agent=agent,
        )