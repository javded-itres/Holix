"""Clear access-denied messages from run_terminal_command."""

from __future__ import annotations

from pathlib import Path

from core.tools.terminal import (
    _blocked_sensitive_path_access,
    _format_access_denial,
    _format_process_result,
)


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


def test_own_workspace_allowed_when_jail_off(tmp_path: Path) -> None:
    """Admin (jail off) must still be able to write into its own workspace path."""
    profile = tmp_path / "profiles" / "admin"
    workspace = profile / "workspace"
    workspace.mkdir(parents=True)
    ws = str(workspace.resolve())
    blocked, reason = _blocked_sensitive_path_access(
        f"mv /tmp/foo {ws}/bar",
        jail_enabled=False,
        workspace_root=ws,
    )
    assert not blocked, reason
    # Secrets next to workspace still blocked
    blocked, _ = _blocked_sensitive_path_access(
        f"cat {profile.resolve()}/.env",
        jail_enabled=False,
        workspace_root=ws,
    )
    assert blocked


def test_profile_tree_blocked_when_no_workspace_root() -> None:
    blocked, reason = _blocked_sensitive_path_access(
        "ls /var/lib/holix/profiles/admin/workspace",
        jail_enabled=False,
        workspace_root=None,
    )
    assert blocked
    assert "profile" in reason.lower() or "secret" in reason.lower()
