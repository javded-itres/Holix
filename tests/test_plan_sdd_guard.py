"""Plan generation must not bootstrap or run SDD workflows."""

from __future__ import annotations

from core.graph.nodes.plan_node import (
    _PLAN_FORBIDDEN_TOOLS,
    _get_tools_description,
    _sanitize_plan_steps_no_sdd,
)


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"tool {name}"


class _Tools:
    def list_tools(self):
        return [
            _Tool("read_file"),
            _Tool("sdd_init"),
            _Tool("sdd_apply"),
            _Tool("sdd_list_specs"),
            _Tool("terminal"),
        ]


def test_plan_tools_description_excludes_sdd_mutation() -> None:
    agent = type("A", (), {"tools": _Tools()})()
    desc = _get_tools_description(agent)
    assert "read_file" in desc
    assert "sdd_list_specs" in desc
    assert "- sdd_init:" not in desc
    assert "- sdd_apply:" not in desc
    assert "excluded" in desc.lower() or "sdd_init" in desc  # note only


def test_sanitize_strips_forbidden_tools() -> None:
    plan = [
        {
            "step": 1,
            "description": "Call sdd_init then implement",
            "tools_needed": ["sdd_init", "write_file", "sdd_apply"],
        },
        {
            "step": 2,
            "description": "Read specs",
            "tools_needed": ["sdd_list_specs", "read_file"],
        },
    ]
    out = _sanitize_plan_steps_no_sdd(plan)
    assert out[0]["tools_needed"] == ["write_file"]
    assert "sdd_init" not in out[0]["description"]
    assert "sdd_list_specs" in out[1]["tools_needed"]
    assert _PLAN_FORBIDDEN_TOOLS  # sanity
