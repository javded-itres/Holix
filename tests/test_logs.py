"""Holix centralized logging and ``holix logs`` command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cli.main import app
from core.logging.events import append_agent_event, log_subagent_event
from core.logging.paths import LogSource, agent_events_log, discover_log_files
from core.logging.reader import parse_log_line, read_log_entries
from core.logging.rotation import rotate_file
from core.logging.setup import configure_holix_logging, set_debug_enabled
from core.logging.state import LoggingState, load_logging_state, save_logging_state
from typer.testing import CliRunner


@pytest.fixture
def holix_logs_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_path = logs / "logging.json"

    monkeypatch.setattr("cli.core.HOLIX_HOME", tmp_path)
    monkeypatch.setattr("cli.core.LOGS_DIR", logs)
    monkeypatch.setattr("core.logging.paths.HOLIX_HOME", tmp_path)
    monkeypatch.setattr("core.logging.paths.LOGS_DIR", logs)
    monkeypatch.setattr("core.logging.setup.LOGS_DIR", logs)
    monkeypatch.setattr("core.logging.paths.logging_state_path", lambda: state_path)
    monkeypatch.setattr("core.logging.state.logging_state_path", lambda: state_path)
    monkeypatch.setattr("core.logging.setup._CONFIGURED", False)
    return tmp_path


def test_logging_state_roundtrip(holix_logs_home: Path) -> None:
    save_logging_state(LoggingState(debug_enabled=True, level="DEBUG"))
    loaded = load_logging_state()
    assert loaded.debug_enabled is True
    assert loaded.level == "DEBUG"


def test_append_agent_event_jsonl(holix_logs_home: Path) -> None:
    append_agent_event("INFO", "tool finished", tool="read_file", conversation_id="c1")
    path = agent_events_log()
    assert path.exists()
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["message"] == "tool finished"
    assert line["tool"] == "read_file"


def test_parse_json_and_plain_lines(tmp_path: Path) -> None:
    json_path = tmp_path / "agent.jsonl"
    json_path.write_text(
        '{"timestamp":"2026-06-06T12:00:00+00:00","level":"ERROR","message":"boom"}\n',
        encoding="utf-8",
    )
    entry = parse_log_line(json_path.read_text().strip(), json_path)
    assert entry is not None
    assert entry.level == "ERROR"
    assert entry.message == "boom"

    plain_path = tmp_path / "holix.log"
    plain_path.write_text("2026-06-06 12:00:01 INFO     [holix] started\n", encoding="utf-8")
    plain = parse_log_line(plain_path.read_text().strip(), plain_path)
    assert plain is not None
    assert plain.level == "INFO"
    assert "started" in plain.message


def test_read_log_entries_filter_level(holix_logs_home: Path) -> None:
    append_agent_event("INFO", "info msg")
    append_agent_event("ERROR", "error msg")
    entries = read_log_entries(source=LogSource.AGENT, lines=50, level="ERROR")
    assert len(entries) == 1
    assert entries[0].message == "error msg"


def test_rotate_file_when_over_limit(holix_logs_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = holix_logs_home / "logs" / "holix.log"
    path.write_text("x" * 200, encoding="utf-8")
    monkeypatch.setattr("core.logging.rotation.settings.log_max_bytes", 100)
    monkeypatch.setattr("core.logging.rotation.settings.log_backup_count", 3)
    created = rotate_file(path)
    assert created
    assert path.read_text(encoding="utf-8") == ""
    assert created[0].exists()


def test_debug_toggle(holix_logs_home: Path) -> None:
    set_debug_enabled(True)
    assert load_logging_state().debug_enabled is True
    log_subagent_event("DEBUG", "heartbeat", subagent="worker-1")
    debug_path = holix_logs_home / "logs" / "agent.debug.jsonl"
    assert debug_path.exists()


def test_discover_log_files(holix_logs_home: Path) -> None:
    files = discover_log_files("default")
    sources = {f.source for f in files}
    assert LogSource.AGENT in sources
    assert LogSource.GATEWAY in sources


def test_cli_logs_list(holix_logs_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "list"])
    assert result.exit_code == 0
    assert "Holix logs" in result.stdout


def test_cli_logs_show(holix_logs_home: Path) -> None:
    append_agent_event("INFO", "hello from agent")
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "show", "-n", "5", "-s", "agent"])
    assert result.exit_code == 0
    assert "hello from agent" in result.stdout


def test_cli_logs_debug_status(holix_logs_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "debug", "status"])
    assert result.exit_code == 0
    assert "Debug mode" in result.stdout


def test_configure_holix_logging_idempotent(holix_logs_home: Path) -> None:
    configure_holix_logging(force=True)
    configure_holix_logging()
    assert (holix_logs_home / "logs" / "holix.log").parent.exists()