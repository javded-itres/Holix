"""Track live agent instances by profile (replaces implicit global guards)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.agent import HolixAgent

_sessions: dict[str, HolixAgent] = {}


def register_agent_session(agent: HolixAgent) -> None:
    profile = (getattr(agent.config, "profile_name", None) or "default").strip() or "default"
    _sessions[profile] = agent


def unregister_agent_session(agent: HolixAgent) -> None:
    profile = (getattr(agent.config, "profile_name", None) or "default").strip() or "default"
    if _sessions.get(profile) is agent:
        _sessions.pop(profile, None)


def get_agent_session(profile_name: str | None = None) -> HolixAgent | None:
    key = (profile_name or "").strip() or "default"
    return _sessions.get(key)


def get_agent_attribute(profile_name: str | None, attr: str) -> Any | None:
    agent = get_agent_session(profile_name)
    if agent is None:
        return None
    return getattr(agent, attr, None)