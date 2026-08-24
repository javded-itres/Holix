"""Session todo_write tool and store."""

from __future__ import annotations

import pytest
from core.runtime.todo_list import (
    format_todo_checklist,
    format_todo_summary,
    get_todos,
    normalize_todo_items,
    replace_todos,
    reset_todo_store,
)
from core.tools.execution_context import conversation_scope, profile_scope, reset_conversation_scope
from core.tools.todo import TodoWriteTool


@pytest.fixture(autouse=True)
def _reset_todos():
    reset_todo_store()
    yield
    reset_todo_store()


def test_normalize_aliases_and_cap() -> None:
    items = normalize_todo_items(
        [
            {"content": "A", "status": "doing"},
            {"content": "B", "status": "done"},
            "C",
        ]
    )
    assert [i.status for i in items] == ["in_progress", "completed", "pending"]
    assert items[2].content == "C"


def test_normalize_rejects_empty_and_too_many() -> None:
    with pytest.raises(ValueError):
        normalize_todo_items([{"content": "  "}])
    with pytest.raises(ValueError):
        normalize_todo_items([{"content": f"t{i}"} for i in range(21)])


def test_replace_and_get_roundtrip() -> None:
    items = replace_todos(
        "default",
        "tui_default_1",
        [{"id": "a", "content": "Write API", "status": "in_progress"}],
    )
    assert get_todos("default", "tui_default_1")[0].content == "Write API"
    assert "Write API" in format_todo_checklist(items)
    assert "▶" in format_todo_summary(items)
    replace_todos("default", "tui_default_1", [])
    assert get_todos("default", "tui_default_1") == []


@pytest.mark.asyncio
async def test_todo_write_tool_persists() -> None:
    token = conversation_scope("sess_1")
    ptok = profile_scope("default")
    try:
        out = await TodoWriteTool().execute(
            todos=[
                {"content": "One", "status": "in_progress"},
                {"content": "Two", "status": "pending"},
            ]
        )
    finally:
        reset_conversation_scope(token)
        from core.tools.execution_context import reset_profile_scope

        reset_profile_scope(ptok)
    assert "Updated" in out
    assert "One" in out
    stored = get_todos("default", "sess_1")
    assert len(stored) == 2
    assert stored[0].status == "in_progress"


@pytest.mark.asyncio
async def test_todo_write_empty_clears() -> None:
    token = conversation_scope("sess_2")
    try:
        await TodoWriteTool().execute(todos=[{"content": "x"}])
        out = await TodoWriteTool().execute(todos=[])
    finally:
        reset_conversation_scope(token)
    assert "cleared" in out.lower()
    assert get_todos("default", "sess_2") == []
