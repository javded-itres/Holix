"""Dishka providers for Holix dependency injection."""

from dishka import Provider, Scope, from_context, provide
from openai import AsyncOpenAI

from core.agent_events import AgentEventBus
from core.di.runtime_config import HolixRuntimeConfig
from core.models.client_factory import create_openai_client


class ConfigProvider(Provider):
    """Provides HolixRuntimeConfig (APP scope, overridable via context)."""

    scope = Scope.APP
    config = from_context(HolixRuntimeConfig)

    @provide(scope=Scope.APP)
    def default_config(self) -> HolixRuntimeConfig:
        return HolixRuntimeConfig.from_settings()


class InfrastructureProvider(Provider):
    """LLM client and shared infrastructure."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def llm_client(self, config: HolixRuntimeConfig) -> AsyncOpenAI:
        return create_openai_client(
            base_url=config.base_url,
            api_key=config.api_key,
            metadata=config.provider_metadata or None,
        )


class AgentDepsProvider(Provider):
    """Agent dependencies (event bus)."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def event_bus(self) -> AgentEventBus:
        return AgentEventBus(name="Holix")


def get_all_providers() -> list[Provider]:
    from core.di.factories import create_holix_agent

    agent_factory_provider = Provider(scope=Scope.APP)
    agent_factory_provider.provide(create_holix_agent)
    return [
        ConfigProvider(),
        InfrastructureProvider(),
        AgentDepsProvider(),
        agent_factory_provider,
    ]