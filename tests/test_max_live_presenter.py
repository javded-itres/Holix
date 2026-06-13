"""MAX live presenter delivery guarantees."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.max.live_presenter import MaxLivePresenter
from integrations.max.session import MaxChatSession


@pytest.mark.asyncio
async def test_deliver_final_answer_only_once() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    presenter = MaxLivePresenter(client, session)

    await presenter.deliver_final_answer("**hello** world")
    await presenter.deliver_final_answer("**hello** world")

    assert client.send_message.await_count == 1
    assert client.send_message.await_args_list[0].kwargs.get("fmt") == "html"
    sent = client.send_message.await_args_list[0].args[0]
    assert "<b>hello</b>" in sent
    assert "**hello**" not in sent


@pytest.mark.asyncio
async def test_finish_delivers_full_content_not_preview_placeholder() -> None:
    client = MagicMock()
    client.edit_message = AsyncMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.bump_live_buffer()
    session.live_message_id = "live-1"
    session.live_buffer.set_answer("✓ Done — full answer below.")
    session.live_buffer.mark_done()

    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=60)
    presenter.note_final_content("This is the real final answer from the agent.")
    await presenter.finish()

    assert client.send_message.await_count == 1
    sent = client.send_message.await_args_list[0].args[0]
    assert "real final answer" in sent
    assert client.send_message.await_args_list[0].kwargs.get("fmt") == "html"


@pytest.mark.asyncio
async def test_deliver_final_answer_not_marked_when_all_sends_fail() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(side_effect=Exception("api down"))
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    presenter = MaxLivePresenter(client, session)

    await presenter.deliver_final_answer("**hello** world")

    assert presenter.final_delivered is False


def test_done_posts_answer_separately_not_in_live_card() -> None:
    from core.presenters.live_buffer import LiveTranscriptBuffer
    from integrations.max.render import buffer_to_max_html

    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.publish_answer_separately = True
    buf.result_posted_separately = True
    buf.set_answer("**Secret final**")
    buf.mark_done()
    html = buffer_to_max_html(buf)
    assert "<b>Secret final</b>" not in html
    assert "отдельным сообщением" in html


@pytest.mark.asyncio
async def test_progress_snapshot_edits_live_message() -> None:
    client = MagicMock()
    client.edit_message = AsyncMock()
    client.send_message = AsyncMock()
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.bump_live_buffer()
    session.live_message_id = "live-1"
    session.live_buffer.add_note("working")

    presenter = MaxLivePresenter(client, session)
    presenter._progress_message_id = "live-1"
    presenter._buffer = session.live_buffer

    await presenter._maybe_send_progress_snapshot()

    client.edit_message.assert_awaited_once()
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_finish_reports_agent_error_message() -> None:
    client = MagicMock()
    client.send_message = AsyncMock(return_value={"message": {"body": {"mid": "m1"}}})
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.bump_live_buffer()
    session.live_buffer.mark_error("LLM connection refused")

    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=60)
    await presenter.finish()

    assert client.send_message.await_count == 1
    sent = client.send_message.await_args_list[0].args[0]
    assert "LLM connection refused" in sent
    assert "unknown error" not in sent.lower()
    assert presenter.final_delivered is True


@pytest.mark.asyncio
async def test_finish_skips_placeholder_when_no_final_content() -> None:
    client = MagicMock()
    client.edit_message = AsyncMock()
    client.send_message = AsyncMock()
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.bump_live_buffer()
    session.live_message_id = "live-1"
    session.live_buffer.set_answer("✓ Done — full answer below.")
    session.live_buffer.mark_done()

    presenter = MaxLivePresenter(client, session, heartbeat_interval_s=60)
    await presenter.finish()

    client.send_message.assert_not_awaited()