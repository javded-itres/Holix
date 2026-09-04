"""Tests for workspace-scoped terminal command blocking."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.security.workspace_command_guard import (
    command_escapes_workspace,
    references_holix_profiles,
    validate_workspace_command,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "profile_workspace"
    root.mkdir()
    (root / ".env").write_text("IN_WORKSPACE=1\n", encoding="utf-8")
    outside = tmp_path / "outside.env"
    outside.write_text("SECRET=1\n", encoding="utf-8")
    return root


def test_references_holix_profiles() -> None:
    assert references_holix_profiles("cat ~/.holix/profiles/alice/.env")
    assert references_holix_profiles("ls .holix/profiles/bob")


def test_references_holix_profiles_allows_under_workspace(tmp_path: Path) -> None:
    """Absolute workspace paths under .../profiles/<name>/workspace must not be blocked."""
    profile = tmp_path / "profiles" / "invite-user"
    workspace = profile / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (profile / "config.yaml").write_text("profile_name: invite-user\n", encoding="utf-8")

    abs_ws = str(workspace.resolve())
    assert not references_holix_profiles(f"cd {abs_ws}", allow_under=workspace)
    assert not references_holix_profiles(
        f"docker compose -f {abs_ws}/docker-compose.yml build",
        allow_under=workspace,
    )
    assert not references_holix_profiles(f"ls {abs_ws}/user_catalog", allow_under=workspace)

    # Secrets / non-workspace profile paths still blocked
    assert references_holix_profiles(
        f"cat {profile.resolve()}/config.yaml",
        allow_under=workspace,
    )
    assert references_holix_profiles("cat ~/.holix/profiles/alice/.env", allow_under=workspace)


def test_allows_absolute_path_under_workspace_profile_tree(tmp_path: Path) -> None:
    profile = tmp_path / "profiles" / "invite-pavel"
    workspace = profile / "workspace"
    workspace.mkdir(parents=True)
    abs_ws = str(workspace.resolve())

    allowed, reason = validate_workspace_command(f"cd {abs_ws}", workspace)
    assert allowed, reason
    allowed, reason = validate_workspace_command(
        f"docker compose -f {abs_ws}/docker-compose.yml build",
        workspace,
    )
    assert allowed, reason
    allowed, reason = validate_workspace_command("docker compose build", workspace)
    assert allowed, reason


def test_blocks_profile_secrets_outside_workspace(tmp_path: Path) -> None:
    profile = tmp_path / "profiles" / "invite-pavel"
    workspace = profile / "workspace"
    workspace.mkdir(parents=True)
    config = profile / "config.yaml"
    config.write_text("x: 1\n", encoding="utf-8")

    allowed, reason = validate_workspace_command(f"cat {config.resolve()}", workspace)
    assert not allowed
    assert reason


def test_blocks_parent_traversal(workspace: Path) -> None:
    blocked, _ = command_escapes_workspace("cat ../outside.env", workspace)
    assert blocked


def test_blocks_absolute_outside_workspace(workspace: Path) -> None:
    outside = workspace.parent / "outside.env"
    blocked, reason = command_escapes_workspace(f"cat {outside}", workspace)
    assert blocked
    assert "outside" in reason.lower() or "workspace" in reason.lower()


def test_allows_workspace_relative_commands(workspace: Path) -> None:
    allowed, _ = validate_workspace_command("ls -la", workspace)
    assert allowed
    allowed, _ = validate_workspace_command("cat .env", workspace)
    assert allowed


def test_allows_dev_null_redirects(workspace: Path) -> None:
    """2>/dev/null and >/dev/null are normal shell, not a workspace escape."""
    for cmd in (
        "true >/dev/null",
        "true 2>/dev/null",
        "cmd arg 2>/dev/null",
        "python -c 'print(1)' >/dev/null 2>&1",
        "test -f foo || echo missing >/dev/null",
    ):
        allowed, reason = validate_workspace_command(cmd, workspace)
        assert allowed, f"{cmd!r} blocked: {reason}"


def test_still_blocks_real_outside_paths(workspace: Path) -> None:
    allowed, reason = validate_workspace_command("cat /etc/passwd", workspace)
    assert not allowed
    assert "outside" in reason.lower() or "workspace" in reason.lower()


def test_blocks_listing_root(workspace: Path) -> None:
    blocked, _ = command_escapes_workspace("ls -la /", workspace)
    assert blocked


def _fake_linked_worktree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Clone + linked worktree under a Holix profiles tree (no real git needed)."""
    profile = tmp_path / "profiles" / "pavel_it-rs.ru"
    clone = profile / "workspace" / "projects" / "app"
    git_dir = clone / ".git"
    wt_git = git_dir / "worktrees" / "change-1"
    wt_git.mkdir(parents=True)
    (git_dir / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    worktree = clone / ".holix" / "worktrees" / "change-1"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {wt_git.resolve()}\n", encoding="utf-8")
    return clone, worktree, git_dir


def test_worktree_jail_allows_clone_git_dir(tmp_path: Path) -> None:
    clone, worktree, git_dir = _fake_linked_worktree(tmp_path)
    git_dir_s = str(git_dir.resolve())
    clone_s = str(clone.resolve())
    wt_s = str(worktree.resolve())

    allowed, reason = validate_workspace_command("git merge main", worktree)
    assert allowed, reason
    allowed, reason = validate_workspace_command(
        f"export GIT_DIR={git_dir_s}/worktrees/change-1",
        worktree,
    )
    assert allowed, reason
    allowed, reason = validate_workspace_command(
        f"git --git-dir={git_dir_s} merge main",
        worktree,
    )
    assert allowed, reason
    allowed, reason = validate_workspace_command(f"cat {git_dir_s}/config", worktree)
    assert allowed, reason

    # Clone working tree (main checkout) stays blocked
    allowed, _ = validate_workspace_command(f"cd {clone_s} && git status", worktree)
    assert not allowed
    allowed, _ = validate_workspace_command(f"cat {clone_s}/README.md", worktree)
    assert not allowed
    other_git = tmp_path / "profiles" / "other-user" / "workspace" / "app" / ".git"
    other_git.mkdir(parents=True)
    allowed, _ = validate_workspace_command(
        f"git --git-dir={other_git.resolve()} status",
        worktree,
    )
    assert not allowed

    # Worktree itself still allowed
    allowed, reason = validate_workspace_command(f"cd {wt_s} && git merge main", worktree)
    assert allowed, reason


def test_worktree_jail_ignores_forged_gitfile(tmp_path: Path) -> None:
    """Rewriting the worktree gitfile must not widen the jail to secrets."""
    _clone, worktree, _git_dir = _fake_linked_worktree(tmp_path)
    secret = tmp_path / "profiles" / "other-user" / "secrets.env"
    secret.parent.mkdir(parents=True)
    secret.write_text("SECRET=1\n", encoding="utf-8")
    (worktree / ".git").write_text(f"gitdir: {secret.resolve()}\n", encoding="utf-8")
    allowed, _ = validate_workspace_command(f"cat {secret.resolve()}", worktree)
    assert not allowed


def test_worktree_jail_file_tool_can_read_gitdir(tmp_path: Path) -> None:
    from core.workspace import resolve_tool_path

    _clone, worktree, git_dir = _fake_linked_worktree(tmp_path)
    from core.tools.execution_context import reset_workspace_scope, workspace_scope

    tokens = workspace_scope(workspace_root=str(worktree), workspace_jail_enabled=True)
    try:
        resolved = resolve_tool_path(str((git_dir / "config").resolve()))
        assert resolved == (git_dir / "config").resolve()
    finally:
        reset_workspace_scope(tokens)


def test_jail_disabled_allows_outside_paths() -> None:
    allowed, _ = validate_workspace_command(
        "cat /etc/hosts",
        None,
        jail_enabled=False,
    )
    assert allowed


def test_jail_disabled_allows_holix_profile_paths() -> None:
    allowed, _ = validate_workspace_command(
        "ls ~/.holix/profiles/bob",
        None,
        jail_enabled=False,
    )
    assert allowed
