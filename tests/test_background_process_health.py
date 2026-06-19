"""Tests for background process log health checks."""

from __future__ import annotations

import pytest
from core.runtime.background_process_health import (
    build_health_report,
    scan_log_for_errors,
    tail_log_file,
)


def test_scan_log_detects_traceback() -> None:
    log = "INFO: starting\nTraceback (most recent call last):\n  File \"app.py\"\nModuleNotFoundError: No module named 'foo'"
    errors = scan_log_for_errors(log)
    assert errors
    assert any("ModuleNotFoundError" in e for e in errors)


def test_scan_log_detects_npm_err() -> None:
    errors = scan_log_for_errors("npm ERR! code ELIFECYCLE\nnpm ERR! errno 1")
    assert errors


def test_scan_log_detects_npm_error_lowercase() -> None:
    log = (
        "npm error code ENOENT\n"
        "npm error path /tmp/project/package.json\n"
        "npm error enoent Could not read package.json"
    )
    errors = scan_log_for_errors(log)
    assert errors
    assert any("npm error" in e.lower() for e in errors)


def test_scan_log_ignores_clean_startup() -> None:
    log = "INFO: Uvicorn running on http://127.0.0.1:8000\nApplication startup complete."
    assert scan_log_for_errors(log) == []


def test_build_health_report_crashed() -> None:
    report = build_health_report(
        process_id="proc_1",
        label="api",
        pid=99,
        log_path="/tmp/x.log",
        running=False,
        exit_code=1,
        log_tail="Traceback\nValueError: bad",
    )
    assert report.status == "crashed"
    assert not report.healthy
    assert report.error_snippets


def test_build_health_report_exited_ok() -> None:
    report = build_health_report(
        process_id="proc_1",
        label="echo",
        pid=99,
        log_path="/tmp/x.log",
        running=False,
        exit_code=0,
        log_tail="hello\n",
    )
    assert report.status == "exited"
    assert not report.healthy
    assert not report.error_snippets


def test_build_health_report_port_in_use() -> None:
    report = build_health_report(
        process_id="proc_1",
        label="api",
        pid=99,
        log_path="/tmp/x.log",
        running=False,
        exit_code=1,
        log_tail="Error: listen EADDRINUSE: address already in use :::8000",
    )
    assert report.status == "port_in_use"
    assert not report.healthy
    assert "EADDRINUSE" in report.recommendation or "port" in report.recommendation.lower()


def test_build_health_report_healthy() -> None:
    report = build_health_report(
        process_id="proc_1",
        label="api",
        pid=99,
        log_path="/tmp/x.log",
        running=True,
        exit_code=None,
        log_tail="Uvicorn running on http://127.0.0.1:8000",
    )
    assert report.status == "healthy"
    assert report.healthy


def test_tail_log_file(tmp_path) -> None:
    log = tmp_path / "out.log"
    log.write_text("line1\nline2\nERROR: boom\n", encoding="utf-8")
    tail = tail_log_file(log, max_lines=10)
    assert "ERROR: boom" in tail


@pytest.mark.asyncio
async def test_registry_check_health_crashed(tmp_path) -> None:
    from unittest.mock import MagicMock, patch

    from core.runtime.background_process import BackgroundProcessRegistry

    reg = BackgroundProcessRegistry()
    popen = MagicMock()
    popen.pid = 42
    popen.poll.return_value = 1

    log_dir = tmp_path / ".holix" / "process-logs"
    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.is_process_alive", return_value=False),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        rec = await reg.start(
            command="false",
            label="fail",
            conversation_id="c1",
            profile="p1",
        )
        log_file = log_dir / f"{rec.process_id}.log"
        log_file.write_text(
            "Traceback (most recent call last):\nModuleNotFoundError: no such module\n",
            encoding="utf-8",
        )

        report = await reg.check_health(
            process_id=rec.process_id,
            profile="p1",
            conversation_id="c1",
            wait_s=0,
        )

    assert report.status == "crashed"
    assert not report.healthy
    assert report.error_snippets