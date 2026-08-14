"""TUI ConfirmationPresenter: modal queue + slash resolve must not hang."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.tui.modals.stack import ModalStack
from core.agent_events import AgentEventBus
from core.security.confirmation import (
    ActionGuard,
    ConfirmationChoice,
    PermissionManager,
    RiskLevel,
)
from core.security.confirmation_events import ConfirmationRequestEvent


class _FakeApp:
    def __init__(self) -> None:
        self.agent = None
        self.logs: list[str] = []
        self._pending_confirmation = None
        self._action_guard_reference = None
        self.opened: list[tuple] = []
        self.popped = 0

    def transcript_write(self, t) -> None:
        self.logs.append(str(t))

    def _append_to_log(self, t) -> None:
        self.transcript_write(t)

    def call_later(self, cb, *a, **k) -> None:
        cb(*a, **k)

    def push_screen(self, modal, callback) -> None:
        self.opened.append((modal, callback))

    def pop_screen(self) -> None:
        self.popped += 1

    def set_timer(self, delay, cb) -> None:
        cb()

    def _refresh_status_bar(self) -> None:
        pass

    def set_status_line(self, s) -> None:
        pass


class _HighRiskTool:
    risk_level = "high"


async def _ok(**kwargs):
    return "done"


def _setup(tmp_path: Path):
    data = tmp_path / "data"
    (data / "security").mkdir(parents=True)
    (data / "security" / "permissions.json").write_text('{"always_grants":[]}')
    bus = AgentEventBus()
    pm = PermissionManager(data_dir=data)
    pm.load()
    guard = ActionGuard(
        event_bus=bus,
        permission_manager=pm,
        auto_allow_threshold=RiskLevel.LOW,
        interactive=True,
        confirmation_timeout=0,
        data_dir=data,
    )
    app = _FakeApp()
    app.agent = SimpleNamespace(
        tools=SimpleNamespace(_action_guard=guard),
        events=bus,
        subagents=None,
    )
    stack = ModalStack(app)

    def _on_event(event) -> None:
        if isinstance(event, ConfirmationRequestEvent):
            app.call_later(stack.confirmation.show, event)

    bus.subscribe(_on_event)
    return app, stack, guard, pm


@pytest.mark.asyncio
async def test_slash_resolve_releases_modal_and_next_opens(tmp_path: Path):
    """/1 while modal open must not freeze the next confirmation forever."""
    app, stack, guard, pm = _setup(tmp_path)

    t1 = asyncio.create_task(
        guard.check_and_execute("run_terminal_command", _HighRiskTool(), {"c": "1"}, _ok, "a")
    )
    await asyncio.sleep(0.02)
    assert len(app.opened) == 1
    assert stack.confirmation._modal_open

    # Slash path: resolve without modal dismiss callback
    stack.confirmation.resolve(ConfirmationChoice.ALLOW_ONCE)
    assert await asyncio.wait_for(t1, timeout=2.0) == "done"
    assert stack.confirmation._modal_open is False
    assert stack.confirmation._active is None
    assert app.popped == 1

    pm.clear_session()
    t2 = asyncio.create_task(
        guard.check_and_execute("run_terminal_command", _HighRiskTool(), {"c": "2"}, _ok, "b")
    )
    await asyncio.sleep(0.05)
    assert len(app.opened) == 2, "second confirmation modal must open after slash resolve"
    app.opened[1][1]("allow_once")
    assert await asyncio.wait_for(t2, timeout=2.0) == "done"


@pytest.mark.asyncio
async def test_modal_dismiss_allow_session_unblocks_concurrent(tmp_path: Path):
    app, stack, guard, pm = _setup(tmp_path)

    t1 = asyncio.create_task(
        guard.check_and_execute("run_terminal_command", _HighRiskTool(), {"c": "a"}, _ok, "c1")
    )
    t2 = asyncio.create_task(
        guard.check_and_execute("run_terminal_command", _HighRiskTool(), {"c": "b"}, _ok, "c2")
    )
    await asyncio.sleep(0.05)
    assert len(guard._pending_confirmations) == 2
    assert len(app.opened) == 1
    assert len(stack.confirmation._queue) == 1

    app.opened[0][1]("allow_session")
    r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
    assert r1 == r2 == "done"


@pytest.mark.asyncio
async def test_modal_key_deny(tmp_path: Path):
    app, stack, guard, _pm = _setup(tmp_path)

    t = asyncio.create_task(
        guard.check_and_execute("run_terminal_command", _HighRiskTool(), {"c": "x"}, _ok, "d")
    )
    await asyncio.sleep(0.02)
    app.opened[0][1]("deny")
    result = await asyncio.wait_for(t, timeout=2.0)
    assert "denied" in result.lower() or result.startswith("Error")
