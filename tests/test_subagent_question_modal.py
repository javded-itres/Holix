"""Sub-agent question modal + presenter wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from cli.tui.modals.subagent_question import SubagentQuestionModal
from cli.tui.modals.subagent_question_presenter import SubagentQuestionPresenter
from core.subagents.interaction_events import SubAgentQuestionEvent


def test_modal_from_event_fields():
    ev = SubAgentQuestionEvent(
        request_id="subq_abc",
        subagent_name="coder-2",
        question="Use JWT or sessions?",
        context="auth/middleware.py has no auth yet",
    )
    modal = SubagentQuestionModal.from_event(
        ev, task_preview="Fix Shop API", queue_index=1, queue_total=2
    )
    assert modal.request_id == "subq_abc"
    assert modal.subagent_name == "coder-2"
    assert "JWT" in modal.question
    assert "middleware" in modal.context
    assert modal.task_preview == "Fix Shop API"
    assert modal.queue_total == 2


def test_presenter_queues_and_opens_modal():
    opened: list = []

    class FakeStack:
        def __init__(self):
            self._active = None

        @property
        def has_active(self):
            return self._active is not None

        @property
        def active_kind(self):
            return self._active

        def set_active(self, kind):
            self._active = kind

    class FakeApp:
        def __init__(self):
            self.agent = None
            self.logs: list[str] = []
            self.status_refreshed = 0

        def transcript_write(self, t):
            self.logs.append(str(t))

        def call_later(self, cb, *a, **k):
            cb(*a, **k)

        def push_screen(self, modal, callback):
            opened.append((modal, callback))

        def _refresh_status_bar(self):
            self.status_refreshed += 1

    stack = FakeStack()
    app = FakeApp()
    presenter = SubagentQuestionPresenter(app, stack)

    e1 = SubAgentQuestionEvent(
        request_id="subq_1",
        subagent_name="coder",
        question="Pick DB?",
        context="postgres vs sqlite",
    )
    e2 = SubAgentQuestionEvent(
        request_id="subq_2",
        subagent_name="coder-2",
        question="Pick queue?",
    )
    presenter.show(e1)
    presenter.show(e2)

    assert len(opened) == 1
    modal, _cb = opened[0]
    assert modal.subagent_name == "coder"
    assert "Pick DB" in modal.question
    assert presenter.pending_count == 2  # active + one queued
    assert any("Pick DB" in line for line in app.logs)

    # Dismiss with answer → second modal opens
    bridge = MagicMock()
    bridge.resolve_question.return_value = True
    bridge.pending_question_ids = ["subq_2"]
    app.agent = SimpleNamespace(subagents=SimpleNamespace(interactions=bridge))

    # Wire real resolve path: patch get_interaction_bridge via agent
    from core.subagents import interaction as interaction_mod

    original = interaction_mod.get_interaction_bridge
    interaction_mod.get_interaction_bridge = lambda agent: bridge  # type: ignore
    try:
        _cb("postgres")
        assert bridge.resolve_question.called
        assert len(opened) == 2
        assert opened[1][0].subagent_name == "coder-2"
    finally:
        interaction_mod.get_interaction_bridge = original


def test_presenter_dedupes_by_request_id():
    class FakeStack:
        has_active = False
        active_kind = None

        def set_active(self, kind):
            pass

    class FakeApp:
        agent = None

        def transcript_write(self, t):
            pass

        def call_later(self, cb, *a, **k):
            cb(*a, **k)

        def push_screen(self, modal, callback):
            pass

    presenter = SubagentQuestionPresenter(FakeApp(), FakeStack())
    ev = SubAgentQuestionEvent(
        request_id="subq_same",
        subagent_name="coder",
        question="once?",
    )
    presenter.show(ev)
    presenter.show(ev)
    assert presenter.pending_count == 1


def test_sync_with_bridge_drops_resolved():
    class FakeStack:
        has_active = False
        active_kind = None

        def set_active(self, kind):
            pass

    class FakeApp:
        def __init__(self):
            self.agent = None

        def transcript_write(self, t):
            pass

    bridge = MagicMock()
    bridge.pending_question_ids = ["subq_live"]
    app = FakeApp()
    app.agent = SimpleNamespace(subagents=SimpleNamespace(interactions=bridge))
    presenter = SubagentQuestionPresenter(app, FakeStack())
    presenter._queue = [
        SubAgentQuestionEvent(request_id="subq_done", subagent_name="a", question="x"),
        SubAgentQuestionEvent(request_id="subq_live", subagent_name="b", question="y"),
    ]
    from core.subagents import interaction as interaction_mod

    original = interaction_mod.get_interaction_bridge
    interaction_mod.get_interaction_bridge = lambda agent: bridge  # type: ignore
    try:
        presenter.sync_with_bridge()
        assert len(presenter._queue) == 1
        assert presenter._queue[0].request_id == "subq_live"
    finally:
        interaction_mod.get_interaction_bridge = original
