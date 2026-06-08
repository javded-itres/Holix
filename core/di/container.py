"""Dishka container factory and agent lifecycle helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dishka import AsyncContainer, make_async_container

from core.agent_events import EventHandler
from core.di.providers import get_all_providers
from core.di.runtime_config import HelixRuntimeConfig

if TYPE_CHECKING:
    from cli.core import ProfileConfig


def create_async_container(
    config: Optional[HelixRuntimeConfig] = None,
) -> AsyncContainer:
    """Create the application async DI container.

    Args:
        config: Optional runtime config injected into APP scope context.
            When omitted, uses :meth:`HelixRuntimeConfig.from_settings`.
    """
    resolved = config or HelixRuntimeConfig.from_settings()
    return make_async_container(
        *get_all_providers(),
        context={HelixRuntimeConfig: resolved},
    )


def resolve_gateway_runtime_config() -> HelixRuntimeConfig:
    """Runtime config for API gateway (HELIX_PROFILE or default)."""
    import os

    from cli.core import init_profile
    from core.env_loader import bootstrap_profile_env

    profile = os.getenv("HELIX_PROFILE", "default")
    bootstrap_profile_env(profile)
    return resolve_runtime_config(init_profile(profile))


def resolve_runtime_config(profile: Optional[ProfileConfig] = None) -> HelixRuntimeConfig:
    """Build runtime config from env settings and optional CLI profile."""
    if profile is None:
        return HelixRuntimeConfig.from_settings()

    base = HelixRuntimeConfig.from_profile(profile)

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
    config: HelixRuntimeConfig,
    *,
    event_listeners: Optional[list[EventHandler]] = None,
    enable_monitoring: bool = True,
    container: Optional[AsyncContainer] = None,
):
    """Create and initialize a HelixAgent using Dishka.

    Returns:
        (agent, container) — caller should ``await container.close()`` when done.
    """
    from core.agent import HelixAgent

    owns_container = container is None
    if owns_container:
        container = create_async_container(config)

    agent = await container.get(HelixAgent)

    if event_listeners:
        for listener in event_listeners:
            agent.events.subscribe(listener)

    if not agent._initialized:
        await agent.initialize()

    return agent, container


async def get_agent_from_container(container: AsyncContainer):
    """Get agent from container, initializing if needed."""
    from core.agent import HelixAgent

    agent = await container.get(HelixAgent)
    if not agent._initialized:
        await agent.initialize()
    return agent