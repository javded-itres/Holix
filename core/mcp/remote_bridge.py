"""Speak to a remote HTTP MCP server from Holix's stdio client.

``mcp-remote`` is the stdio process. It talks Streamable HTTP first and falls
back to SSE. Header values stay in the child environment, not in argv.
"""

from __future__ import annotations

from urllib.parse import urlparse

from core.mcp.config import MCPServerConfig

_HTTP_TRANSPORTS = frozenset({"http", "streamable-http", "mcp-remote"})


def is_remote_http(transport: str | None) -> bool:
    return str(transport or "").strip().lower() in _HTTP_TRANSPORTS


def build_remote_http_config(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    risk: str = "medium",
) -> dict:
    """Profile entry for ``holix mcp add --transport http``."""
    data: dict = {
        "transport": "http",
        "url": str(url or "").strip(),
        "timeout": 60.0,
        "default_risk_level": risk or "medium",
    }
    cleaned = {
        str(key).strip(): str(value) for key, value in (headers or {}).items() if str(key).strip()
    }
    if cleaned:
        data["headers"] = cleaned
    return data


def bridge_http_to_stdio(cfg: MCPServerConfig) -> MCPServerConfig:
    """Return a stdio config that runs ``npx -y mcp-remote <url>``.

    A stdio or SSE config is returned unchanged.
    """
    if not is_remote_http(cfg.transport):
        return cfg
    url = str(cfg.url or "").strip()
    if not url:
        return cfg
    args = ["-y", "mcp-remote", url]
    if urlparse(url).scheme == "http":
        args.append("--allow-http")
    env = dict(cfg.env or {})
    seen: set[str] = set()
    index = 0
    for name, value in dict(cfg.headers or {}).items():
        header_name = str(name).strip()
        if not header_name:
            continue
        env_key = f"MCP_REMOTE_H_{index}"
        index += 1
        env[env_key] = str(value)
        args.extend(["--header", f"{header_name}:${{{env_key}}}"])
        seen.add(header_name.lower())
    for key, value in dict(cfg.env or {}).items():
        if not str(key).startswith("MCP_HEADER_") or not str(value).strip():
            continue
        header_name = str(key)[len("MCP_HEADER_") :]
        if not header_name or header_name.lower() in seen:
            continue
        args.extend(["--header", f"{header_name}:${{{key}}}"])
        seen.add(header_name.lower())
    return MCPServerConfig(
        name=cfg.name,
        transport="stdio",
        command="npx",
        args=args,
        env=env,
        cwd=cfg.cwd,
        timeout=cfg.timeout or 60.0,
        default_risk_level=cfg.default_risk_level,
    )
