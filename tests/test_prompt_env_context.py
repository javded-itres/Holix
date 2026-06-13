"""System prompt includes Holix env path context."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.env_loader import format_env_context_block, profile_env_path
from core.prompt_builder import build_system_prompt


def test_format_env_context_block_lists_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_PROFILE", "work")
    (tmp_path / "profiles" / "work").mkdir(parents=True)
    profile_env_path("work").write_text("MODEL=test\n", encoding="utf-8")
    (tmp_path / "profiles" / "work" / "config.yaml").write_text("profile_name: work\n", encoding="utf-8")

    block = format_env_context_block()
    assert str(tmp_path) in block
    assert "work" in block
    assert str(profile_env_path("work")) in block
    assert "HOLIX_HOME" in block
    assert "holix gateway reload" in block


def test_build_system_prompt_includes_env_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    (tmp_path / "profiles" / "default").mkdir(parents=True)
    profile_env_path("default").write_text("# env\n", encoding="utf-8")

    prompt = build_system_prompt(
        tools_description="- **read_file**: read",
        active_skills=[],
        profile_name="default",
    )
    assert "## Holix configuration paths" in prompt
    assert str(profile_env_path("default")) in prompt