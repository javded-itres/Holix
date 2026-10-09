"""Plan text is published when plan mode changes, even without approval."""

from __future__ import annotations

import json

import pytest
from cli.tui.code.handlers.events import CodeEventHandler
from core.agent_events import PlanModeChangedEvent
from core.tools.execution_context import (
    agent_emit_scope,
    conversation_scope,
    reset_agent_emit_scope,
    reset_conversation_scope,
)
from core.tools.plan_mode import PlanModeTool, current_plan_text
from core.tools.plan_mode_state import exit_plan_mode
from rich.markdown import Markdown


class _Log:
    def __init__(self) -> None:
        self.items: list = []

    def transcript_write(self, content) -> None:
        self.items.append(content)

    def transcript_scroll_bottom(self) -> None:
        return None


@pytest.mark.asyncio
async def test_exit_without_approval_still_publishes_the_plan() -> None:
    seen: list[PlanModeChangedEvent] = []
    token = conversation_scope("plan-display")
    emit_token = agent_emit_scope(seen.append)
    try:
        exit_plan_mode()
        entered = json.loads(await PlanModeTool().execute(action="enter", plan="Этап 1: каркас"))
        assert entered["active"] is True
        assert any(event.plan == "Этап 1: каркас" for event in seen)
        assert current_plan_text() == "Этап 1: каркас"
        left = json.loads(
            await PlanModeTool().execute(
                action="exit",
                plan="Этап 1: каркас\nЭтап 2: DOCX",
                require_approval=False,
            )
        )
        assert left["active"] is False
        assert left["plan"].startswith("Этап 1")
        published = [event.plan for event in seen if event.action == "exit"]
        assert published == ["Этап 1: каркас\nЭтап 2: DOCX"]
    finally:
        exit_plan_mode()
        reset_agent_emit_scope(emit_token)
        reset_conversation_scope(token)


def test_tui_prints_plan_mode_text() -> None:
    app = _Log()
    CodeEventHandler(app).handle(PlanModeChangedEvent(action="exit", plan="Этап 2: DOCX"))
    assert len(app.items) == 1
    shown = app.items[0]
    assert isinstance(shown, Markdown)
    assert "Этап 2: DOCX" in shown.markup
    assert shown.markup.lstrip().startswith("# План")
