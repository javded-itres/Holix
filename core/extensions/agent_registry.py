"""Discover and register ``holix.agent.extensions`` + local folder extensions."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from core.extensions.agent_base import AgentExtension, SlashCommandSpec
from core.extensions.local_loader import (
    discover_local_agent_extensions,
    load_local_default_settings,
)
from core.extensions.manifest import load_manifest_from_module, merge_manifest_into_extension
from core.extensions.middleware import MiddlewareChain, get_or_create_chain, install_llm_middleware
from core.extensions.permissions import PERMISSION_TOOLS, enforce_permissions
from core.extensions.registry import _entry_points_for_group
from core.extensions.settings import (
    ensure_default_settings_file,
    load_extension_settings,
)

logger = logging.getLogger(__name__)

ENTRYPOINT_GROUP = "holix.agent.extensions"

# Permission for middleware registration (tools also accepted for BC)
PERMISSION_MIDDLEWARE = "middleware"

_agent_slash_commands: list[SlashCommandSpec] = []
_agent_prompt_fragments: dict[str, list[str]] = {}
_agent_extension_settings: dict[str, dict[str, Any]] = {}


def agent_slash_commands() -> tuple[SlashCommandSpec, ...]:
    return tuple(_agent_slash_commands)


def agent_prompt_fragment(profile: str) -> str | None:
    parts = _agent_prompt_fragments.get(profile) or _agent_prompt_fragments.get("*") or []
    if not parts:
        return None
    return "\n".join(parts)


def agent_extension_settings(profile: str | None = None) -> dict[str, dict[str, Any]]:
    """Return loaded settings keyed by extension name (last registered agent)."""
    return dict(_agent_extension_settings)


@lru_cache
def discover_entrypoint_agent_extensions() -> tuple[AgentExtension, ...]:
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
            if not isinstance(ext, AgentExtension) and not hasattr(ext, "register_tools"):
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


def discover_agent_extensions(profile: str | None = None) -> tuple[Any, ...]:
    """Entry-point packages + drop-in folders under Holix home / profile."""
    entry = list(discover_entrypoint_agent_extensions())
    local = list(discover_local_agent_extensions(profile))
    # Local folders override same-named entry points (easier dev iteration)
    by_name: dict[str, Any] = {}
    for ext in entry:
        by_name[str(getattr(ext, "name", "") or "")] = ext
    for ext in local:
        name = str(getattr(ext, "name", "") or "")
        by_name[name] = ext
    return tuple(v for k, v in by_name.items() if k)


def _extension_defaults(ext: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    if hasattr(ext, "default_settings") and callable(ext.default_settings):
        try:
            raw = ext.default_settings()
            if isinstance(raw, dict):
                defaults.update(raw)
        except Exception:
            logger.exception("extension %s default_settings failed", getattr(ext, "name", "?"))
    local_path = getattr(ext, "_holix_local_path", None)
    if local_path:
        from pathlib import Path

        folder_defaults = load_local_default_settings(Path(local_path))
        defaults = {**folder_defaults, **defaults}
    return defaults


def _apply_settings(ext: Any, profile: str) -> dict[str, Any]:
    name = str(getattr(ext, "name", "") or "unnamed")
    defaults = _extension_defaults(ext)
    ensure_default_settings_file(profile, name, defaults)
    settings = load_extension_settings(profile, name, defaults=defaults)
    if hasattr(ext, "on_settings_loaded") and callable(ext.on_settings_loaded):
        try:
            ext.on_settings_loaded(settings)
        except Exception:
            logger.exception("extension %s on_settings_loaded failed", name)
    else:
        try:
            ext.settings = settings
        except Exception:
            pass
    return settings


def _can_register_tools(ext: Any) -> bool:
    return enforce_permissions(ext, frozenset({PERMISSION_TOOLS}), context="agent tools")


def _can_register_middleware(ext: Any) -> bool:
    # Allow either explicit middleware permission or tools (common for agent ext)
    perms = getattr(ext, "permissions", None) or frozenset()
    if not perms:
        return True
    if PERMISSION_MIDDLEWARE in perms or PERMISSION_TOOLS in perms:
        return True
    return enforce_permissions(
        ext, frozenset({PERMISSION_MIDDLEWARE}), context="agent middleware"
    )


def _tool_names(agent: Any) -> set[str]:
    tools = getattr(agent, "tools", None)
    if tools is None:
        return set()
    if hasattr(tools, "get_tool_names"):
        try:
            return set(tools.get_tool_names())
        except Exception:
            pass
    raw = getattr(tools, "tools", None)
    if isinstance(raw, dict):
        return set(raw.keys())
    return set()


def _unregister_extension_tools(agent: Any) -> list[str]:
    """Remove tools previously registered by agent extensions (hot-reload)."""
    names = list(getattr(agent, "_extension_tool_names", None) or [])
    tools = getattr(agent, "tools", None)
    removed: list[str] = []
    if tools is None:
        return removed
    for name in names:
        try:
            if hasattr(tools, "unregister") and tools.unregister(name):
                removed.append(name)
            elif hasattr(tools, "tools") and isinstance(tools.tools, dict):
                if name in tools.tools:
                    del tools.tools[name]
                    removed.append(name)
        except Exception:
            logger.debug("failed to unregister extension tool %s", name, exc_info=True)
    try:
        agent._extension_tool_names = set()
    except Exception:
        pass
    return removed


def register_agent_extensions(agent: Any) -> list[str]:
    """Register tools, slash commands, settings, and LLM middleware."""
    global _agent_slash_commands, _agent_prompt_fragments, _agent_extension_settings

    profile = getattr(getattr(agent, "config", None), "profile_name", "default") or "default"
    names: list[str] = []
    settings_map: dict[str, dict[str, Any]] = {}
    extension_tool_names: set[str] = set()

    # Reset contributions for this agent init (local folders re-scanned every time)
    _agent_slash_commands = []
    _agent_prompt_fragments = {}

    chain = get_or_create_chain(agent)
    chain.clear()

    from core.extensions.control import (
        all_agent_extensions_off,
        is_extension_blocked,
        quarantine_extension,
    )

    if all_agent_extensions_off():
        logger.warning(
            "all agent extensions skipped (HOLIX_AGENT_EXTENSIONS_OFF=1) profile=%s",
            profile,
        )
        _agent_extension_settings = settings_map
        try:
            agent.extension_settings = settings_map
            agent._extension_tool_names = set()
            agent._agent_extension_names = []
        except Exception:
            pass
        return names

    for ext in discover_agent_extensions(profile):
        name = str(getattr(ext, "name", "") or type(ext).__name__)
        blocked, block_reason = is_extension_blocked(profile, name)
        if blocked:
            logger.info(
                "agent extension %s skipped (%s)",
                name,
                block_reason or "blocked",
            )
            settings_map[name] = {
                "enabled": False,
                "blocked": True,
                "block_reason": block_reason,
            }
            continue
        try:
            settings = _apply_settings(ext, profile)
            settings_map[name] = settings

            # disabled via settings
            if settings.get("enabled") is False:
                logger.info("agent extension %s disabled via settings", name)
                continue

            if _can_register_tools(ext):
                before_tools = _tool_names(agent)
                ext.register_tools(agent.tools, agent)
                extension_tool_names.update(_tool_names(agent) - before_tools)
                slash_buf: list[SlashCommandSpec] = []
                if hasattr(ext, "register_slash_commands"):
                    ext.register_slash_commands(slash_buf)
                _agent_slash_commands.extend(slash_buf)
                if hasattr(ext, "augment_system_prompt"):
                    fragment = ext.augment_system_prompt(profile)
                    if fragment:
                        _agent_prompt_fragments.setdefault(profile, []).append(fragment.strip())

            if _can_register_middleware(ext) and hasattr(ext, "register_middleware"):
                try:
                    ext.register_middleware(chain, agent)
                except Exception as mw_exc:
                    logger.exception("extension %s register_middleware failed", name)
                    quarantine_extension(
                        profile,
                        name,
                        f"register_middleware: {type(mw_exc).__name__}: {mw_exc}",
                    )
                    continue

            names.append(name)
            logger.debug("registered agent extension %s for profile %s", name, profile)
        except Exception as exc:
            logger.exception("agent extension %s registration failed", name)
            try:
                quarantine_extension(
                    profile,
                    name,
                    f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass

    _agent_extension_settings = settings_map
    try:
        agent.extension_settings = settings_map
        agent._extension_tool_names = extension_tool_names
        agent._agent_extension_names = list(names)
    except Exception:
        pass

    # Install / refresh LLM proxy after all middleware registered
    client = getattr(agent, "client", None)
    if client is not None:
        install_llm_middleware(client, chain, agent)
        if len(chain) > 0:
            logger.info(
                "LLM middleware active for profile %s: %s",
                profile,
                ", ".join(chain.names()) or "(none)",
            )

    return names


def reload_agent_extensions(agent: Any) -> dict[str, Any]:
    """Hot-reload drop-in agent extensions without restarting the process.

    Unregisters tools from previously loaded extensions, re-imports local
    modules, and re-runs registration. Safe for local single-operator use
    after ``manage_agent_extensions(create=…)``.
    """
    removed = _unregister_extension_tools(agent)
    purged = 0
    try:
        from core.extensions.local_loader import purge_local_agent_extension_modules

        purged = purge_local_agent_extension_modules()
    except Exception:
        logger.debug("purge_local_agent_extension_modules failed", exc_info=True)

    clear_agent_extension_cache()
    loaded = register_agent_extensions(agent)
    logger.info(
        "agent extensions hot-reloaded: loaded=%s removed_tools=%s purged_modules=%s",
        loaded,
        removed,
        purged,
    )
    return {
        "ok": True,
        "loaded": loaded,
        "removed_tools": removed,
        "purged_modules": purged,
        "slash_commands": [
            {"command": s.command, "description": s.description}
            for s in agent_slash_commands()
        ],
    }


def clear_agent_extension_cache() -> None:
    """Reset cached slash/prompt/settings state (tests / reload)."""
    global _agent_slash_commands, _agent_prompt_fragments, _agent_extension_settings
    _agent_slash_commands = []
    _agent_prompt_fragments = {}
    _agent_extension_settings = {}
    if hasattr(discover_entrypoint_agent_extensions, "cache_clear"):
        discover_entrypoint_agent_extensions.cache_clear()
