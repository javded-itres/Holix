"""Cron delivery channel: Telegram/MAX active session, Studio new session."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.cron.delivery import (
    delivery_channel,
    pick_active_conversation,
    resolve_delivery_conversation_id,
    telegram_html_body,
    without_internal_cron_sessions,
)
from core.cron.models import CronJob
from core.cron.session_sync import persist_cron_result
from core.cron.studio_notify import open_studio_cron_session


def _job(**kwargs) -> CronJob:
    data = {
        "id": "abc123def456",
        "name": "Daily",
        "task": "summarize",
        "cron_expression": "0 9 * * *",
        "profile": "default",
    }
    data.update(kwargs)
    return CronJob(**data)


def test_channel_telegram_wins_over_session_id():
    job = _job(notify_chat_id=99, session_id="studio")
    assert delivery_channel(job) == "telegram"


def test_channel_max_and_studio():
    assert delivery_channel(_job(notify_max_user_id=7)) == "max"
    assert delivery_channel(_job(session_id="studio")) == "studio"
    assert delivery_channel(_job(session_id="studio_tab2")) == "studio"
    assert delivery_channel(_job(session_id="tui_default")) == "session"
    assert delivery_channel(_job()) == "none"


def test_pick_active_prefers_newest_timestamped_session():
    prefix = "tg_default_99"
    recent = ["tg_default_99_1710000002", "tg_default_99", "other"]
    assert pick_active_conversation(prefix, recent, fallback=prefix) == "tg_default_99_1710000002"


def test_pick_active_does_not_match_longer_chat_id():
    prefix = "tg_default_12"
    recent = ["tg_default_123", "tg_default_12"]
    assert pick_active_conversation(prefix, recent, fallback=prefix) == "tg_default_12"


def test_resolve_telegram_active_conversation():
    job = _job(notify_chat_id=55, session_id="tg_default_55")
    cid = resolve_delivery_conversation_id(
        job,
        recent_ids=["tg_default_55_9999999999", "cron-abc"],
    )
    assert cid == "tg_default_55_9999999999"


def test_telegram_html_has_newlines_not_br():
    html = telegram_html_body("Cron · Daily", "line1\nline2 <ok>")
    assert "<br>" not in html
    assert "\n\n" in html
    assert "&lt;ok&gt;" in html
    assert "<b>" in html


def test_without_internal_cron_sessions():
    rows = [
        {"conversation_id": "tg_default_1"},
        {"conversation_id": "cron-abc123def456"},
        {"conversation_id": "max_default_2"},
    ]
    out = without_internal_cron_sessions(rows)
    assert [r["conversation_id"] for r in out] == ["tg_default_1", "max_default_2"]


def test_open_studio_cron_session_is_new_file(tmp_path: Path, monkeypatch) -> None:
    profile = "cron_studio_new"

    def fake_data_dir(name: str) -> Path:
        d = tmp_path / name / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(
        "core.cron.studio_notify.resolve_holix_default_data_dir",
        fake_data_dir,
    )
    job = _job(profile=profile, session_id="studio")
    cid = open_studio_cron_session(job, "Пора работать!")
    assert cid is not None
    assert cid.startswith("studio_cron_")
    path = tmp_path / profile / "data" / "studio" / "cwd" / f"{cid}.json"
    assert path.is_file()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    classes = [m["cls"] for m in data["messages"]]
    assert "user" in classes
    assert "assistant" in classes
    assert "Пора работать" in data["messages"][-1]["text"]
    # Must not append into the default studio.json tab.
    assert not (tmp_path / profile / "data" / "studio" / "cwd" / "studio.json").is_file()


@pytest.mark.asyncio
async def test_persist_telegram_mirrors_to_active_session():
    job = _job(notify_chat_id=42, session_id="tg_default_42")
    agent = MagicMock()
    agent.memory = MagicMock()
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()

    await persist_cron_result(
        agent,
        job,
        response="Done.",
        run_conversation_id="cron-abc123def456",
        recent_ids=["tg_default_42_1710000001"],
    )
    targets = [c.args[0] for c in agent.memory.save_message.await_args_list]
    assert "cron-abc123def456" in targets
    assert "tg_default_42_1710000001" in targets
