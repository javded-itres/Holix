"""Dishka container factory and agent lifecycle helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import AsyncContainer, make_async_container

from core.agent_events import EventHandler
from core.di.providers import get_all_providers
from core.di.runtime_config import HolixRuntimeConfig

if TYPE_CHECKING:
    from cli.core import ProfileConfig


def create_async_container(
    config: HolixRuntimeConfig | None = None,
) -> AsyncContainer:
    """Create the application async DI container.

    Args:
        config: Optional runtime config injected into APP scope context.
            When omitted, uses :meth:`HolixRuntimeConfig.from_settings`.
    """
    resolved = config or HolixRuntimeConfig.from_settings()
    return make_async_container(
        *get_all_providers(),
        context={HolixRuntimeConfig: resolved},
    )


def resolve_gateway_runtime_config() -> HolixRuntimeConfig:
    """Runtime config for API gateway (HOLIX_PROFILE or default)."""
    import os

    from cli.core import init_profile

    from core.env_loader import bootstrap_profile_env

    profile = os.getenv("HOLIX_PROFILE", "default")
    bootstrap_profile_env(profile)
    return resolve_runtime_config(init_profile(profile))


def resolve_runtime_config(profile: ProfileConfig | None = None) -> HolixRuntimeConfig:
    """Build runtime config from env settings and optional CLI profile."""
    if profile is None:
        return HolixRuntimeConfig.from_settings()

    base = HolixRuntimeConfig.from_profile(profile)

    try:
        from core.models.manager import ModelManager

        model_manager = ModelManager(profile)
        model_config = model_manager.get_default_model_config()
        if model_config:
            return base.with_overrides(
                model=model_config.model,
                base_url=model_config.base_url,
                api_key=model_config.api_key,
                temperature=model_config.temperature,
            )
    except Exception:
        pass

    return base


async def create_agent(
    config: HolixRuntimeConfig,
    *,
    event_listeners: list[EventHandler] | None = None,
    enable_monitoring: bool = True,
    container: AsyncContainer | None = None,
):
    """Create and initialize a HolixAgent using Dishka.

    Returns:
        (agent, container) — caller should ``await container.close()`` when done.
    """
    from core.agent import HolixAgent

    owns_container = container is None
    if owns_container:
        container = create_async_container(config)

    agent = await container.get(HolixAgent)

    if event_listeners:
        for listener in event_listeners:
            agent.events.subscribe(listener)

    if not agent._initialized:
        await agent.initialize()

    return agent, container


async def get_agent_from_container(container: AsyncContainer):
    """Get agent from container, initializing if needed."""
    from core.agent import HolixAgent

    agent = await container.get(HolixAgent)
    if not agent._initialized:
        await agent.initialize()
    return agent