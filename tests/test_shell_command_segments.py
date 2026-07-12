"""Tests for compound shell command parsing in the safety whitelist."""

from __future__ import annotations

from core.security.safety import (
    command_needs_shell,
    command_whitelist,
    iter_shell_command_segments,
)


def test_command_needs_shell_detects_operators() -> None:
    assert not command_needs_shell("ls -la")
    assert command_needs_shell("mkdir -p a && cd a")
    assert command_needs_shell("echo hi > out.txt")
    assert command_needs_shell("ls | head")


def test_iter_shell_command_segments_splits_compound_commands() -> None:
    segments = iter_shell_command_segments("mkdir -p shop && cd shop && uv add fastapi")
    assert segments == ["mkdir -p shop", "cd shop", "uv add fastapi"]


def test_iter_shell_command_segments_splits_pipes_and_redirects() -> None:
    segments = iter_shell_command_segments("ls -la | head -5 > out.txt")
    assert "ls -la" in segments
    assert "head -5" in segments


def test_whitelist_allows_redirect_and_chain() -> None:
    ok, reason = command_whitelist.is_command_allowed(
        "mkdir -p app && echo 'print(1)' > app/main.py"
    )
    assert ok, reason