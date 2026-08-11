"""uvx MCP SDK 1.x pin for reference servers broken on mcp 2.x."""

from __future__ import annotations

from core.mcp.uvx_compat import (
    MCP_SDK_V1_SPEC,
    ensure_uvx_mcp_v1_pin,
    normalize_mcp_servers_uvx,
)


def test_fetch_gets_pin() -> None:
    assert ensure_uvx_mcp_v1_pin("uvx", ["mcp-server-fetch"]) == [
        "--with",
        MCP_SDK_V1_SPEC,
        "mcp-server-fetch",
    ]


def test_already_pinned_not_doubled() -> None:
    args = ["--with", "mcp>=1.9.0,<2", "mcp-server-fetch"]
    assert ensure_uvx_mcp_v1_pin("uvx", args) == args


def test_npx_unchanged() -> None:
    assert ensure_uvx_mcp_v1_pin("npx", ["-y", "foo"]) == ["-y", "foo"]


def test_normalize_servers() -> None:
    servers = {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
        "ctx": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
    }
    out = normalize_mcp_servers_uvx(servers)
    assert out["fetch"]["args"][0] == "--with"
    assert out["fetch"]["args"][2] == "mcp-server-fetch"
    assert out["ctx"]["args"] == ["-y", "@upstash/context7-mcp"]
