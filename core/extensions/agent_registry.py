"""Discover and register ``holix.agent.extensions`` entry points."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from core.extensions.agent_base import AgentExtension, SlashCommandSpec
from core.extensions.manifest import load_manifest_from_module, merge_manifest_into_extension
from core.extensions.permissions import PERMISSION_TOOLS, enforce_permissions
from core.extensions.registry import _entry_points_for_group

logger = logging.getLogger(__name__)

ENTRYPOINT_GROUP = "holix.agent.extensions"

_agent_slash_commands: list[SlashCommandSpec] = []
_agent_prompt_fragments: dict[str, list[str]] = {}


def agent_slash_commands() -> tuple[SlashCommandSpec, ...]:
    return tuple(_agent_slash_commands)


def agent_prompt_fragment(profile: str) -> str | None:
    parts = _agent_prompt_fragments.get(profile) or _agent_prompt_fragments.get("*") or []
    if not parts:
        return None
    return "\n".join(parts)


@lru_cache
def discover_agent_extensions() -> tuple[AgentExtension, ...]:
    loaded: list[AgentExtension] = []
    for ep in sorted(_entry_points_for_group(ENTRYPOINT_GROUP), key=lambda e: e.name):
        try:
            obj = ep.load()
            if isinstance(obj, type):
                ext = obj()
            elif callable(obj):
                ext = obj()
            else:
                ext = obj
            if not isinstance(ext, AgentExtension):
                logger.warning("agent extension %s does not implement AgentExtension", ep.name)
                continue
            module = getattr(ep, "module", None) or str(ep.value).split(":", 1)[0]
            manifest = load_manifest_from_module(module)
            merge_manifest_into_extension(ext, manifest)
            if not getattr(ext, "name", ""):
                ext.name = ep.name
            loaded.append(ext)
        except Exception:
            logger.exception("failed to load agent extension %s", ep.name)
    return tuple(loaded)


def register_agent_extensions(agent: Any) -> list[str]:
    """Register tools and slash commands from agent extensions onto a HolixAgent."""
    global _agent_slash_commands, _agent_prompt_fragments

    profile = getattr(getattr(agent, "config", None), "profile_name", "default") or "default"
    names: list[str] = []

    for ext in discover_agent_extensions():
        if not enforce_permissions(ext, frozenset({PERMISSION_TOOLS}), context="agent tools"):
            continue
        try:
            ext.register_tools(agent.tools, agent)
            slash_buf: list[SlashCommandSpec] = []
            ext.register_slash_commands(slash_buf)
            _agent_slash_commands.extend(slash_buf)
            fragment = ext.augment_system_prompt(profile)
            if fragment:
                _agent_prompt_fragments.setdefault(profile, []).append(fragment.strip())
            names.append(ext.name)
            logger.debug("registered agent extension %s for profile %s", ext.name, profile)
        except Exception:
            logger.exception("agent extension %s registration failed", ext.name)
    return names


def clear_agent_extension_cache() -> None:
    """Reset cached slash/prompt state (tests)."""
    global _agent_slash_commands, _agent_prompt_fragments
    _agent_slash_commands = []
    _agent_prompt_fragments = {}
    if hasattr(discover_agent_extensions, "cache_clear"):
        discover_agent_extensions.cache_clear()