"""Read/write profile ``enable_subagents`` for messenger UIs."""

from __future__ import annotations

from typing import Any

_SUBAGENT_TOOL_NAMES = (
    "delegate_to_subagent",
    "wait_subagent_result",
    "list_subagents",
    "list_subagent_types",
    "terminate_subagent",
)


def is_subagents_enabled_for_host(host: Any) -> bool:
    """Current effective flag: live agent config, else profile, else default on."""
    from core.config_utils import is_subagents_enabled

    agent = getattr(host, "agent", None)
    if agent is not None:
        return is_subagents_enabled(getattr(agent, "config", None))

    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return True
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(profile)
        return is_subagents_enabled(cfg)
    except Exception:
        return True


def set_subagents_enabled_for_host(host: Any, enabled: bool) -> bool:
    """Persist ``enable_subagents`` on the host profile and update a live agent.

    Returns the effective flag after apply.
    """
    enabled = bool(enabled)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update enable_subagents")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.enable_subagents = enabled
    manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        agent.config = agent.config.with_overrides(enable_subagents=enabled)
        _sync_subagent_tools(agent, enabled)

    return enabled


def _sync_subagent_tools(agent: Any, enabled: bool) -> None:
    """Register or drop sub-agent tools so the next LLM turn matches the flag."""
    tools = getattr(agent, "tools", None)
    if tools is None:
        return

    if enabled:
        names = set(tools.get_tool_names()) if hasattr(tools, "get_tool_names") else set()
        if "delegate_to_subagent" not in names:
            from core.tools.subagents import register_subagent_tools

            register_subagent_tools(tools, agent)
        return

    if not hasattr(tools, "unregister"):
        return
    for name in _SUBAGENT_TOOL_NAMES:
        try:
            tools.unregister(name)
        except Exception:
            pass
