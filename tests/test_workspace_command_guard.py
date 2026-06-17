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