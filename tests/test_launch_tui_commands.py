"""TUI /launch slash command handlers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cli.shared.commands.launch_commands import run_launch_command


class FakeHost:
    def __init__(self) -> None:
        self.profile = "default"
        self.lines: list[str] = []

    def transcript_write(self, content: object) -> None:
        self.lines.append(str(content))


@pytest.mark.asyncio
async def test_launch_claude_command_starts_cli() -> None:
    host = FakeHost()
    fake_session = {
        "session_id": "s1",
        "tmux_session": "holix-default-claude-s1",
        "cli_id": "claude",
        "model_name": "coder",
    }
    with patch(
        "cli.shared.commands.launch_commands.launch_external_cli",
        return_value=fake_session,
    ):
        await run_launch_command(host, '/launch claude -t "frontend"')

    joined = "\n".join(host.lines)
    assert "claude" in joined
    assert "holix-default-claude-s1" in joined


@pytest.mark.asyncio
async def test_launch_sessions_lists_active() -> None:
    host = FakeHost()
    with patch(
        "cli.shared.commands.launch_commands.list_sessions",
        return_value=[
            {
                "session_id": "s9",
                "cli_id": "claude",
                "tmux_session": "holix-default-claude-s9",
                "window_index": 0,
                "model_name": "coder",
                "model_slot": "coder",
            }
        ],
    ):
        await run_launch_command(host, "/launch sessions")

    assert any("s9" in line for line in host.lines)