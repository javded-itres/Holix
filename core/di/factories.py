"""Factory functions registered with Dishka (imports HolixAgent here to avoid cycles)."""

from openai import AsyncOpenAI

from core.agent import HolixAgent
from core.agent_events import AgentEventBus
from core.di.runtime_config import HolixRuntimeConfig


def create_holix_agent(
    config: HolixRuntimeConfig,
    llm_client: AsyncOpenAI,
    event_bus: AgentEventBus,
) -> HolixAgent:
    return HolixAgent(
        config=config,
        client=llm_client,
        event_bus=event_bus,
        enable_monitoring=True,
    )