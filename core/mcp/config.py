"""MCP server configuration models (for profile + runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


Transport = Literal["stdio", "sse"]


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server connection."""

    name: str
    transport: Transport = "stdio"

    # stdio
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None

    # sse / http
    url: Optional[str] = None

    # common
    timeout: float = 30.0
    default_risk_level: str = "medium"  # no|low|medium|high ; used as baseline for guard

    def to_dict(self) -> Dict[str, Any]:
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
            if self.env:
                d["env"] = self.env
            if self.cwd:
                d["cwd"] = self.cwd
        else:
            if self.url:
                d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":
        from core.config_utils import resolve_env_refs

        resolved = resolve_env_refs(dict(data))
        args = resolved.get("args", [])
        if isinstance(args, list):
            args = [str(a) for a in args]
        env = resolved.get("env", {})
        if not isinstance(env, dict):
            env = {}
        return cls(
            name=name,
            transport=resolved.get("transport", "stdio"),
            command=resolved.get("command"),
            args=args,
            env={str(k): str(v) for k, v in env.items()},
            cwd=resolved.get("cwd"),
            url=resolved.get("url"),
            timeout=float(resolved.get("timeout", 30.0)),
            default_risk_level=resolved.get("default_risk_level", "medium"),
        )


def validate_server_config(cfg: MCPServerConfig) -> List[str]:
    """Return list of validation error strings (empty = ok)."""
    errs: List[str] = []
    if cfg.transport == "stdio":
        if not cfg.command:
            errs.append("stdio requires 'command'")
    elif cfg.transport == "sse":
        if not cfg.url:
            errs.append("sse requires 'url'")
    if cfg.timeout <= 0:
        errs.append("timeout must be > 0")
    if cfg.default_risk_level not in ("no", "low", "medium", "high"):
        errs.append("default_risk_level invalid")
    return errs
