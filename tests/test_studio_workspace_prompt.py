"""Studio workspace hint in system prompt."""

from __future__ import annotations

import pytest
from core.prompt_builder import format_studio_workspace_block


def test_studio_workspace_block_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_MODE", "cwd")
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_ROOT", "/Users/dev/Helix")
    block = format_studio_workspace_block(workspace_jail_enabled=False)
    assert "cwd" in block
    assert "/Users/dev/Helix" in block
    assert "profile" in block.lower()


def test_studio_workspace_block_prefers_session_jail_over_serve_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SaaS serve often sets cwd=deploy tree; agent must use the user profile workspace."""
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_MODE", "cwd")
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_ROOT", "/home/itadmin/holix-deploy/Helix")
    block = format_studio_workspace_block(
        workspace_root="/var/lib/holix/profiles/invite-user/workspace",
        workspace_jail_enabled=True,
    )
    assert "/var/lib/holix/profiles/invite-user/workspace" in block
    assert "/home/itadmin/holix-deploy/Helix" not in block
    assert "Do **not** write into the Holix install/deploy" in block


def test_studio_workspace_block_empty_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_MODE", raising=False)
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_ROOT", raising=False)
    assert format_studio_workspace_block(workspace_jail_enabled=False) == ""
