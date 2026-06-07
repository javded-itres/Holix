"""Sub-agent question / confirmation bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.security.confirmation import ConfirmationChoice
from core.subagents.interaction import (
    SubAgentInteractionBridge,
    resolve_any_confirmation,
    try_route_subagent_reply,
)


def _bridge() -> SubAgentInteractionBridge:
    parent = MagicMock()
    parent.events = MagicMock()
    return SubAgentInteractionBridge(parent, confirmation_timeout=5)


@pytest.mark.asyncio
async def test_ipc_confirmation_resolves_via_bridge() -> None:
    bridge = _bridge()

    async def approve() -> None:
        await asyncio.sleep(0.05)
        pending = list(bridge._pending_confirmations.keys())
        assert pending
        bridge.resolve_confirmation(pending[0], ConfirmationChoice.ALLOW_ONCE)

    asyncio.create_task(approve())
    choice = await bridge.handle_ipc_confirmation(
        "researcher-2",
        {
            "request_id": "subcfm_test",
            "tool_name": "write_file",
            "arguments": {"path": "a.txt"},
            "risk_level": "medium",
            "reason": "File write",
        },
    )
    assert choice == ConfirmationChoice.ALLOW_ONCE.value


@pytest.mark.asyncio
async def test_question_reply_routes_to_subagent() -> None:
    bridge = _bridge()
    parent = bridge._parent
    parent.subagents = MagicMock()
    parent.subagents.interactions = bridge

    async def answer() -> None:
        await asyncio.sleep(0.05)
        bridge.resolve_question_for_subagent("coder", "use pytest")

    asyncio.create_task(answer())
    result = await bridge.handle_ipc_question(
        "coder",
        {"request_id": "subq_test", "question": "Which test runner?"},
    )
    assert result == "use pytest"


@pytest.mark.asyncio
async def test_try_route_subagent_reply_explicit() -> None:
    bridge = _bridge()
    parent = bridge._parent
    parent.subagents = MagicMock()
    parent.subagents.interactions = bridge

    loop = asyncio.get_running_loop()
    bridge._pending_questions["subq_1"] = loop.create_future()
    bridge._question_meta = {
        "subq_1": {"subagent_name": "coder", "question": "framework?"},
    }

    handled, feedback = try_route_subagent_reply(parent, "/subagent-reply coder pytest")
    assert handled
    assert "reply sent" in feedback


def test_resolve_any_confirmation_prefers_bridge() -> None:
    bridge = _bridge()
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    bridge._pending_confirmations["subcfm_x"] = future

    agent = MagicMock()
    agent.subagents.interactions = bridge
    agent.tools._action_guard = None

    assert resolve_any_confirmation(agent, ConfirmationChoice.DENY)
    assert future.done()
    assert future.result() == ConfirmationChoice.DENY