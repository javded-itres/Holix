"""Tests for Holix Studio workspace files API helpers."""

from __future__ import annotations

import pytest
from integrations.desktop.workspace_files import (
    WorkspacePathError,
    list_tree,
    read_file,
    resolve_studio_workspace_root,
    resolve_workspace_path,
)


@pytest.fixture
def studio_profile(tmp_path, monkeypatch):
    home = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(home))
    profile = "studio_test"
    profile_dir = home / "profiles" / profile
    ws = profile_dir / "workspace"
    ws.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "profile_name: studio_test\nworkspace_jail_enabled: false\n",
        encoding="utf-8",
    )
    (ws / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (ws / "docs").mkdir()
    (ws / "docs" / "readme.md").write_text("# Hi\n", encoding="utf-8")
    return profile


@pytest.fixture
def studio_profile_ws(tmp_path, monkeypatch, studio_profile):
    home = tmp_path / "holix"
    return home / "profiles" / studio_profile / "workspace"


def test_list_tree(studio_profile, studio_profile_ws) -> None:
    tree = list_tree(studio_profile, depth=3, workspace_root=studio_profile_ws)
    names = {c["name"] for c in tree["children"]}
    assert "hello.py" in names
    assert "docs" in names


def test_read_file(studio_profile, studio_profile_ws) -> None:
    data = read_file(studio_profile, "hello.py", workspace_root=studio_profile_ws)
    assert "print" in data["content"]
    assert data["language"] == "python"


def test_path_traversal_blocked(studio_profile, studio_profile_ws) -> None:
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(
            studio_profile,
            "../secret",
            workspace_root=studio_profile_ws,
        )


def test_resolve_studio_workspace_uses_serve_cwd_when_jail_off(
    tmp_path,
    monkeypatch,
    studio_profile,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    root = resolve_studio_workspace_root(studio_profile, serve_cwd=project)
    assert root == project.resolve()