"""Basic tests for MCP integration (adapters + config + manager mock)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from core.mcp.config import MCPServerConfig, validate_server_config
from core.mcp.tool import MCPTool


def test_mcp_server_config_stdio():
    cfg = MCPServerConfig(
        name="fs",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )
    assert cfg.name == "fs"
    assert validate_server_config(cfg) == []


def test_mcp_server_config_sse_bad():
    cfg = MCPServerConfig(name="remote", transport="sse")  # missing url
    errs = validate_server_config(cfg)
    assert any("url" in e for e in errs)


@pytest.mark.asyncio
async def test_mcp_tool_adapter_delegates(tmp_path: Path):
    """MCPTool.execute delegates to manager.call_tool and normalizes result."""
    mock_mgr = AsyncMock()
    mock_mgr.call_tool.return_value = {"content": [{"type": "text", "text": "hello from mcp"}]}

    tool = MCPTool(
        server_name="fs",
        tool_name="read_file",
        description="Read a file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        manager=mock_mgr,
        risk_level="low",
    )
    assert tool.name == "mcp_fs_read_file"
    assert "read_file" in tool.description or "Read a file" in tool.description

    res = await tool.execute(path=str(tmp_path / "x.txt"))
    assert "hello from mcp" in res
    mock_mgr.call_tool.assert_awaited()


def test_registry_mcp_hook_exists():
    from core.tools.registry import ToolRegistry

    reg = ToolRegistry()
    assert hasattr(reg, "register_mcp")
    assert hasattr(reg, "mcp_status")
    assert reg.mcp_status() == []


def test_mcp_manager_mark_ready_harvests():
    from core.mcp.manager import MCPManager

    seen: list[str] = []
    mgr = MCPManager({})
    mgr.on_tools_ready = seen.append
    mgr._mark_ready(
        "context7",
        [{"name": "resolve-library-id", "description": "", "inputSchema": {}}],
    )
    assert seen == ["context7"]
    status = {row["name"]: row for row in mgr.server_status()}
    # no configs → empty status; still discovered
    assert status == {}
    assert mgr._discovered_tools["context7"][0]["name"] == "resolve-library-id"


@pytest.mark.asyncio
async def test_stdio_mcp_stderr_stays_off_the_terminal(tmp_path: Path, monkeypatch):
    """A crashing stdio server must not write its stderr onto the TUI terminal."""
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    import os
    import sys

    from core.mcp.manager import MCPManager

    read_fd, write_fd = os.pipe()
    saved = os.dup(2)
    os.dup2(write_fd, 2)
    os.close(write_fd)
    os.set_blocking(read_fd, False)
    try:
        mgr = MCPManager(
            {
                "boom": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [
                        "-c",
                        "import sys; sys.stderr.write('MCP_STDERR_BOOM\\n'); sys.stderr.flush()",
                    ],
                }
            }
        )
        await mgr.connect_all()
        await mgr.wait_ready(["boom"], timeout=5)
        await mgr.disconnect_all()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        leaked = b""
        while True:
            try:
                chunk = os.read(read_fd, 4096)
            except BlockingIOError:
                break
            if not chunk:
                break
            leaked += chunk
        os.close(read_fd)

    assert b"MCP_STDERR_BOOM" not in leaked
    log = (tmp_path / "logs" / "mcp-stderr.log").read_text(encoding="utf-8")
    assert "MCP_STDERR_BOOM" in log
    assert " boom " in log


def test_mcp_manager_status_includes_configured_servers():
    from core.mcp.manager import MCPManager

    mgr = MCPManager({"context7": {"transport": "stdio", "command": "npx", "args": ["-y", "x"]}})
    rows = mgr.server_status()
    assert rows[0]["name"] == "context7"
    assert rows[0]["ready"] is False
    assert rows[0]["tools"] == 0
    mgr._mark_ready(
        "context7",
        [
            {"name": "resolve-library-id", "description": "", "inputSchema": {}},
            {"name": "query-docs", "description": "", "inputSchema": {}},
        ],
    )
    rows = mgr.server_status()
    assert rows[0]["ready"] is True
    assert rows[0]["tools"] == 2
