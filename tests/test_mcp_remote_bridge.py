"""stdio↔HTTP bridge through mcp-remote."""

from __future__ import annotations

import pytest
from cli.commands.mcp import _parse_header
from core.mcp.config import MCPServerConfig, validate_server_config
from core.mcp.remote_bridge import bridge_http_to_stdio, build_remote_http_config


def test_https_remote_uses_mcp_remote_without_putting_secret_in_argv() -> None:
    saved = build_remote_http_config(
        "https://example.com/mcp",
        {"Authorization": "Bearer secret"},
    )
    cfg = MCPServerConfig.from_dict("docs", saved)
    assert validate_server_config(cfg) == []
    launched = bridge_http_to_stdio(cfg)
    assert launched.transport == "stdio"
    assert launched.command == "npx"
    assert launched.args[:3] == ["-y", "mcp-remote", "https://example.com/mcp"]
    assert "--allow-http" not in launched.args
    header = launched.args[launched.args.index("--header") + 1]
    assert header.startswith("Authorization:${")
    assert "secret" not in " ".join(launched.args)
    assert "Bearer secret" in launched.env.values()


def test_plain_http_allows_private_network() -> None:
    cfg = MCPServerConfig.from_dict(
        "lan",
        {"transport": "streamable-http", "url": "http://192.168.88.1:4000/mcp"},
    )
    launched = bridge_http_to_stdio(cfg)
    assert launched.args[-1] == "--allow-http"
    assert "http://192.168.88.1:4000/mcp" in launched.args


def test_stdio_is_not_rewritten() -> None:
    cfg = MCPServerConfig.from_dict(
        "local",
        {"transport": "stdio", "command": "uvx", "args": ["some-mcp"]},
    )
    launched = bridge_http_to_stdio(cfg)
    assert launched.command == "uvx"
    assert launched.args == ["some-mcp"]


def test_mcp_header_env_is_forwarded() -> None:
    cfg = MCPServerConfig.from_dict(
        "docs",
        {
            "transport": "http",
            "url": "https://example.com/mcp",
            "env": {"MCP_HEADER_Authorization": "Bearer from-env"},
        },
    )
    launched = bridge_http_to_stdio(cfg)
    assert "Authorization:${MCP_HEADER_Authorization}" in launched.args
    assert "from-env" not in " ".join(launched.args)


def test_remote_alias_without_url_is_incomplete() -> None:
    from core.mcp.assign import mcp_server_incomplete

    assert mcp_server_incomplete({"transport": "http", "url": "https://example.com/mcp"}) is False
    assert mcp_server_incomplete({"transport": "mcp-remote"}) is True


def test_http_without_url_is_invalid() -> None:
    cfg = MCPServerConfig.from_dict("docs", {"transport": "http"})
    assert any("url" in err for err in validate_server_config(cfg))


def test_parse_header() -> None:
    assert _parse_header("Authorization: Bearer secret") == ("Authorization", "Bearer secret")
    with pytest.raises(ValueError):
        _parse_header("not a header")
