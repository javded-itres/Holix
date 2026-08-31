"""System prompt includes Holix env path context."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.env_loader import format_env_context_block, profile_env_path
from core.prompt_builder import build_system_prompt, tools_prompt_policy


def test_format_env_context_block_lists_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_PROFILE", "work")
    (tmp_path / "profiles" / "work").mkdir(parents=True)
    profile_env_path("work").write_text("MODEL=test\n", encoding="utf-8")
    (tmp_path / "profiles" / "work" / "config.yaml").write_text(
        "profile_name: work\n", encoding="utf-8"
    )

    block = format_env_context_block()
    assert str(tmp_path) in block
    assert "work" in block
    assert str(profile_env_path("work")) in block
    assert "HOLIX_HOME" in block
    assert "holix gateway reload" in block


def test_tools_prompt_policy_is_not_a_catalog() -> None:
    text = tools_prompt_policy()
    assert "JSON schemas" in text
    assert "not listed here" in text
    assert "- **read_file**:" not in text
    assert "Navigate code with `lsp`" in text
    assert "pytest-loop" in text
    assert "tail/head" in text
    prompt = build_system_prompt(
        tools_description=text,
        active_skills=[],
        profile_name="default",
    )
    assert "Function-calling tools are attached" in prompt
    assert "- **read_file**:" not in prompt


def test_build_system_prompt_includes_env_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_build_system_prompt_requires_run_and_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    (tmp_path / "profiles" / "default").mkdir(parents=True)

    prompt = build_system_prompt(
        tools_description="- **read_file**: read",
        active_skills=[],
        profile_name="default",
    )
    assert "## Run, debug, and environment setup (mandatory after you change code)" in prompt
    assert "patch_file" in prompt
    assert "create a new file" in prompt.lower() or "new file" in prompt
    assert "writing files is not enough" in prompt.lower()
    assert "check_background_process" in prompt
    assert "never claim" in prompt.lower() and "done" in prompt.lower()
    assert "## Hard rule: never fake completed work" in prompt
    assert "Saying you will do it is not doing it" in prompt
    assert "Navigate code with `lsp`" in prompt
    assert "## Review vs implement" in prompt
    assert "do not pytest-loop" in prompt.lower() or "pytest-loop" in prompt
    assert "never pipe" in prompt.lower()
    assert "всё ли работает" not in prompt
    assert "все ли работает" not in prompt


def test_format_env_context_block_jail_hides_install_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gateway CWD is Holix install — must not appear as project root when jail is on."""
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_PROFILE", "invite-user")
    (tmp_path / "profiles" / "invite-user").mkdir(parents=True)
    workspace = tmp_path / "profiles" / "invite-user" / "workspace"
    workspace.mkdir(parents=True)
    install = tmp_path / "holix-deploy" / "Helix"
    install.mkdir(parents=True)
    (install / ".env").write_text("FROM_INSTALL=1\n", encoding="utf-8")
    monkeypatch.chdir(install)

    block = format_env_context_block(
        profile_name="invite-user",
        workspace_root=str(workspace),
        workspace_jail_enabled=True,
    )
    assert str(install / ".env") not in block
    assert "holix-deploy" not in block
    assert str(workspace) in block
    assert "jail root" in block.lower()

    prompt = build_system_prompt(
        tools_description="- **read_file**: read",
        active_skills=[],
        profile_name="invite-user",
        workspace_root=str(workspace),
        workspace_jail_enabled=True,
    )
    assert str(workspace) in prompt
    assert str(install / ".env") not in prompt
