"""Resolve which MCP servers a slot may use, and fill missing popular configs."""

from __future__ import annotations

import os
from typing import Any


def assigned_mcp_names(assignments: dict[str, list[str]] | None) -> list[str]:
    """Unique server names mentioned in any agent-slot allow-list."""
    names: list[str] = []
    seen: set[str] = set()
    for lst in (assignments or {}).values():
        for raw in lst or []:
            name = str(raw or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def servers_for_slot(
    assignments: dict[str, list[str]] | None,
    slot: str,
    *,
    installed: list[str] | None = None,
) -> list[str] | None:
    """Allow-list for a slot.

    ``None`` → inherit all installed servers.
    ``[]`` → none.
    ``[...]`` → only those names.
    """
    assigns = assignments or {}
    key = (slot or "main").strip().lower() or "main"
    if key in assigns:
        return [str(s).strip() for s in (assigns.get(key) or []) if str(s).strip()]
    return None if installed is None else list(installed)


def mcp_tool_allowed(
    tool_name: str,
    *,
    slot: str,
    assignments: dict[str, list[str]] | None,
) -> bool:
    """True if ``mcp_<server>_…`` may be shown to ``slot``."""
    name = str(tool_name or "")
    if not name.startswith("mcp_"):
        return True
    allowed = servers_for_slot(assignments, slot)
    if allowed is None:
        return True
    return any(name.startswith(f"mcp_{srv}_") for srv in allowed)


def mcp_defs_for_names(
    servers: dict[str, Any] | None,
    names: list[str] | None,
) -> dict[str, Any]:
    """Installed + popular-catalog defs for the given server names only."""
    wanted = [str(n).strip() for n in (names or []) if str(n).strip()]
    if not wanted:
        return {}
    filled = fill_assigned_mcp_servers(servers, {"_": wanted})
    return {name: filled[name] for name in wanted if name in filled}


def mcp_server_incomplete(cfg: Any) -> bool:
    """True when a saved MCP entry cannot be launched (no command / URL)."""
    if not isinstance(cfg, dict) or not cfg:
        return True
    transport = str(cfg.get("transport") or "stdio").strip().lower()
    if transport in {"sse", "http", "streamable-http"}:
        return not str(cfg.get("url") or "").strip()
    return not str(cfg.get("command") or "").strip()


def _merge_env(popular_env: dict[str, Any], existing_env: dict[str, Any]) -> dict[str, Any]:
    env = dict(popular_env or {})
    for key, val in dict(existing_env or {}).items():
        if str(val or "").strip():
            env[key] = val
    for key, val in list(env.items()):
        if str(val or "").strip():
            continue
        from_env = os.environ.get(key, "")
        if from_env.strip():
            env[key] = from_env
    return env


def fill_assigned_mcp_servers(
    servers: dict[str, Any] | None,
    assignments: dict[str, list[str]] | None,
) -> dict[str, Any]:
    """Copy ``servers`` and add/complete popular-catalog configs for assigned names."""
    out: dict[str, Any] = dict(servers or {})
    to_fill = [
        name
        for name in assigned_mcp_names(assignments)
        if name not in out or mcp_server_incomplete(out.get(name))
    ]
    if not to_fill:
        return out
    try:
        from core.mcp.installer import build_config_from_popular
        from core.mcp.popular import get_popular_by_key
    except Exception:
        return out
    for name in to_fill:
        pop = get_popular_by_key(name)
        if pop is None:
            continue
        try:
            cfg = dict(build_config_from_popular(pop, {}) or {})
        except Exception:
            continue
        existing = out.get(name) if isinstance(out.get(name), dict) else {}
        env = _merge_env(dict(cfg.get("env") or {}), dict((existing or {}).get("env") or {}))
        if env:
            cfg["env"] = env
        if existing and existing.get("default_risk_level") not in (None, ""):
            cfg["default_risk_level"] = existing.get("default_risk_level")
        cfg.setdefault("_source", "popular")
        cfg["_auto_from_assignment"] = True
        out[name] = cfg
    return out
