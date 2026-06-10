"""Tests for profile terminal whitelist CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.env_loader import profile_env_path
from core.terminal_whitelist_config import (
    WHITELIST_ENABLED_KEY,
    WHITELIST_EXTRA_KEY,
    add_whitelist_commands,
    parse_command_list,
    read_whitelist_enabled,
    read_whitelist_extra,
    set_whitelist_enabled,
)


@pytest.fixture
def profile_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    profile = "dev"
    profiles_root = tmp_path / "profiles"
    profile_dir = profiles_root / profile
    profile_dir.mkdir(parents=True)
    (profile_dir / ".env").write_text("# test profile env\n", encoding="utf-8")
    monkeypatch.setattr("cli.core.PROFILES_DIR", profiles_root)
    monkeypatch.setattr("core.env_loader.helix_home", lambda: tmp_path)
    return profile


def test_parse_command_list_dedupes_and_normalizes() -> None:
    assert parse_command_list(" Docker, make ,docker, GIT ") == ["docker", "make", "git"]


def test_add_whitelist_commands_persists_to_profile_env(profile_env: str) -> None:
    added = add_whitelist_commands(profile_env, "ls, cat, python, git")
    assert added == ["ls", "cat", "python", "git"]
    assert read_whitelist_extra(profile_env) == ["ls", "cat", "python", "git"]

    added_again = add_whitelist_commands(profile_env, "docker, ls")
    assert added_again == ["docker"]
    assert read_whitelist_extra(profile_env) == ["ls", "cat", "python", "git", "docker"]

    path = profile_env_path(profile_env)
    text = path.read_text(encoding="utf-8")
    assert f"{WHITELIST_EXTRA_KEY}=ls,cat,python,git,docker" in text


def test_set_whitelist_enabled_writes_profile_env(profile_env: str) -> None:
    set_whitelist_enabled(profile_env, True)
    assert read_whitelist_enabled(profile_env) is True
    path = profile_env_path(profile_env)
    assert f"{WHITELIST_ENABLED_KEY}=true" in path.read_text(encoding="utf-8")

    set_whitelist_enabled(profile_env, False)
    assert read_whitelist_enabled(profile_env) is False
    assert f"{WHITELIST_ENABLED_KEY}=false" in path.read_text(encoding="utf-8")


def test_settings_read_helix_whitelist_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_TERMINAL_COMMAND_WHITELIST", "false")
    monkeypatch.setenv("HELIX_TERMINAL_WHITELIST_EXTRA", "docker,make")
    from importlib import reload

    import config

    reload(config)
    assert config.settings.terminal_command_whitelist is False
    assert config.settings.terminal_whitelist_extra == "docker,make"