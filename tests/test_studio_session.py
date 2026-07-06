"""Tests for Holix Studio WebSocket session."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agent_events import (
    AgentEventBus,
    FinalResponseEvent,
    ThinkingEvent,
)
from integrations.desktop.session import StudioSession


@pytest.fixture
def captured() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def session(captured: list[dict[str, Any]]) -> StudioSession:
    sess = StudioSession("test")
    sess.set_broadcast(lambda payload: _capture(captured, payload))
    return sess


async def _capture(store: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    store.append(payload)


def _mock_agent(
    *,
    holix_events: list[AgentEvent] | None = None,
) -> MagicMock:
    agent = MagicMock()
    bus = AgentEventBus()
    agent.events = bus
    agent.config = MagicMock()
    agent._use_langgraph = True

    async def fake_run_holix(
        _agent: Any,
        _text: str,
        _conversation_id: str,
        *,
        stream: bool = False,
    ) -> AsyncGenerator[Any, None]:
        for event in holix_events or []:
            yield event

    return agent, bus, fake_run_holix


@pytest.mark.asyncio
async def test_stop_run_without_active_run_does_not_notify(
    session: StudioSession,
    captured: list[dict[str, Any]],
) -> None:
    cancelled = await session.stop_run(notify=True)
    assert cancelled is False
    assert captured == []


@pytest.mark.asyncio
async def test_user_message_forwards_bus_final_response(
    session: StudioSession,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, bus, _ = _mock_agent()

    async def fake_run_with_bus_final(
        _agent: Any,
        _text: str,
        _conversation_id: str,
        *,
        stream: bool = False,
    ) -> AsyncGenerator[Any, None]:
        yield ThinkingEvent(message="boot", conversation_id="studio")
        bus.emit(
            FinalResponseEvent(
                content="Привет!",
                conversation_id="studio",
            )
        )
        await asyncio.sleep(0)

    session.agent = agent
    session._attach_event_forwarder(agent)
    monkeypatch.setattr(
        "core.runtime.executor.run_holix",
        fake_run_with_bus_final,
    )

    await session.handle_client_message({"type": "user_message", "text": "Как дела?"})
    if session._run_task:
        await session._run_task

    types = [m["type"] for m in captured]
    assert "run_stopped" not in types
    assert "run_started" in types
    assert "thinking" in types
    assert "final_response" in types
    assert any(m.get("content") == "Привет!" for m in captured)
    assert "run_finished" in types


@pytest.mark.asyncio
async def test_second_message_while_running_is_ignored(
    session: StudioSession,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, bus, fake_run = _mock_agent()

    async def slow_run(
        _agent: Any,
        _text: str,
        _conversation_id: str,
        *,
        stream: bool = False,
    ) -> AsyncGenerator[Any, None]:
        yield ThinkingEvent(message="boot", conversation_id="studio")
        await asyncio.sleep(0.2)
        bus.emit(FinalResponseEvent(content="done", conversation_id="studio"))

    session.agent = agent
    session._attach_event_forwarder(agent)
    monkeypatch.setattr("core.runtime.executor.run_holix", slow_run)

    await session.handle_client_message({"type": "user_message", "text": "first"})
    await session.handle_client_message({"type": "user_message", "text": "second"})
    if session._run_task:
        await session._run_task

    started = [m for m in captured if m["type"] == "run_started"]
    assert len(started) == 1


@pytest.mark.asyncio
async def test_slash_stop_notifies_once(
    session: StudioSession,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, _, fake_run = _mock_agent()

    async def hanging_run(
        _agent: Any,
        _text: str,
        _conversation_id: str,
        *,
        stream: bool = False,
    ) -> AsyncGenerator[Any, None]:
        yield ThinkingEvent(message="boot", conversation_id="studio")
        await asyncio.sleep(10)

    session.agent = agent
    monkeypatch.setattr("core.runtime.executor.run_holix", hanging_run)

    await session.handle_client_message({"type": "user_message", "text": "wait"})
    await asyncio.sleep(0.05)
    await session.handle_client_message({"type": "slash", "command": "/stop"})
    await asyncio.sleep(0.05)

    stopped = [m for m in captured if m["type"] == "run_stopped"]
    assert len(stopped) == 1