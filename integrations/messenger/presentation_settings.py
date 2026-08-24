"""Read/write ``tools_presentation`` for messenger UIs."""

from __future__ import annotations

from typing import Any

from core.tools.code_mode.policy import normalize_presentation


def presentation_for_host(host: Any) -> str:
    agent = getattr(host, "agent", None)
    if agent is not None:
        tools = getattr(agent, "tools", None)
        if tools is not None and hasattr(tools, "presentation_for_slot"):
            return tools.presentation_for_slot("main")
        cfg = getattr(agent, "config", None)
        if cfg is not None:
            return normalize_presentation(getattr(cfg, "tools_presentation", None))
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return "native"
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(profile)
        return normalize_presentation(getattr(cfg, "tools_presentation", None))
    except Exception:
        return "native"


def slot_presentation_for_host(host: Any, slot: str) -> str:
    key = (slot or "main").strip().lower() or "main"
    agent = getattr(host, "agent", None)
    if agent is not None:
        tools = getattr(agent, "tools", None)
        if tools is not None and hasattr(tools, "presentation_for_slot"):
            return tools.presentation_for_slot(key)
        cfg = getattr(agent, "config", None)
        by_slot = getattr(cfg, "tools_presentation_by_slot", None) or {}
        if key in by_slot:
            return normalize_presentation(by_slot.get(key))
    profile = str(getattr(host, "profile", None) or "").strip()
    if profile:
        try:
            from cli.core import get_profile_manager

            cfg = get_profile_manager().load_profile(profile)
            by_slot = getattr(cfg, "tools_presentation_by_slot", None) or {}
            if key in by_slot:
                return normalize_presentation(by_slot.get(key))
            return normalize_presentation(getattr(cfg, "tools_presentation", None))
        except Exception:
            pass
    return "native"


def set_presentation_for_host(host: Any, value: str, *, slot: str | None = None) -> str:
    """Persist presentation on the profile and a live agent/tools registry."""
    mode = normalize_presentation(value)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update tools_presentation")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    key = (slot or "").strip().lower()
    if key and key not in ("main", "default"):
        by_slot = dict(getattr(cfg, "tools_presentation_by_slot", None) or {})
        by_slot[key] = mode
        cfg.tools_presentation_by_slot = by_slot
    else:
        cfg.tools_presentation = mode
    manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        if key and key not in ("main", "default"):
            by_slot = dict(getattr(agent.config, "tools_presentation_by_slot", None) or {})
            by_slot[key] = mode
            agent.config = agent.config.with_overrides(tools_presentation_by_slot=by_slot)
            tools = getattr(agent, "tools", None)
            if tools is not None:
                mapping = dict(getattr(tools, "_tools_presentation_by_slot", None) or {})
                mapping[key] = mode
                tools._tools_presentation_by_slot = mapping
        else:
            agent.config = agent.config.with_overrides(tools_presentation=mode)
            tools = getattr(agent, "tools", None)
            if tools is not None:
                tools._tools_presentation = mode
    return mode


def clear_slot_presentation_for_host(host: Any, slot: str) -> None:
    """Drop a per-type tools_presentation override so the type inherits the profile."""
    key = (slot or "").strip().lower()
    if not key or key in ("main", "default"):
        return
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return
    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    by_slot = dict(getattr(cfg, "tools_presentation_by_slot", None) or {})
    if key in by_slot:
        del by_slot[key]
        cfg.tools_presentation_by_slot = by_slot
        manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        live = dict(getattr(agent.config, "tools_presentation_by_slot", None) or {})
        if key in live:
            del live[key]
            agent.config = agent.config.with_overrides(tools_presentation_by_slot=live)
        tools = getattr(agent, "tools", None)
        if tools is not None:
            mapping = dict(getattr(tools, "_tools_presentation_by_slot", None) or {})
            mapping.pop(key, None)
            tools._tools_presentation_by_slot = mapping
