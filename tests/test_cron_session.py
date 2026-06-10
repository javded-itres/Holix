"""Cron result persistence into conversations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.cron.models import CronJob
from core.cron.session_sync import cron_session_label, format_cron_summary, persist_cron_result


def test_cron_session_label():
    assert cron_session_label("cron-status-check-001") == "cron: status-check-001"
    assert cron_session_label("tui_default") == "tui_default"


def test_format_cron_summary():
    job = CronJob(id="j1", name="Daily", task="t", cron_expression="0 9 * * *")
    text = format_cron_summary(job, "All good")
    assert "Daily" in text
    assert "All good" in text


@pytest.mark.asyncio
async def test_persist_cron_result_mirrors_to_session():
    job = CronJob(
        id="j1",
        name="Daily",
        task="t",
        cron_expression="0 9 * * *",
        session_id="tui_default",
    )
    agent = MagicMock()
    agent.memory = MagicMock()
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()

    stored = await persist_cron_result(
        agent,
        job,
        response="Done.",
        run_conversation_id="cron-j1",
    )
    assert stored == "Done."
    assert agent.memory.save_message.await_count == 2
    calls = [c.args[0] for c in agent.memory.save_message.await_args_list]
    assert "cron-j1" in calls
    assert "tui_default" in calls


@pytest.mark.asyncio
async def test_persist_skips_duplicate_assistant():
    job = CronJob(id="j1", name="X", task="t", cron_expression="0 * * * *")
    agent = MagicMock()
    agent.memory = MagicMock()
    agent.memory.get_conversation = AsyncMock(
        return_value=[{"role": "assistant", "content": "Same"}]
    )
    agent.memory.save_message = AsyncMock()

    await persist_cron_result(
        agent,
        job,
        response="Same",
        run_conversation_id="cron-j1",
    )
    agent.memory.save_message.assert_not_awaited()