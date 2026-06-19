"""Tool schema registration must not send duplicate function names to the LLM."""

from __future__ import annotations

from collections import Counter

from core.tools.aliases import resolve_tool_name
from core.tools.registry import ToolRegistry


def test_get_schemas_has_no_duplicate_function_names() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    names = [s["function"]["name"] for s in registry.get_schemas()]
    dupes = {k: v for k, v in Counter(names).items() if v > 1}
    assert dupes == {}
    assert "start_background_process" in names
    assert "check_background_process" in names


def test_run_project_alias_resolves() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    assert resolve_tool_name("run_project") == "start_background_process"
    assert "start_background_process" in registry.tools