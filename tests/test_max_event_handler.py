"""MAX event handler → outbound delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import FinalResponseEvent, ToolCallResultEvent, ToolCallStartEvent
from integrations.max.event_handler import MaxEventHandler
from integrations.max.live_presenter import MaxLivePresenter
from integrations.max.session import MaxChatSession


@pytest.mark.asyncio
async def test_tool_events_enqueue_outbound_in_order() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=3356055, profile="default", conversation_id="max_default_3356055")
    session.chat_type = "dialog"
    session.reply_user_id = 3356055
    session.reply_chat_id = 201888907
    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=120)
    await presenter.start()

    handler = MaxEventHandler(presenter, approvals=MagicMock())
    handler.handle(
        ToolCallStartEvent(
            tool_name="web_search",
            tool_id="t1",
            arguments_raw='{"query": "saas agents"}',
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        ToolCallResultEvent(
            tool_name="web_search",
            tool_id="t1",
            result="found 3 articles",
            duration_ms=120.0,
            conversation_id=session.conversation_id,
        )
    )
    handler.handle(
        FinalResponseEvent(
            content="Here is the summary.",
            steps_taken=1,
            conversation_id=session.conversation_id,
        )
    )

    await presenter.drain_outbound()

    texts = [call.args[0] for call in client.send_message.await_args_list]
    # start() sends progress line first
    assert any("обрабатывает" in t for t in texts)
    assert any("🔧 web_search" in t for t in texts)
    assert any("📋 web_search" in t and "found 3 articles" in t for t in texts)
    assert any("Here is the summary." in t for t in texts)
    assert not any('{"total":' in t for t in texts)
    tool_idx = next(i for i, t in enumerate(texts) if "🔧" in t)
    result_idx = next(i for i, t in enumerate(texts) if "📋" in t)
    final_idx = next(i for i, t in enumerate(texts) if "Here is the summary." in t)
    assert tool_idx < result_idx < final_idx
    final_call = client.send_message.await_args_list[final_idx]
    assert final_call.kwargs.get("fmt") == "html"