"""Basic tests for MCP integration (adapters + config + manager mock)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
