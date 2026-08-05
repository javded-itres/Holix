"""Stopped process history survives prune (reboot knowledge)."""

from __future__ import annotations

from pathlib import Path

from core.runtime import background_process_store as store


def test_prune_keeps_stopped_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    profile = "admin"
    # Fake running then dead
    live = {
        "process_id": "p1",
        "label": "bot",
        "command": "python bot.py",
        "pid": 999999,  # not alive
        "conversation_id": "c1",
        "profile": profile,
        "chat_id": None,
        "log_path": "/tmp/x.log",
        "started_at": 1.0,
        "status": "running",
        "stopped_at": None,
    }
    path = store.profile_process_index_path(profile)
    path.parent.mkdir(parents=True)
    store._write_index(profile, [live])  # noqa: SLF001

    alive_out = store.prune_dead_records(profile, is_alive=lambda _pid: False)
    assert alive_out == []
    rows = store.load_index(profile)
    assert len(rows) == 1
    assert rows[0]["status"] == "stopped"
    assert rows[0]["command"] == "python bot.py"
