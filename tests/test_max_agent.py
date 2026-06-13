"""MAX agent bridge helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.max.bot import HelixMaxBot
from integrations.max.config import MaxSettings
from integrations.max.markdown import split_max_text, truncate_max_text
from integrations.max.models import message_id_from_response
from integrations.max.session import MaxChatSession


def test_split_max_text_chunks_long_message() -> None:
    text = "line\n" * 2000
    chunks = split_max_text(text, limit=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_truncate_max_text() -> None:
    assert truncate_max_text("abc", limit=10) == "abc"
    assert truncate_max_text("x" * 20, limit=10).endswith("…")


def test_message_id_from_response() -> None:
    assert message_id_from_response({"message": {"message_id": "mid-1"}}) == "mid-1"
    assert message_id_from_response({"message": {"body": {"mid": "42"}}}) == "42"
    assert message_id_from_response({"message": {"mid": "top-level"}}) == "top-level"
    assert message_id_from_response({"mid": "root"}) == "root"
    assert message_id_from_response({}) is None


def test_max_session_conversation_id() -> None:
    sess = MaxChatSession(user_id=7, profile="default", conversation_id="max_default_7")
    assert sess.execution_mode == "react"
    buf = sess.bump_live_buffer()
    assert buf.profile == "default"


@pytest.mark.asyncio
async def test_bot_warmup_initializes_agent_once() -> None:
    settings = MaxSettings(access_token="tok", profile="default")
    bot = HelixMaxBot(settings)
    agent = MagicMock(model="test/model")

    with patch(
        "integrations.max.bot.create_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ) as create:
        await bot.warmup()
        await bot.warmup()

    create.assert_awaited_once_with("default", bot_profile="default")
    assert bot._agent is agent