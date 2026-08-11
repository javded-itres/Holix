"""Compat helpers for uvx-launched MCP Python servers.

MCP Python SDK 2.0 renamed ``McpError`` → ``MCPError``. Many reference servers
(``mcp-server-fetch``, ``mcp-server-git``, …) still import ``McpError`` and crash
on startup when ``uvx`` resolves the latest ``mcp`` dependency.

Holix pins SDK 1.x for those packages via ``uvx --with 'mcp>=1.9.0,<2'``.
"""

from __future__ import annotations

from typing import Any

# Packages known to import mcp.shared.exceptions.McpError (SDK 1.x API).
_UVX_PACKAGES_NEEDING_MCP_V1: frozenset[str] = frozenset(
    {
        "mcp-server-fetch",
        "mcp-server-git",
        "mcp-server-sqlite",
        "mcp-server-time",
        "mcp-server-everything",
    }
)

MCP_SDK_V1_SPEC = "mcp>=1.9.0,<2"


def _args_have_mcp_pin(args: list[str]) -> bool:
    for i, a in enumerate(args):
        if a != "--with" or i + 1 >= len(args):
            continue
        spec = args[i + 1].strip()
        # bare "mcp", version specs, or extras
        name = spec.split("[", 1)[0]
        if (
            name == "mcp"
            or name.startswith("mcp=")
            or name.startswith("mcp>")
            or name.startswith("mcp<")
        ):
            return True
        if name.startswith("mcp") and any(c in name for c in "><="):
            return True
    return False


def _needs_mcp_v1_pin(args: list[str]) -> bool:
    for a in args:
        base = a.split("==", 1)[0].split("[", 1)[0].strip()
        if base in _UVX_PACKAGES_NEEDING_MCP_V1:
            return True
        # Any remaining mcp-server-* reference server is likely SDK 1.x era
        if base.startswith("mcp-server-"):
            return True
    return False


def ensure_uvx_mcp_v1_pin(command: str | None, args: list[str] | None) -> list[str]:
    """Return uvx args with an SDK 1.x pin when launching known-broken packages."""
    out = [str(a) for a in (args or [])]
    cmd = (command or "").strip()
    if cmd not in {"uvx", "uv"}:
        return out
    if not _needs_mcp_v1_pin(out):
        return out
    if _args_have_mcp_pin(out):
        return out
    return ["--with", MCP_SDK_V1_SPEC, *out]


def normalize_mcp_servers_uvx(servers: dict[str, Any] | None) -> dict[str, Any]:
    """Copy mcp_servers dict, pinning MCP SDK 1.x for uvx Python reference servers."""
    if not servers:
        return {}
    out: dict[str, Any] = {}
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            out[name] = raw
            continue
        data = dict(raw)
        command = data.get("command")
        args = data.get("args")
        if not isinstance(args, list):
            args = []
        pinned = ensure_uvx_mcp_v1_pin(
            str(command) if command is not None else None,
            [str(a) for a in args],
        )
        if pinned != list(args):
            data["args"] = pinned
        out[name] = data
    return out
