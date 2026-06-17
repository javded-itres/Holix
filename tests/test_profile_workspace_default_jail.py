"""Every profile gets an isolated workspace directory by default."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    return tmp_path


def test_create_profile_enables_workspace_jail(holix_home: Path) -> None:
    manager = ProfileManager()
    config = manager.create_profile("alice")

    workspace = manager.get_profile_dir("alice") / "workspace"
    assert workspace.is_dir()
    assert config.workspace_jail_enabled is True
    assert config.workspace_root == str(workspace.resolve())


def test_load_profile_migrates_workspace_jail(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("bob")
    config_file = manager.get_profile_dir("bob") / "config.yaml"
    config_file.write_text("profile_name: bob\nworkspace_jail_enabled: false\n", encoding="utf-8")

    config = manager.load_profile("bob")
    workspace = manager.get_profile_dir("bob") / "workspace"

    assert config.workspace_jail_enabled is True
    assert config.workspace_root == str(workspace.resolve())