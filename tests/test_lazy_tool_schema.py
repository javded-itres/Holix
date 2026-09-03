"""Claude-style deferred tool schemas (core set + tool_search enable_matches)."""

from __future__ import annotations

import json

import pytest
from core.tools.execution_context import reset_tools_registry_scope, tools_registry_scope
from core.tools.lazy_schema import CORE_TOOL_NAMES, lazy_tools_enabled
from core.tools.registry import ToolRegistry
from core.tools.tool_search import ToolSearchTool


def test_lazy_tools_on_by_default() -> None:
    assert lazy_tools_enabled() is True


def test_get_schemas_core_only_by_default() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    names = {s["function"]["name"] for s in registry.get_schemas()}
    assert "tool_search" in names
    assert "read_file" in names
    assert "lsp" in names
    assert "send_chat_files" in names
    assert "self_diagnose" in names
    for core in CORE_TOOL_NAMES:
        if core in registry.tools:
            assert core in names, core
    assert "sql_query" not in names
    assert "notebook_edit" not in names
    assert "job_monitor" not in names
    assert "sdd_apply" not in names


def test_deferred_tool_still_executes_when_not_in_schema() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    names = {s["function"]["name"] for s in registry.get_schemas()}
    assert "sql_query" not in names
    assert "sql_query" in registry.tools


@pytest.mark.asyncio
async def test_tool_search_enable_matches_adds_deferred_schema() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    token = tools_registry_scope(registry)
    try:
        before = {s["function"]["name"] for s in registry.get_schemas()}
        assert "sql_query" not in before
        raw = await ToolSearchTool().execute(query="sql database query", enable_matches=True)
        payload = json.loads(raw)
        assert payload["ok"] is True
        names = [m["name"] for m in payload["matches"]]
        assert "sql_query" in names
        after = {s["function"]["name"] for s in registry.get_schemas()}
        assert "sql_query" in after
        assert "read_file" in after
    finally:
        reset_tools_registry_scope(token)


def test_subagent_allowlist_exposes_deferred_tools() -> None:
    from core.subagents.react_agent import FilteredToolRegistry

    inner = ToolRegistry(profile_name="default")
    inner.register_all()
    assert "sql_query" not in {s["function"]["name"] for s in inner.get_schemas()}
    child = FilteredToolRegistry(
        inner,
        allowed={"read_file", "sql_query"},
        inherit_mcp=False,
        mcp_servers=[],
    )
    names = {s["function"]["name"] for s in child.get_schemas()}
    assert "read_file" in names
    assert "sql_query" in names
    assert "write_file" not in names


def test_lazy_tools_env_off_sends_full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_LAZY_TOOLS", "0")
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    names = {s["function"]["name"] for s in registry.get_schemas()}
    assert "sql_query" in names
    assert "notebook_edit" in names
    assert "job_monitor" in names
