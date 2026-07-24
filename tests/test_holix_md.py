"""`.holix/HOLIX.md` project context."""

from __future__ import annotations

from pathlib import Path

from core.project.holix_md import (
    HOLIX_MD_REL_PATH,
    append_holix_project_context,
    discover_holix_md_paths,
    format_holix_md_block,
    get_holix_md_path,
    holix_md_exists,
    load_holix_md,
    resolve_holix_md_read_path,
)
from core.project.init_prompt import build_init_user_message


def test_holix_md_path_under_dot_helix(tmp_path: Path) -> None:
    p = get_holix_md_path(tmp_path)
    assert p == tmp_path / ".holix" / "HOLIX.md"
    assert HOLIX_MD_REL_PATH == ".holix/HOLIX.md"


def test_load_and_inject(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    holix = project / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Demo\n\nREST on /api/v1\n", encoding="utf-8")

    assert holix_md_exists(project)
    assert "REST" in load_holix_md(project)
    block = format_holix_md_block()
    assert "REST" in block
    out = append_holix_project_context("BASE", project)
    assert "BASE" in out
    assert "REST" in out


def test_init_message_targets_holix_md() -> None:
    msg = build_init_user_message()
    assert ".holix/HOLIX.md" in msg
    assert "write_file" in msg.lower() or "Write" in msg


def test_discover_nested_holix_md_up_to_two_levels(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    nested = project / "apps" / "api"
    nested.mkdir(parents=True)
    holix = nested / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# API service\n", encoding="utf-8")

    assert resolve_holix_md_read_path(project) == holix / "HOLIX.md"
    assert holix_md_exists(project)
    assert "API service" in load_holix_md(project)
    block = format_holix_md_block(project)
    assert "apps/api/.holix/HOLIX.md" in block
    assert "API service" in block


def test_prefers_root_holix_md_over_nested(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    root_holix = project / ".holix"
    root_holix.mkdir()
    (root_holix / "HOLIX.md").write_text("# Root handbook\n", encoding="utf-8")

    nested = project / "pkg"
    nested.mkdir()
    pkg_holix = nested / ".holix"
    pkg_holix.mkdir()
    (pkg_holix / "HOLIX.md").write_text("# Package only\n", encoding="utf-8")

    assert resolve_holix_md_read_path(project) == root_holix / "HOLIX.md"
    assert "Root handbook" in load_holix_md(project)
    paths = discover_holix_md_paths(project)
    assert paths[0] == root_holix / "HOLIX.md"
    assert len(paths) == 2


def test_ignores_holix_md_deeper_than_two_levels(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    deep = project / "a" / "b" / "c"
    deep.mkdir(parents=True)
    holix = deep / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Too deep\n", encoding="utf-8")

    assert resolve_holix_md_read_path(project) is None
    assert not holix_md_exists(project)


def test_discover_skips_unreadable_subdirs(tmp_path: Path) -> None:
    """Docker volume mounts (root-owned db_data) must not abort discovery."""
    import os
    import stat

    project = tmp_path / "repo"
    project.mkdir()
    nested = project / "apps" / "api"
    nested.mkdir(parents=True)
    holix = nested / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# API\n", encoding="utf-8")

    blocked = project / "emis_backend" / "db_data"
    blocked.mkdir(parents=True)
    # No traverse for others — mimics root-owned postgres volume for non-root agent.
    os.chmod(blocked, 0o000)

    try:
        paths = discover_holix_md_paths(project)
        assert paths == [holix / "HOLIX.md"]
        assert "API" in load_holix_md(project)
    finally:
        os.chmod(blocked, stat.S_IRWXU)