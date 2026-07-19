"""Dishka provider registry."""

from dishka import Provider, Scope

from core.di.providers.agent_services import AgentServicesProvider
from core.di.providers.config import ConfigProvider
from core.di.providers.infrastructure import InfrastructureProvider
from core.di.providers.run import RunContextProvider


def get_all_providers(*, gateway: bool = False) -> list[Provider]:
    from core.di.factories import create_holix_agent

    agent_factory_provider = Provider(scope=Scope.APP)
    agent_factory_provider.provide(create_holix_agent)
    providers: list[Provider] = [
        ConfigProvider(),
        InfrastructureProvider(),
        AgentServicesProvider(),
        RunContextProvider(),
        agent_factory_provider,
    ]
    if gateway:
        from core.di.providers.gateway import GatewayServicesProvider

        providers.append(GatewayServicesProvider())
    return providers


__all__ = ["get_all_providers"]
