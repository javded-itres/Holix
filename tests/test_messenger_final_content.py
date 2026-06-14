"""Messenger final answer normalization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import (
    AssistantDeltaEvent,
    FinalResponseEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.presenters.final_content import (
    MESSENGER_EMPTY_FINAL_RU,
    is_placeholder_final,
    resolve_messenger_final_content,
)
from integrations.max.event_handler import MaxEventHandler
from integrations.max.live_presenter import MaxLivePresenter
from integrations.max.session import MaxChatSession


def test_placeholder_detection() -> None:
    assert is_placeholder_final("No response generated")
    assert is_placeholder_final("")
    assert not is_placeholder_final("Готово")


def test_resolve_prefers_streamed_over_placeholder() -> None:
    text = resolve_messenger_final_content(
        "No response generated",
        streamed_answer="Ответ из стрима",
    )
    assert text == "Ответ из стрима"


def test_resolve_falls_back_to_tool_result() -> None:
    text = resolve_messenger_final_content(
        "No response generated",
        last_tool_result="Результат web_search",
    )
    assert text == "Результат web_search"


def test_resolve_prefers_subagent_response_from_recent_tools() -> None:
    import json

    recent = [
        {
            "name": "wait_subagent_result",
            "full_result": json.dumps(
                {
                    "job_id": "researcher",
                    "success": True,
                    "response": "Итог исследования рынка.",
                },
                ensure_ascii=False,
            ),
        }
    ]
    text = resolve_messenger_final_content(
        "No response generated",
        last_tool_result='{"status":"spawned"}',
        recent_tool_results=recent,
    )
    assert "Итог исследования рынка" in text


def test_resolve_empty_message() -> None:
    assert resolve_messenger_final_content("") == MESSENGER_EMPTY_FINAL_RU


@pytest.mark.asyncio
async def test_max_final_placeholder_uses_tool_result() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=1, profile="admin", conversation_id="max_admin_1")
    session.chat_type = "dialog"
    session.reply_user_id = 1
    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=120)
    await presenter.start()
    handler = MaxEventHandler(presenter, approvals=MagicMock())

    handler.handle(
        ToolCallResultEvent(
            tool_name="web_search",
            tool_id="t1",
            result="Найдено 3 статьи про SaaS",
            duration_ms=50.0,
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        FinalResponseEvent(
            content="No response generated",
            steps_taken=1,
            conversation_id=session.conversation_id,
        )
    )
    await presenter.drain_outbound()

    texts = [call.args[0] for call in client.send_message.await_args_list]
    assert any("Найдено 3 статьи про SaaS" in t for t in texts)
    assert not any(t.strip() == "No response generated" for t in texts)


@pytest.mark.asyncio
async def test_max_tool_preamble_not_used_as_final() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=3, profile="admin", conversation_id="max_admin_3")
    session.chat_type = "dialog"
    session.reply_user_id = 3
    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=120)
    await presenter.start()
    handler = MaxEventHandler(presenter, approvals=MagicMock())

    handler.handle(
        AssistantDeltaEvent(
            content="Давайте посмотрю…",
            accumulated="Давайте посмотрю…",
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        ToolCallStartEvent(
            tool_name="list_subagents",
            tool_id="t1",
            arguments_raw="{}",
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        ToolCallResultEvent(
            tool_name="list_subagents",
            tool_id="t1",
            result="Нет активных субагентов",
            duration_ms=10.0,
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        FinalResponseEvent(
            content="No response generated",
            steps_taken=2,
            conversation_id=session.conversation_id,
        )
    )
    await presenter.drain_outbound()

    texts = [call.args[0] for call in client.send_message.await_args_list]
    assert not any("Давайте посмотрю" in t for t in texts)
    assert any("Нет активных субагентов" in t for t in texts)


@pytest.mark.asyncio
async def test_max_streaming_delta_used_when_final_empty() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=2, profile="admin", conversation_id="max_admin_2")
    session.chat_type = "dialog"
    session.reply_user_id = 2
    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=120)
    await presenter.start()
    handler = MaxEventHandler(presenter, approvals=MagicMock())

    handler.handle(
        AssistantDeltaEvent(
            content=" часть",
            accumulated="Итоговый ответ",
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        FinalResponseEvent(
            content="No response generated",
            steps_taken=1,
            conversation_id=session.conversation_id,
        )
    )
    await presenter.drain_outbound()

    texts = [call.args[0] for call in client.send_message.await_args_list]
    assert any("Итоговый ответ" in t for t in texts)