"""Map Claude Code .mcp.json entries to Helix MCP server config."""

from __future__ import annotations

from typing import Any

from core.config_utils import resolve_env_refs


def parse_claude_mcp_json(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return Helix-style mcp_servers dict from Claude plugin .mcp.json."""
    out: dict[str, dict[str, Any]] = {}
    for name, spec in data.items():
        if not isinstance(spec, dict):
            continue
        converted = _convert_server(name, spec)
        if converted:
            out[name] = resolve_env_refs(converted)
    return out


def _convert_server(name: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    stype = (spec.get("type") or "stdio").lower()
    if stype in ("http", "sse", "streamable-http"):
        url = spec.get("url")
        if not url:
            return None
        cfg: dict[str, Any] = {
            "transport": "sse",
            "url": url,
            "timeout": 60.0,
            "default_risk_level": "medium",
        }
        headers = spec.get("headers")
        if headers:
            cfg["env"] = {f"MCP_HEADER_{k}": str(v) for k, v in headers.items()}
        return cfg

    if stype == "stdio" or spec.get("command"):
        command = spec.get("command")
        if not command:
            return None
        return {
            "transport": "stdio",
            "command": command,
            "args": spec.get("args") or [],
            "env": spec.get("env") or {},
            "timeout": 30.0,
            "default_risk_level": "medium",
        }

    return None


def merge_into_profile_servers(
    existing: dict[str, dict[str, Any]],
    plugin_name: str,
    servers: dict[str, dict[str, Any]],
    *,
    prefix: str = "claude",
) -> dict[str, dict[str, Any]]:
    merged = dict(existing)
    for key, cfg in servers.items():
        helix_name = f"{prefix}-{plugin_name}-{key}" if key != plugin_name else f"{prefix}-{plugin_name}"
        helix_name = helix_name.replace("__", "-")[:64]
        merged[helix_name] = cfg
    return merged