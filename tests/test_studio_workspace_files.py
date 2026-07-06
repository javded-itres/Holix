"""Tests for Holix Studio workspace files API helpers."""

from __future__ import annotations

import pytest
from integrations.desktop.workspace_files import (
    WorkspacePathError,
    list_tree,
    read_file,
    resolve_workspace_path,
)


@pytest.fixture
def studio_profile(tmp_path, monkeypatch):
    home = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(home))
    profile = "studio_test"
    ws = home / "profiles" / profile / "workspace"
    ws.mkdir(parents=True)
    (ws / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (ws / "docs").mkdir()
    (ws / "docs" / "readme.md").write_text("# Hi\n", encoding="utf-8")
    return profile


def test_list_tree(studio_profile) -> None:
    tree = list_tree(studio_profile, depth=3)
    names = {c["name"] for c in tree["children"]}
    assert "hello.py" in names
    assert "docs" in names


def test_read_file(studio_profile) -> None:
    data = read_file(studio_profile, "hello.py")
    assert "print" in data["content"]
    assert data["language"] == "python"


def test_path_traversal_blocked(studio_profile) -> None:
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(studio_profile, "../secret")