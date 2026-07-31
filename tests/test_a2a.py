"""A2A protocol: models, card, server, client tools, config."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.a2a.card import build_agent_card
from core.a2a.client import extract_task_text
from core.a2a.config import load_a2a_config
from core.a2a.models import A2AMessage, TaskState
from core.a2a.server import cancel_task, get_task_public, handle_message_send
from core.a2a.store import A2ATaskStore


def test_message_parse_and_text() -> None:
    msg = A2AMessage.parse(
        {
            "role": "user",
            "parts": [{"kind": "text", "text": "hello"}],
            "contextId": "ctx1",
        }
    )
    assert msg.role == "user"
    assert msg.text_content() == "hello"
    assert msg.contextId == "ctx1"


def test_load_a2a_config_from_raw() -> None:
    cfg = load_a2a_config(
        raw={
            "a2a": {
                "enabled": True,
                "public_url": "https://x.example/a2a",
                "remote_agents": [
                    {"name": "r1", "url": "https://r1.example/a2a"},
                ],
            }
        }
    )
    assert cfg.enabled is True
    assert cfg.public_url == "https://x.example/a2a"
    assert len(cfg.remote_agents) == 1
    assert cfg.remote_agents[0].name == "r1"


def test_build_agent_card_minimal() -> None:
    card = build_agent_card(
        "default",
        public_url="https://gw.example/a2a",
        config=load_a2a_config(raw={"enabled": True, "name": "TestAgent"}),
    )
    assert card["name"] == "TestAgent"
    assert card["url"] == "https://gw.example/a2a"
    assert card["protocolVersion"] == "0.3.0"
    assert card["capabilities"]["streaming"] is True
    assert isinstance(card["skills"], list) and card["skills"]


@pytest.mark.asyncio
async def test_handle_message_send_success() -> None:
    store = A2ATaskStore()
    agent = SimpleNamespace(
        run=AsyncMock(return_value="pong from holix"),
    )
    result = await handle_message_send(
        agent=agent,
        message={
            "role": "user",
            "parts": [{"kind": "text", "text": "ping"}],
            "contextId": "ctx-test",
        },
        profile="p1",
        store=store,
    )
    assert result["contextId"] == "ctx-test"
    assert result["status"]["state"] == TaskState.COMPLETED.value
    assert extract_task_text(result) == "pong from holix"
    agent.run.assert_awaited_once()
    # conversation mapped
    kwargs = agent.run.await_args.kwargs
    assert kwargs["conversation_id"] == "a2a:ctx-test"
    assert kwargs["user_input"] == "ping"

    got = get_task_public(result["id"], store=store, profile="p1")
    assert got is not None
    assert got["id"] == result["id"]


@pytest.mark.asyncio
async def test_handle_message_send_failure() -> None:
    store = A2ATaskStore()
    agent = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("boom")))
    result = await handle_message_send(
        agent=agent,
        message=A2AMessage.from_user_text("x"),
        profile="p1",
        store=store,
    )
    assert result["status"]["state"] == TaskState.FAILED.value
    assert "boom" in extract_task_text(result)


def test_cancel_task() -> None:
    store = A2ATaskStore()
    from core.a2a.models import A2ATask, A2ATaskStatus

    task = A2ATask(
        id="task_c1",
        profile="p1",
        status=A2ATaskStatus(state=TaskState.WORKING),
    )
    store.put(task)
    out = cancel_task("task_c1", store=store, profile="p1")
    assert out is not None
    assert out["status"]["state"] == TaskState.CANCELED.value


def test_extract_task_text_from_artifacts() -> None:
    text = extract_task_text(
        {
            "status": {"state": "completed"},
            "artifacts": [
                {"parts": [{"kind": "text", "text": "artifact body"}]},
            ],
        }
    )
    assert text == "artifact body"


@pytest.mark.asyncio
async def test_handle_message_stream_events() -> None:
    from core.a2a.server import handle_message_stream
    from core.agent_events import FinalResponseEvent, ThinkingEvent

    store = A2ATaskStore()

    async def _fake_run_holix(agent, user_input, conversation_id, *, stream=False, execution_mode=None):
        yield ThinkingEvent(message="planning")
        yield FinalResponseEvent(content="streamed answer")

    agent = SimpleNamespace(
        _initialized=True,
        emit=lambda e: None,
        run=AsyncMock(return_value="fallback"),
    )

    import core.a2a.server as server_mod

    # Patch run_holix import path used inside handle_message_stream
    import core.runtime.executor as executor_mod

    original = executor_mod.run_holix
    executor_mod.run_holix = _fake_run_holix  # type: ignore[assignment]
    try:
        events = []
        async for item in handle_message_stream(
            agent=agent,
            message={"role": "user", "parts": [{"kind": "text", "text": "hi"}]},
            profile="p1",
            store=store,
        ):
            events.append(item)
    finally:
        executor_mod.run_holix = original

    assert events, "expected stream events"
    assert "task" in events[0]
    assert events[0]["task"]["status"]["state"] in {"working", "submitted"}
    # should include statusUpdate and/or artifactUpdate and final completed
    kinds = set()
    for e in events:
        kinds.update(e.keys())
    assert "statusUpdate" in kinds or "artifactUpdate" in kinds
    finals = [
        e
        for e in events
        if e.get("statusUpdate", {}).get("final")
        or (
            e.get("task", {}).get("status", {}).get("state")
            in {"completed", "failed"}
        )
    ]
    assert finals
    # completed answer stored
    last_task = get_task_public(events[0]["task"]["id"], store=store, profile="p1")
    assert last_task is not None
    assert last_task["status"]["state"] == "completed"
    assert extract_task_text(last_task) == "streamed answer"
