"""Session todo checklist — whole-list replace, visible in TUI / Telegram / MAX."""

from __future__ import annotations

from typing import Any

from core.runtime.todo_list import (
    format_todo_checklist,
    format_todo_summary,
    items_as_dicts,
    replace_todos,
)
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name


class TodoWriteTool(BaseTool):
    """Replace the session todo list (Claude Code / dsh ``todo_write``)."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "todo_write"
        self.risk_level = "no"
        self.description = (
            "Replace the session checklist shown in TUI (top of screen) and "
            "Telegram/MAX live status. Send the ENTIRE list every call — it "
            "replaces the previous list (no partial updates). Use on multi-step "
            "work (3+ steps). Statuses: pending, in_progress, completed, cancelled. "
            "Mark every task you are actively doing as in_progress. Empty list "
            "clears the checklist. This is a plan, not proof of work — still call "
            "the real tools (write_file, terminal, …) to do the work."
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": (
                        "Full replacement list. Each item: content (required) and "
                        "status (pending|in_progress|completed|cancelled). Optional id."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Stable id for this item (optional)",
                            },
                            "content": {
                                "type": "string",
                                "description": "Short task text",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "cancelled",
                                ],
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["todos"],
        }

    async def execute(self, todos: Any = None, **_: Any) -> str:
        profile = get_profile_name()
        conversation_id = get_conversation_id()
        try:
            items = replace_todos(profile, conversation_id, todos)
        except ValueError as exc:
            return f"Error: {exc}"
        self._emit(profile, conversation_id, items)
        if not items:
            return "Todos cleared."
        summary = format_todo_summary(items)
        body = format_todo_checklist(items)
        return f"Updated {summary}.\n{body}"

    def _emit(self, profile: str, conversation_id: str, items: list) -> None:
        try:
            from core.agent_events import TodoListUpdatedEvent
            from core.tools.execution_context import get_agent_emit

            emit = get_agent_emit()
            if emit is None:
                return
            emit(
                TodoListUpdatedEvent(
                    conversation_id=conversation_id,
                    profile=profile,
                    todos=items_as_dicts(items),
                )
            )
        except Exception:
            return
