"""Tests for TUI background process viewer helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cli.tui.modals.process_viewer import (
    format_process_log_text,
    format_process_meta,
    resolve_background_process_record,
)
from core.runtime.background_process import BackgroundProcessRecord, get_background_process_registry


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.runtime.background_process._registry",
        None,
        raising=False,
    )


def _record(
    *,
    process_id: str = "proc_test",
    log_path: str = "",
) -> BackgroundProcessRecord:
    return BackgroundProcessRecord(
        process_id=process_id,
        label="api",
        command="uvicorn main:app",
        pid=4242,
        conversation_id="tui_default",
        profile="default",
        log_path=log_path,
    )


def test_resolve_background_process_record_by_id() -> None:
    registry = get_background_process_registry()
    rec = _record(process_id="proc_abc")
    registry._records["proc_abc"] = rec

    host = MagicMock(profile="default", conversation_id="tui_default")
    host._background_process_id = None

    found = resolve_background_process_record(host, process_id="proc_abc")
    assert found is rec


def test_format_process_log_text_reads_tail(tmp_path: Path) -> None:
    log_file = tmp_path / "proc_test.log"
    log_file.write_text("line one\nline two\n", encoding="utf-8")
    rec = _record(log_path=str(log_file))

    body = format_process_log_text(rec, lang="en")
    assert "line two" in body


def test_format_process_meta_running(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _record()
    monkeypatch.setattr(
        "core.runtime.background_process.is_process_alive",
        lambda _pid: True,
    )
    meta = format_process_meta(rec, lang="en")
    assert "api" in meta
    assert "4242" in meta
    assert "uvicorn main:app" in meta
    assert "running" in meta


def test_format_process_log_text_empty_when_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _record(log_path=str(tmp_path / "missing.log"))
    rec._popen = None
    monkeypatch.setattr(
        "core.runtime.background_process.is_process_alive",
        lambda _pid: False,
    )

    body = format_process_log_text(rec, lang="en")
    assert "no log output" in body.lower()