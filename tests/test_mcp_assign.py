"""Per-agent MCP allow-lists and popular-config fill."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.mcp.assign import (
    fill_assigned_mcp_servers,
    mcp_defs_for_names,
    mcp_tool_allowed,
    servers_for_slot,
)
from core.tools.registry import ToolRegistry


def test_servers_for_slot_inherit_when_missing() -> None:
    assert servers_for_slot({"main": ["holix_studio"]}, "python-coder") is None
    assert servers_for_slot({"python-coder": ["context7"]}, "python-coder") == ["context7"]
    assert servers_for_slot({"python-coder": []}, "python-coder") == []


def test_mcp_tool_allowed_by_slot() -> None:
    assigns = {"main": ["holix_studio"], "python-coder": ["context7", "holix_studio"]}
    assert mcp_tool_allowed("mcp_holix_studio_list", slot="main", assignments=assigns)
    assert not mcp_tool_allowed("mcp_context7_resolve-library-id", slot="main", assignments=assigns)
    assert mcp_tool_allowed(
        "mcp_context7_resolve-library-id", slot="python-coder", assignments=assigns
    )
    assert mcp_tool_allowed("write_file", slot="main", assignments=assigns)


def test_fill_assigned_adds_popular_context7() -> None:
    out = fill_assigned_mcp_servers(
        {"holix_studio": {"transport": "stdio", "command": "x"}},
        {"python-coder": ["context7", "holix_studio"]},
    )
    assert "holix_studio" in out
    assert "context7" in out
    assert out["context7"].get("command") == "npx"
    assert out["context7"].get("_auto_from_assignment") is True


def test_mcp_defs_for_names_fills_missing_popular() -> None:
    subset = mcp_defs_for_names(
        {"holix_studio": {"transport": "stdio", "command": "x"}},
        ["context7", "missing-custom"],
    )
    assert set(subset) == {"context7"}
    assert subset["context7"].get("command") == "npx"


def test_fill_completes_stub_and_keeps_api_key() -> None:
    out = fill_assigned_mcp_servers(
        {
            "context7": {
                "default_risk_level": "no",
                "env": {"CONTEXT7_API_KEY": "ctx7sk-test-key"},
            }
        },
        {"python-coder": ["context7"]},
    )
    assert out["context7"].get("command") == "npx"
    assert "-y" in (out["context7"].get("args") or [])
    assert out["context7"]["env"].get("CONTEXT7_API_KEY") == "ctx7sk-test-key"
    assert out["context7"].get("default_risk_level") == "no"


def test_get_schemas_hides_unassigned_mcp_for_main() -> None:
    reg = ToolRegistry()
    ctx = MagicMock()
    ctx.name = "mcp_context7_query-docs"
    ctx.to_openai_schema.return_value = {
        "type": "function",
        "function": {"name": "mcp_context7_query-docs"},
    }
    studio = MagicMock()
    studio.name = "mcp_holix_studio_list"
    studio.to_openai_schema.return_value = {
        "type": "function",
        "function": {"name": "mcp_holix_studio_list"},
    }
    reg.tools["mcp_context7_query-docs"] = ctx
    reg.tools["mcp_holix_studio_list"] = studio
    reg._mcp_assignments = {
        "main": ["holix_studio"],
        "python-coder": ["context7", "holix_studio"],
    }
    main = {s["function"]["name"] for s in reg.get_schemas(for_agent_slot="main")}
    coder = {s["function"]["name"] for s in reg.get_schemas(for_agent_slot="python-coder")}
    assert "mcp_holix_studio_list" not in main
    assert "mcp_context7_query-docs" not in main
    assert "mcp_context7_query-docs" not in coder
    reg._session_enabled_tools = {"mcp_holix_studio_list", "mcp_context7_query-docs"}
    main = {s["function"]["name"] for s in reg.get_schemas(for_agent_slot="main")}
    coder = {s["function"]["name"] for s in reg.get_schemas(for_agent_slot="python-coder")}
    assert "mcp_holix_studio_list" in main
    assert "mcp_context7_query-docs" not in main
    assert "mcp_context7_query-docs" in coder
    assert "mcp_holix_studio_list" in coder
