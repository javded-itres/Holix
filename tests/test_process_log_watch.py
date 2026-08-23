"""Messenger live tail of background process logs."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.runtime.background_process import (
    BackgroundProcessRecord,
    get_background_process_registry,
)
from integrations.messenger.process_log_watch import (
    format_process_log_watch,
    load_process_record,
    process_log_tail,
)


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.runtime.background_process._registry",
        None,
        raising=False,
    )


def _record(tmp_path: Path, *, running: bool = True) -> BackgroundProcessRecord:
    log = tmp_path / "proc.log"
    log.write_text("boot\nready on http://127.0.0.1:8000\n", encoding="utf-8")
    rec = BackgroundProcessRecord(
        process_id="proc_logs",
        label="api",
        command="uvicorn main:app",
        pid=4242,
        conversation_id="tg_1",
        profile="admin",
        log_path=str(log),
    )
    rec._popen = object() if running else None
    return rec


def test_format_process_log_watch_includes_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _record(tmp_path)
    monkeypatch.setattr(
        "core.runtime.background_process.is_process_alive",
        lambda _pid: True,
    )
    text = format_process_log_watch(rec, html=False, locale="en")
    assert "api" in text
    assert "4242" in text
    assert "ready on http://127.0.0.1:8000" in text
    html = format_process_log_watch(rec, html=True, locale="ru")
    assert "<pre>" in html
    assert "ready on" in html


def test_format_process_log_watch_gone() -> None:
    html = format_process_log_watch(None, html=True, locale="ru")
    assert "недоступен" in html


def test_load_process_record_roundtrip(tmp_path: Path) -> None:
    rec = _record(tmp_path)
    get_background_process_registry()._records[rec.process_id] = rec
    assert load_process_record("proc_logs") is rec
    assert process_log_tail(rec).endswith("ready on http://127.0.0.1:8000")


def test_telegram_process_keyboard_has_logs_and_stop() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import background_process_stop_keyboard

    kb = background_process_stop_keyboard("deadbeef", locale="ru")
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any("логи" in t.lower() for t in texts)
    assert any("останов" in t.lower() for t in texts)
    assert "hx:pl:deadbeef" in data
    assert "hx:ps:deadbeef" in data
