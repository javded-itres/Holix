"""Cron results mirrored into Studio chat history."""

from __future__ import annotations

import json
from pathlib import Path

from core.cron.models import CronJob
from core.cron.studio_notify import mirror_cron_to_studio_chat


def test_mirror_cron_to_studio_chat_opens_new_session(tmp_path: Path, monkeypatch) -> None:
    profile = "cron_studio"

    def fake_data_dir(name: str) -> Path:
        d = tmp_path / name / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(
        "core.cron.studio_notify.resolve_holix_default_data_dir",
        fake_data_dir,
    )

    job = CronJob(
        id="job1",
        name="Reminder",
        task="say hi",
        cron_expression="*/5 * * * *",
        profile=profile,
        session_id="studio",
    )
    cid = mirror_cron_to_studio_chat(job, "Пора работать!")
    assert cid and cid.startswith("studio_cron_job1_")

    path = tmp_path / profile / "data" / "studio" / "cwd" / f"{cid}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["conversation_id"] == cid
    assert data["messages"][-1]["cls"] == "assistant"
    assert "Пора работать" in data["messages"][-1]["text"]
    assert "[Cron · Reminder]" in data["messages"][-1]["text"]
    assert not (tmp_path / profile / "data" / "studio" / "cwd" / "studio.json").exists()
