"""`.helix/HELIX.md` project context."""

from __future__ import annotations

from pathlib import Path

from core.project.helix_md import (
    HELIX_MD_REL_PATH,
    append_helix_project_context,
    format_helix_md_block,
    get_helix_md_path,
    helix_md_exists,
    load_helix_md,
)
from core.project.init_prompt import build_init_user_message


def test_helix_md_path_under_dot_helix(tmp_path: Path) -> None:
    p = get_helix_md_path(tmp_path)
    assert p == tmp_path / ".helix" / "HELIX.md"
    assert HELIX_MD_REL_PATH == ".helix/HELIX.md"


def test_load_and_inject(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.chdir(tmp_path)
    helix = tmp_path / ".helix"
    helix.mkdir()
    (helix / "HELIX.md").write_text("# Demo\n\nREST on /api/v1\n", encoding="utf-8")

    assert helix_md_exists()
    assert "REST" in load_helix_md()
    block = format_helix_md_block()
    assert "REST" in block
    out = append_helix_project_context("BASE", tmp_path)
    assert "BASE" in out
    assert "REST" in out


def test_init_message_targets_helix_md() -> None:
    msg = build_init_user_message()
    assert ".helix/HELIX.md" in msg
    assert "write_file" in msg.lower() or "Write" in msg