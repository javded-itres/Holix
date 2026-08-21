"""`.holix/HOLIX.md` project context."""

from __future__ import annotations

from pathlib import Path

from core.project.holix_md import (
    HOLIX_MD_REL_PATH,
    append_holix_project_context,
    discover_holix_md_paths,
    ensure_holix_md_exists,
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


def test_discovers_holix_md_at_four_levels(tmp_path: Path) -> None:
    """Studio layout: workspace / projects / slug / repo / .holix / HOLIX.md."""
    project = tmp_path / "workspace"
    repo = project / "projects" / "shop" / "api"
    repo.mkdir(parents=True)
    holix = repo / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Shop API\n", encoding="utf-8")

    assert resolve_holix_md_read_path(project) == holix / "HOLIX.md"
    assert "Shop API" in load_holix_md(project)


def test_ignores_holix_md_deeper_than_four_levels(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    deep = project / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    holix = deep / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Too deep\n", encoding="utf-8")

    assert resolve_holix_md_read_path(project) is None
    assert not holix_md_exists(project)


def test_reads_legacy_root_holix_md(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "HOLIX.md").write_text("# Root handbook\n", encoding="utf-8")
    assert resolve_holix_md_read_path(project) == project / "HOLIX.md"


def test_ensure_creates_holix_md_when_missing(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "README.md").write_text("# App\n", encoding="utf-8")
    monkeypatch.chdir(project)

    path = ensure_holix_md_exists(project)
    assert path is not None
    assert path == project / ".holix" / "HOLIX.md"
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip()


def test_ensure_migrates_root_holix_md(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "HOLIX.md").write_text("# Legacy root\n\nStack: FastAPI\n", encoding="utf-8")

    path = ensure_holix_md_exists(project)
    assert path == project / ".holix" / "HOLIX.md"
    assert "FastAPI" in path.read_text(encoding="utf-8")
    assert (project / "HOLIX.md").is_file()  # original kept


def test_append_injects_agents_claude_and_rules(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.chdir(project)
    holix = project / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Handbook\n\nAPI service\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# Agents\n\nUse uv.\n", encoding="utf-8")
    (project / "CLAUDE.md").write_text("# Claude\n\nNo secrets.\n", encoding="utf-8")
    (project / "rules.md").write_text("# Rules\n\nSOLID.\n", encoding="utf-8")

    out = append_holix_project_context("BASE", project)
    assert "BASE" in out
    assert "API service" in out
    assert "Use uv." in out
    assert "No secrets." in out
    assert "SOLID." in out
    assert "AGENTS.md" in out
    assert "CLAUDE.md" in out
    assert "rules.md" in out


def test_append_reads_RULES_md_when_rules_md_missing(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.chdir(project)
    holix = project / ".holix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Handbook\n", encoding="utf-8")
    (project / "RULES.md").write_text("# RULES\n\nLint before push.\n", encoding="utf-8")

    out = append_holix_project_context("BASE", project)
    assert "Lint before push." in out
    assert "RULES.md" in out


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
