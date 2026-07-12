"""Studio workspace hint in system prompt."""

from __future__ import annotations

import pytest

from core.prompt_builder import format_studio_workspace_block


def test_studio_workspace_block_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_MODE", "cwd")
    monkeypatch.setenv("HOLIX_STUDIO_WORKSPACE_ROOT", "/Users/dev/Helix")
    block = format_studio_workspace_block()
    assert "cwd" in block
    assert "/Users/dev/Helix" in block
    assert "profile" in block.lower()


def test_studio_workspace_block_empty_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_MODE", raising=False)
    monkeypatch.delenv("HOLIX_STUDIO_WORKSPACE_ROOT", raising=False)
    assert format_studio_workspace_block() == ""