"""Workspace directory is created for every profile; jail is opt-in."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    return tmp_path


def test_create_profile_has_workspace_without_jail(holix_home: Path) -> None:
    manager = ProfileManager()
    config = manager.create_profile("alice")

    workspace = manager.get_profile_dir("alice") / "workspace"
    assert workspace.is_dir()
    assert config.workspace_jail_enabled is False
    assert config.workspace_root == str(workspace.resolve())


def test_default_and_admin_profiles_have_no_jail(holix_home: Path) -> None:
    manager = ProfileManager()
    for name in ("default", "admin"):
        manager.create_profile(name)
        config = manager.load_profile(name)
        assert config.workspace_jail_enabled is False


def test_load_profile_preserves_jail_disabled(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("bob")
    config_file = manager.get_profile_dir("bob") / "config.yaml"
    config_file.write_text("profile_name: bob\nworkspace_jail_enabled: false\n", encoding="utf-8")

    config = manager.load_profile("bob")
    workspace = manager.get_profile_dir("bob") / "workspace"

    assert config.workspace_jail_enabled is False
    assert config.workspace_root == str(workspace.resolve())


def test_load_profile_preserves_jail_enabled(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("carol", with_access_key=True)
    config = manager.load_profile("carol")

    assert config.workspace_jail_enabled is True