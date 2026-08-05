"""Clear access-denied messages from run_terminal_command."""

from __future__ import annotations

from core.tools.terminal import _format_access_denial, _format_process_result


def test_sudo_denied_is_human_readable() -> None:
    msg = _format_process_result(
        returncode=1,
        output="",
        error="sudo: I'm sorry holix. I'm afraid I can't do that",
    )
    assert "нет прав" in msg.lower() or "прав" in msg
    assert "sudo" in msg.lower() or "root" in msg.lower()
    assert "STDOUT" in msg


def test_permission_denied_path() -> None:
    msg = _format_access_denial(
        returncode=1,
        output="",
        error="bash: /root/secret: Permission denied",
    )
    assert msg is not None
    assert "прав" in msg.lower() or "permission" in msg.lower()
