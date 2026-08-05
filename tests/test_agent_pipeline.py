"""Agent pipeline classic vs modern."""

from __future__ import annotations

from core.agent_pipeline import (
    PIPELINE_CLASSIC,
    PIPELINE_MODERN,
    is_classic_pipeline,
    is_modern_pipeline,
    normalize_pipeline,
)
from core.graph.action_honesty import resolve_tool_choice


def test_normalize_pipeline_aliases() -> None:
    assert normalize_pipeline("1.0.2") == PIPELINE_CLASSIC
    assert normalize_pipeline("classic") == PIPELINE_CLASSIC
    assert normalize_pipeline("modern") == PIPELINE_MODERN
    assert normalize_pipeline(None) == PIPELINE_CLASSIC
    assert is_classic_pipeline("legacy")
    assert is_modern_pipeline("current")


def test_classic_does_not_force_tools_on_action() -> None:
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    state = {
        "user_input": "Сделай пост",
        "messages": [{"role": "user", "content": "Сделай пост"}],
        "tool_results": [],
        "honesty_nudge_count": 0,
        "agent_pipeline": "classic",
    }
    assert resolve_tool_choice(state, state["messages"], tools=tools) == "auto"


def test_status_menu_includes_pipeline_button() -> None:
    import pytest

    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Pipeline" in labels
