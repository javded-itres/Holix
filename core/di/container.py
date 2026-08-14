"""Dishka container factory and agent lifecycle helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import AsyncContainer, make_async_container

from core.agent_events import EventHandler
from core.di.providers import get_all_providers
from core.di.runtime_config import HolixRuntimeConfig

if TYPE_CHECKING:
    from core.profile import ProfileConfig


def create_async_container(
    config: HolixRuntimeConfig | None = None,
    *,
    gateway: bool = False,
) -> AsyncContainer:
    """Create the application async DI container.

    Args:
        config: Optional runtime config injected into APP scope context.
            When omitted, uses :meth:`HolixRuntimeConfig.from_settings`.
        gateway: Include gateway process services (registry, stores, auth).
    """
    resolved = config or HolixRuntimeConfig.from_settings()
    return make_async_container(
        *get_all_providers(gateway=gateway),
        context={HolixRuntimeConfig: resolved},
    )


def resolve_gateway_runtime_config() -> HolixRuntimeConfig:
    """Runtime config for API gateway (HOLIX_PROFILE or default).

    Falls back to env/settings when the named profile is not on disk yet
    (e.g. import during tests before profiles are created).
    """
    import os

    from core.env_loader import bootstrap_profile_env
    from core.profile import ProfileNotFoundError, init_profile
    from core.profile_keys import ProfileKeyError

    profile = (os.getenv("HOLIX_PROFILE") or "default").strip() or "default"
    try:
        bootstrap_profile_env(profile)
        return resolve_runtime_config(init_profile(profile, prompt_key=False))
    except (ProfileNotFoundError, ProfileKeyError, OSError, ValueError):
        return HolixRuntimeConfig.from_settings()


def resolve_runtime_config(profile: ProfileConfig | None = None) -> HolixRuntimeConfig:
    """Build runtime config from env settings and optional CLI profile."""
    from core.di.runtime_config import apply_unattended_policy

    if profile is None:
        return apply_unattended_policy(HolixRuntimeConfig.from_settings())

    base = HolixRuntimeConfig.from_profile(profile)

    try:
        from core.models.manager import ModelManager

        model_manager = ModelManager(profile)
        model_config = model_manager.get_default_model_config()
        if model_config:
            base = base.with_overrides(
                model=model_config.model,
                base_url=model_config.base_url,
                api_key=model_config.api_key,
                temperature=model_config.temperature,
            )
    except Exception:
        pass

    return apply_unattended_policy(base)


async def create_agent(
    config: HolixRuntimeConfig,
    *,
    event_listeners: list[EventHandler] | None = None,
    enable_monitoring: bool = True,
    container: AsyncContainer | None = None,
    mcp_ready_timeout: float = 10.0,
    defer_skill_index: bool = False,
):
    """Create and initialize a HolixAgent using Dishka.

    Returns:
        (agent, container) — caller should ``await agent.close()`` when done.
    """
    from core.agent import HolixAgent

    owns_container = container is None
    if owns_container:
        container = create_async_container(config)

    agent = await container.get(HolixAgent)
    agent._di_container = container

    if enable_monitoring:
        from core.agent_events import wire_default_monitoring

        wire_default_monitoring(agent.events)

    if event_listeners:
        for listener in event_listeners:
            agent.events.subscribe(listener)

    if not agent._initialized:
        await agent.initialize(
            mcp_ready_timeout=mcp_ready_timeout,
            defer_skill_index=defer_skill_index,
        )

    return agent, container


async def get_agent_from_container(container: AsyncContainer):
    """Get agent from container, initializing if needed."""
    from core.agent import HolixAgent

    agent = await container.get(HolixAgent)
    if not agent._initialized:
        await agent.initialize()
    return agent
