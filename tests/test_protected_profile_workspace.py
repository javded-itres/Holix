"""Protected profiles get an isolated workspace directory."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager, enable_profile_workspace_isolation
from core.profile_keys import store_profile_access_key


@pytest.fixture
def helix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    monkeypatch.setenv("HELIX_ENV", "development")
    return tmp_path


def test_enable_workspace_isolation_on_existing_profile(helix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("bob")
    store_profile_access_key("bob")

    workspace = enable_profile_workspace_isolation(manager, "bob")
    config = manager.load_profile("bob")

    assert workspace == manager.get_profile_dir("bob") / "workspace"
    assert workspace.is_dir()
    assert config.workspace_jail_enabled is True
    assert config.workspace_root == str(workspace.resolve())