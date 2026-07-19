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


@pytest.mark.asyncio
async def test_persist_cron_result_mirrors_to_studio_session(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    profile = "studio_cron"

    def fake_data_dir(name: str) -> Path:
        d = tmp_path / name / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(
        "core.cron.studio_notify.resolve_holix_default_data_dir",
        fake_data_dir,
    )

    job = CronJob(
        id="j-studio",
        name="Studio ping",
        task="ping",
        cron_expression="0 9 * * *",
        profile=profile,
        session_id="studio",
    )
    agent = MagicMock()
    agent.memory = None

    await persist_cron_result(
        agent,
        job,
        response="Studio cron hello",
        run_conversation_id="cron-j-studio",
    )

    path = Path(tmp_path) / profile / "data" / "studio" / "cwd" / "studio.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "Studio cron hello" in data["messages"][-1]["text"]