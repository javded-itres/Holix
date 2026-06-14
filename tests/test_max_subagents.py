"""MAX + sub-agent interaction (non-blocking like Telegram)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.security.confirmation import ConfirmationChoice
from core.subagents.interaction import SubAgentInteractionBridge
from integrations.max.bot import HelixMaxBot
from integrations.max.config import MaxSettings
from integrations.max.host import MaxHost
from integrations.max.session import MaxChatSession


@pytest.mark.asyncio
async def test_confirmation_callback_does_not_wait_on_run_lock() -> None:
    """Sub-agent/main confirmations must resolve while agent run is in progress."""
    client = MagicMock()
    client.answer_callback = AsyncMock()
    client.delete_message = AsyncMock()
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.reply_user_id = 1
    agent = MagicMock()
    bridge = SubAgentInteractionBridge(agent)
    agent.subagents = MagicMock()
    agent.subagents.interactions = bridge
    session.agent = agent

    loop = asyncio.get_running_loop()
    gate = loop.create_future()

    async def fake_run(_user_input: str) -> None:
        await gate

    host = MaxHost(client, session)
    host._run_agent = fake_run  # type: ignore[method-assign]
    host._start_agent_run("delegate task")

    await asyncio.sleep(0.05)
    assert not gate.done()

    request_id = "cfm-test-1"
    confirm_future = asyncio.create_task(
        bridge.handle_ipc_confirmation(
            "coder-1",
            {
                "request_id": request_id,
                "tool_name": "write_file",
                "arguments": {"path": "a.py"},
                "risk_level": "high",
                "reason": "write",
            },
        )
    )
    await asyncio.sleep(0.05)

    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb-1",
            "payload": f"cfm:{request_id}:1",
            "user": {"user_id": 1},
            "message": {"recipient": {"chat_id": 99}},
        },
    }

    bot = HelixMaxBot(MaxSettings(access_token="tok", allowed_user_ids=[1]))
    with patch.object(bot, "_allowed", return_value=True):
        with patch.object(bot, "_get_session", new_callable=AsyncMock, return_value=session):
            await bot._handle_message_callback(client, update)

    choice = await asyncio.wait_for(confirm_future, timeout=1.0)
    assert choice == ConfirmationChoice.ALLOW_ONCE.value
    gate.set_result(None)


@pytest.mark.asyncio
async def test_subagent_reply_while_agent_run_in_progress() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    agent = MagicMock()
    bridge = SubAgentInteractionBridge(agent)
    agent.subagents = MagicMock()
    agent.subagents.interactions = bridge
    session.agent = agent

    loop = asyncio.get_running_loop()
    gate = loop.create_future()

    async def fake_run(_user_input: str) -> None:
        await gate

    host = MaxHost(client, session)
    host._run_agent = fake_run  # type: ignore[method-assign]
    host._start_agent_run("wait for subagent")

    await asyncio.sleep(0.05)
    question_task = asyncio.create_task(
        bridge.handle_ipc_question(
            "researcher-1",
            {"request_id": "subq-1", "question": "Which API?", "context": ""},
        )
    )
    await asyncio.sleep(0.05)

    await host.handle_user_text("/subagent-reply researcher-1 use REST")

    answer = await asyncio.wait_for(question_task, timeout=1.0)
    assert answer == "use REST"
    gate.set_result(None)

    client.send_message.assert_awaited()
    sent = client.send_message.await_args_list[-1].args[0]
    assert "researcher-1" in sent