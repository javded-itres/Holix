"""MCP server configuration models (for profile + runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Transport = Literal["stdio", "sse", "http", "streamable-http", "mcp-remote"]


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server connection."""

    name: str
    transport: Transport = "stdio"

    # stdio
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None

    # sse / http
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    # common
    timeout: float = 30.0
    default_risk_level: str = "medium"  # no|low|medium|high ; used as baseline for guard

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "transport": self.transport,
            "timeout": self.timeout,
            "default_risk_level": self.default_risk_level,
        }
        if self.transport == "stdio":
            if self.command:
                d["command"] = self.command
            if self.args:
                d["args"] = self.args
            if self.cwd:
                d["cwd"] = self.cwd
        else:
            if self.url:
                d["url"] = self.url
        if self.headers:
            d["headers"] = dict(self.headers)
        # env holds secrets + MCP_HEADER_* for both transports
        if self.env:
            d["env"] = self.env
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MCPServerConfig:
        from core.config_utils import resolve_env_refs

        resolved = resolve_env_refs(dict(data))
        args = resolved.get("args", [])
        if isinstance(args, list):
            args = [str(a) for a in args]
        env = resolved.get("env", {})
        if not isinstance(env, dict):
            env = {}
        headers = resolved.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}
        return cls(
            name=name,
            transport=resolved.get("transport", "stdio"),
            command=resolved.get("command"),
            args=args,
            env={str(k): str(v) for k, v in env.items()},
            cwd=resolved.get("cwd"),
            url=resolved.get("url"),
            headers={str(k): str(v) for k, v in headers.items()},
            timeout=float(resolved.get("timeout", 30.0)),
            default_risk_level=resolved.get("default_risk_level", "medium"),
        )


def validate_server_config(cfg: MCPServerConfig) -> list[str]:
    """Return list of validation error strings (empty = ok)."""
    errs: list[str] = []
    from core.mcp.remote_bridge import is_remote_http

    if cfg.transport == "stdio":
        if not cfg.command:
            errs.append("stdio requires 'command'")
    elif cfg.transport == "sse" or is_remote_http(cfg.transport):
        if not cfg.url:
            errs.append(f"{cfg.transport} requires 'url'")
    if cfg.timeout <= 0:
        errs.append("timeout must be > 0")
    if cfg.default_risk_level not in ("no", "low", "medium", "high"):
        errs.append("default_risk_level invalid")
    return errs
