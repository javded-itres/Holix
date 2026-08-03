"""Planning context: HOLIX.md + openspec specs + auto /init pre-scan."""

from __future__ import annotations

from core.project.holix_md import HOLIX_MD_FILENAME
from core.project.planning_context import (
    ensure_planning_context,
    load_openspec_specs_context,
)


def test_ensure_runs_init_when_holix_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# App\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"app"}\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")

    assert not (tmp_path / ".holix" / HOLIX_MD_FILENAME).exists()

    ctx = ensure_planning_context(locale="en")

    assert ctx.init_ran is True
    assert (tmp_path / ".holix" / HOLIX_MD_FILENAME).is_file()
    assert ctx.holix_present is True
    assert "HOLIX.md" in ctx.handbook_block or "Project knowledge" in ctx.handbook_block
    assert "package.json" in ctx.handbook_block or "Pre-scan" in ctx.handbook_block or "scan" in ctx.handbook_block.lower()


def test_ensure_uses_existing_holix_without_init(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    holix = tmp_path / ".holix"
    holix.mkdir(parents=True, exist_ok=True)
    (holix / HOLIX_MD_FILENAME).write_text(
        "# Handbook\n\n## Overview\nCustom stack: FastAPI + Postgres\n",
        encoding="utf-8",
    )

    ctx = ensure_planning_context(locale="en")

    assert ctx.init_ran is False
    assert ctx.holix_present is True
    assert "FastAPI + Postgres" in ctx.handbook_block


def test_load_openspec_specs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / "openspec" / "specs" / "auth"
    specs.mkdir(parents=True)
    (specs / "spec.md").write_text(
        "# Auth\n\n## Requirements\n- Login with email\n",
        encoding="utf-8",
    )

    block, paths = load_openspec_specs_context()
    assert paths
    assert "openspec/specs/auth/spec.md" in paths[0] or "spec.md" in paths[0]
    assert "Login with email" in block

    ctx = ensure_planning_context(locale="en")
    # No HOLIX → init runs, but specs still included
    assert ctx.specs_present is True
    assert "Login with email" in ctx.handbook_block
