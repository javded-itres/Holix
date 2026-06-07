"""Factory functions registered with Dishka (imports HelixAgent here to avoid cycles)."""

from openai import AsyncOpenAI

from core.agent import HelixAgent
from core.agent_events import AgentEventBus
from core.di.runtime_config import HelixRuntimeConfig


def create_helix_agent(
    config: HelixRuntimeConfig,
    llm_client: AsyncOpenAI,
    event_bus: AgentEventBus,
) -> HelixAgent:
    return HelixAgent(
        config=config,
        client=llm_client,
        event_bus=event_bus,
        enable_monitoring=True,
    )