"""holix launch CLI command tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.commands.launch import app as launch_app
from core.external_cli.store import LaunchedSession
from typer.testing import CliRunner


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


@pytest.fixture
def launch_runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setattr("cli.commands.launch.ensure_launch_platform", lambda: None)
    monkeypatch.setattr("cli.commands.launch.get_current_profile", lambda: "default")
    monkeypatch.setattr(
        "cli.commands.launch.get_current_config",
        lambda: SimpleNamespace(
            providers={},
            default_provider=None,
            models_via_providers=False,
            model="test-model",
            base_url="http://localhost/v1",
            api_key="key",
            temperature=0.5,
            agent_models={},
        ),
    )
    return CliRunner()


def test_launch_claude_status(holix_home, launch_runner: CliRunner, monkeypatch) -> None:
    monkeypatch.setattr("cli.launch.cli_status.find_active_sessions_for_cli", lambda *_: [])
    result = launch_runner.invoke(launch_app, ["claude", "status"])
    assert result.exit_code == 0
    assert "holix launch claude status" in result.stdout
    assert "Claude Code" in result.stdout


def test_launch_claude_attaches_existing_session(
    holix_home, launch_runner: CliRunner, monkeypatch
) -> None:
    existing = LaunchedSession(
        session_id="abc123",
        tmux_session="holix-default-claude-dead",
        cli_id="claude",
        profile="default",
        cwd="/tmp",
        model_slot="coder",
        model_name="claude-sonnet",
        window_index=0,
        task_preview="",
        created_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        "cli.commands.launch.find_active_sessions_for_cli",
        lambda *_: [existing],
    )
    attached: list[str] = []
    monkeypatch.setattr(
        "cli.commands.launch.attach_session",
        lambda name: attached.append(name) or 0,
    )

    result = launch_runner.invoke(launch_app, ["claude"])

    assert result.exit_code == 0
    assert attached == ["holix-default-claude-dead"]
    assert "Attaching to holix-default-claude-dead" in result.stdout


def test_launch_claude_new_session_starts_and_attaches(
    holix_home, launch_runner: CliRunner, monkeypatch
) -> None:
    launched = LaunchedSession(
        session_id="new1",
        tmux_session="holix-default-claude-new1",
        cli_id="claude",
        profile="default",
        cwd="/tmp",
        model_slot="coder",
        model_name="claude-sonnet",
        window_index=0,
        task_preview="",
        created_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr("cli.commands.launch.find_active_sessions_for_cli", lambda *_: [])
    monkeypatch.setattr("cli.commands.launch.launch_cli_by_id", lambda **_kwargs: launched)
    attached: list[str] = []
    monkeypatch.setattr(
        "cli.commands.launch.attach_session",
        lambda name: attached.append(name) or 0,
    )

    result = launch_runner.invoke(launch_app, ["claude", "--new"])

    assert result.exit_code == 0
    assert attached == ["holix-default-claude-new1"]


def test_launch_claude_detach_skips_attach(
    holix_home, launch_runner: CliRunner, monkeypatch
) -> None:
    existing = LaunchedSession(
        session_id="abc123",
        tmux_session="holix-default-claude-dead",
        cli_id="claude",
        profile="default",
        cwd="/tmp",
        model_slot="coder",
        model_name="claude-sonnet",
        window_index=0,
        task_preview="",
        created_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        "cli.commands.launch.find_active_sessions_for_cli",
        lambda *_: [existing],
    )
    monkeypatch.setattr(
        "cli.commands.launch.attach_session",
        lambda _name: pytest.fail("attach_session should not be called"),
    )

    result = launch_runner.invoke(launch_app, ["claude", "--detach"])

    assert result.exit_code == 0
    assert "Active session: holix-default-claude-dead" in result.stdout