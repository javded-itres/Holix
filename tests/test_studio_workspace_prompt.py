"""Studio workspace hint in system prompt."""

from __future__ import annotations

import pytest
from core.prompt_builder import (
    format_studio_preview_block,
    format_studio_workspace_block,
)


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


def test_studio_preview_block_empty_outside_studio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_STUDIO", raising=False)
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_MODE", raising=False)
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_ROOT", raising=False)
    assert format_studio_preview_block(workspace_jail_enabled=False) == ""


def test_studio_preview_block_subdomain_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_STUDIO", "1")
    monkeypatch.setenv("PREVIEW_URL_MODE", "subdomain")
    monkeypatch.setenv("PREVIEW_BASE_DOMAIN", "preview.holix-agent.ru")
    monkeypatch.setenv("STUDIO_PUBLIC_URL", "https://studio.holix-agent.ru")
    block = format_studio_preview_block()
    assert "subdomain" in block.lower()
    assert "preview.holix-agent.ru" in block
    assert "localhost" in block  # forbidden rule mentions it
    assert "Browser" in block
    assert "open_preview_url" in block
    assert "holix_studio" in block
    assert "p{PORT}" in block or "p{{PORT}}" in block or "p{PORT}-" in block


def test_studio_preview_block_path_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_STUDIO", "1")
    monkeypatch.setenv("PREVIEW_URL_MODE", "path")
    monkeypatch.delenv("PREVIEW_BASE_DOMAIN", raising=False)
    monkeypatch.setenv("STUDIO_PUBLIC_URL", "https://studio.example.com")
    block = format_studio_preview_block()
    assert "/studio/preview/" in block
    assert "subdomain" not in block.lower() or "path" in block.lower()
