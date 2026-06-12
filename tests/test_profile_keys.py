"""Tests for profile access keys."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager, init_profile, switch_profile
from core.profile_keys import (
    ProfileKeyError,
    ProfileNotFoundError,
    profile_has_access_key,
    remove_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def reset_unlocked_profiles() -> None:
    from cli import core

    core._unlocked_profiles.clear()
    yield
    core._unlocked_profiles.clear()


def test_create_profile_open_by_default(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("alice")
    assert not profile_has_access_key("alice")
    assert manager.pop_last_created_access_key() is None


def test_create_profile_with_access_key(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True)
    assert profile_has_access_key("alice")
    key = manager.pop_last_created_access_key()
    assert key and key.startswith("hp_")
    config = manager.load_profile("alice")
    workspace = manager.get_profile_dir("alice") / "workspace"
    assert workspace.is_dir()
    assert config.workspace_jail_enabled is True
    assert config.workspace_root == str(workspace.resolve())


def test_default_profile_blocked_in_production(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import resolve_active_profile_name

    monkeypatch.setenv("HOLIX_ENV", "production")

    with pytest.raises(ProfileNotFoundError):
        resolve_active_profile_name(None)

    with pytest.raises(ProfileNotFoundError):
        resolve_active_profile_name("default")


def test_switch_requires_access_key(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ProfileManager()
    manager.create_profile("bob", with_access_key=True)
    access_key = manager.pop_last_created_access_key()
    assert access_key

    init_profile("default", prompt_key=False)

    with pytest.raises(ProfileKeyError):
        switch_profile("bob", profile_key="wrong-key")

    config = switch_profile("bob", profile_key=access_key)
    assert config.profile_name == "bob"


def test_env_profile_key_unlocks(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ProfileManager()
    manager.create_profile("carol", with_access_key=True)
    access_key = manager.pop_last_created_access_key()
    assert access_key

    init_profile("default", prompt_key=False)
    monkeypatch.setenv("HOLIX_PROFILE_KEY", access_key)
    config = init_profile("carol", prompt_key=False)
    assert config.profile_name == "carol"


def test_default_profile_switch_without_key(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("legacy")
    assert not profile_has_access_key("legacy")

    init_profile("default", prompt_key=False)
    config = switch_profile("legacy")
    assert config.profile_name == "legacy"


def test_load_profile_unknown_raises(holix_home: Path) -> None:
    manager = ProfileManager()
    with pytest.raises(ProfileNotFoundError):
        manager.load_profile("missing")


def test_key_init_and_verify(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("dana", with_access_key=False)
    key = store_profile_access_key("dana")
    assert verify_profile_access_key("dana", key)
    assert not verify_profile_access_key("dana", "bad")


def test_disable_access_key_allows_free_switch(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("eve", with_access_key=True)
    access_key = manager.pop_last_created_access_key()
    assert access_key

    init_profile("default", prompt_key=False)
    switch_profile("eve", profile_key=access_key)

    assert remove_profile_access_key("eve")
    assert not profile_has_access_key("eve")

    config = switch_profile("eve")
    assert config.profile_name == "eve"