"""Tests for Holix Studio workspace files API helpers."""

from __future__ import annotations

import pytest
from integrations.desktop.workspace_files import (
    WorkspacePathError,
    create_directory,
    list_tree,
    read_file,
    resolve_studio_workspace_root,
    resolve_workspace_path,
    upload_file,
    write_file,
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


def test_read_log_file(studio_profile, studio_profile_ws) -> None:
    (studio_profile_ws / "logs").mkdir()
    (studio_profile_ws / "logs" / "helix_20260603.log").write_text(
        "2026-06-03 INFO started\n",
        encoding="utf-8",
    )
    data = read_file(
        studio_profile,
        "logs/helix_20260603.log",
        workspace_root=studio_profile_ws,
    )
    assert "INFO started" in data["content"]


def test_path_traversal_blocked(studio_profile, studio_profile_ws) -> None:
    with pytest.raises(WorkspacePathError):
        resolve_workspace_path(
            studio_profile,
            "../secret",
            workspace_root=studio_profile_ws,
        )


def test_write_file_create_and_update(studio_profile, studio_profile_ws) -> None:
    created = write_file(
        studio_profile,
        "notes/new.txt",
        "hello",
        create_only=True,
        workspace_root=studio_profile_ws,
    )
    assert created["created"] is True
    assert read_file(studio_profile, "notes/new.txt", workspace_root=studio_profile_ws)["content"] == "hello"

    updated = write_file(
        studio_profile,
        "notes/new.txt",
        "updated",
        workspace_root=studio_profile_ws,
    )
    assert updated["created"] is False
    assert read_file(studio_profile, "notes/new.txt", workspace_root=studio_profile_ws)["content"] == "updated"


def test_write_file_create_only_conflict(studio_profile, studio_profile_ws) -> None:
    write_file(studio_profile, "dup.txt", "a", create_only=True, workspace_root=studio_profile_ws)
    with pytest.raises(FileExistsError):
        write_file(studio_profile, "dup.txt", "b", create_only=True, workspace_root=studio_profile_ws)


def test_create_directory(studio_profile, studio_profile_ws) -> None:
    created = create_directory(studio_profile, "notes", workspace_root=studio_profile_ws)
    assert created["path"] == "notes"
    assert created["kind"] == "directory"
    assert (studio_profile_ws / "notes").is_dir()

    nested = create_directory(
        studio_profile,
        "notes/archive/2026",
        workspace_root=studio_profile_ws,
    )
    assert nested["path"] == "notes/archive/2026"
    assert (studio_profile_ws / "notes" / "archive" / "2026").is_dir()


def test_create_directory_conflict(studio_profile, studio_profile_ws) -> None:
    with pytest.raises(FileExistsError):
        create_directory(studio_profile, "docs", workspace_root=studio_profile_ws)


def test_upload_file(studio_profile, studio_profile_ws) -> None:
    result = upload_file(
        studio_profile,
        "docs",
        "image.bin",
        b"\x00\x01",
        workspace_root=studio_profile_ws,
    )
    assert result["path"] == "docs/image.bin"
    assert (studio_profile_ws / "docs" / "image.bin").read_bytes() == b"\x00\x01"


def test_resolve_studio_workspace_uses_serve_cwd_when_jail_off(
    tmp_path,
    monkeypatch,
    studio_profile,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    root = resolve_studio_workspace_root(studio_profile, serve_cwd=project)
    assert root == project.resolve()