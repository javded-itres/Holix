"""Deterministic `/init` pre-scan."""

from __future__ import annotations

from core.project.holix_md import HOLIX_MD_FILENAME
from core.project.init_scan import (
    format_init_scan_report,
    scan_project_for_init,
    write_init_skeleton,
)


def _seed_monorepo(root) -> None:
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "package.json").write_text("{}", encoding="utf-8")
    api = root / "apps" / "api"
    web = root / "apps" / "web"
    api.mkdir(parents=True)
    web.mkdir(parents=True)
    (api / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
    (web / "package.json").write_text("{}", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "architecture.md").write_text("# Arch\n", encoding="utf-8")


def test_scan_project_for_init_detects_manifests_and_subprojects(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_monorepo(tmp_path)

    scan = scan_project_for_init()

    assert scan.file_count >= 4
    assert any("package.json" in p for p in scan.manifest_paths)
    assert any("apps/api" in p for p in scan.manifest_paths)
    assert "README.md" in scan.readme_paths
    assert "docs" in scan.doc_dirs
    assert any(p.endswith("apps/api") or "apps/api" in p for p in scan.subprojects)
    assert scan.directory_tree
    assert "apps/" in scan.directory_tree


def test_format_init_scan_report_includes_tree_and_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_monorepo(tmp_path)
    scan = scan_project_for_init(target_dir="apps/api")

    report = format_init_scan_report(scan, locale="en")

    assert "Pre-scan" in report
    assert "apps/api" in report
    assert "```" in report
    assert "pyproject.toml" in report


def test_write_init_skeleton_creates_holix_md(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_monorepo(tmp_path)
    scan = scan_project_for_init()
    template = "# Template\n\n## Overview\n"

    path = write_init_skeleton(
        scan,
        holix_rel_path=".holix/HOLIX.md",
        template=template,
        locale="en",
    )

    assert path == tmp_path / ".holix" / HOLIX_MD_FILENAME
    text = path.read_text(encoding="utf-8")
    assert "# Template" in text
    assert "Pre-filled from scan" in text
    assert "apps/" in text


def test_scan_skips_library_without_descending(tmp_path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("x = 1\n", encoding="utf-8")
    poison = tmp_path / "Library" / "Caches"
    poison.mkdir(parents=True)
    (poison / "huge.py").write_text("y = 2\n", encoding="utf-8")

    scan = scan_project_for_init(cwd=tmp_path)

    assert scan.file_count == 1
    assert "Library" not in scan.top_level_dirs
    assert all("Library" not in p for p in scan.manifest_paths)


def test_scan_refuses_home_directory(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    home = tmp_path / "home"
    docs = home / "Documents"
    docs.mkdir(parents=True)
    (docs / "notes.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    scan = scan_project_for_init(cwd=home)

    assert scan.file_count == 0
    assert scan.manifest_paths == []
    assert scan.directory_tree == ""


def test_scan_marks_large_repo_by_file_count(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "src"
    pkg.mkdir()
    for i in range(450):
        (pkg / f"mod_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")

    scan = scan_project_for_init()

    assert scan.is_large
    report = format_init_scan_report(scan, locale="ru")
    assert "Большой репозиторий" in report
