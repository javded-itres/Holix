"""Dependency injection layer (Dishka)."""

from core.di.runtime_config import HolixRuntimeConfig

__all__ = [
    "HolixRuntimeConfig",
    "create_async_container",
    "create_agent",
    "get_agent_from_container",
    "resolve_runtime_config",
]


def __getattr__(name: str):
    """Lazy exports to avoid circular imports with core.agent."""
    if name in ("create_async_container", "create_agent", "get_agent_from_container", "resolve_runtime_config"):
        from core.di import container as c

        return getattr(c, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")