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


def test_blocks_listing_root(workspace: Path) -> None:
    blocked, _ = command_escapes_workspace("ls -la /", workspace)
    assert blocked


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