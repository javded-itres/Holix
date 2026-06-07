"""Dishka providers for Helix dependency injection."""

from dishka import Provider, Scope, from_context, provide
from openai import AsyncOpenAI

from core.agent_events import AgentEventBus
from core.di.factories import create_helix_agent
from core.di.runtime_config import HelixRuntimeConfig


class ConfigProvider(Provider):
    """Provides HelixRuntimeConfig (APP scope, overridable via context)."""

    scope = Scope.APP
    config = from_context(HelixRuntimeConfig)

    @provide(scope=Scope.APP)
    def default_config(self) -> HelixRuntimeConfig:
        return HelixRuntimeConfig.from_settings()


class InfrastructureProvider(Provider):
    """LLM client and shared infrastructure."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def llm_client(self, config: HelixRuntimeConfig) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)


class AgentDepsProvider(Provider):
    """Agent dependencies (event bus)."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def event_bus(self) -> AgentEventBus:
        return AgentEventBus(name="HelixAgentAi")


# Standalone provider for agent factory (avoid binding `self` on class methods)
AgentFactoryProvider = Provider(scope=Scope.APP)
AgentFactoryProvider.provide(create_helix_agent)


def get_all_providers() -> list[Provider]:
    return [
        ConfigProvider(),
        InfrastructureProvider(),
        AgentDepsProvider(),
        AgentFactoryProvider,
    ]