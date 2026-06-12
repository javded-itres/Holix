"""`.holix/HOLIX.md` project context."""

from __future__ import annotations

from pathlib import Path

from core.project.holix_md import (
    HOLIX_MD_REL_PATH,
    append_holix_project_context,
    format_holix_md_block,
    get_holix_md_path,
    holix_md_exists,
    load_holix_md,
)
from core.project.init_prompt import build_init_user_message


def test_holix_md_path_under_dot_helix(tmp_path: Path) -> None:
    p = get_holix_md_path(tmp_path)
    assert p == tmp_path / ".holix" / "HOLIX.md"
    assert HOLIX_MD_REL_PATH == ".holix/HOLIX.md"


def test_load_and_inject(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.chdir(tmp_path)
    holix = tmp_path / ".helix"
    holix.mkdir()
    (holix / "HOLIX.md").write_text("# Demo\n\nREST on /api/v1\n", encoding="utf-8")

    assert holix_md_exists()
    assert "REST" in load_holix_md()
    block = format_holix_md_block()
    assert "REST" in block
    out = append_holix_project_context("BASE", tmp_path)
    assert "BASE" in out
    assert "REST" in out


def test_init_message_targets_holix_md() -> None:
    msg = build_init_user_message()
    assert ".holix/HOLIX.md" in msg
    assert "write_file" in msg.lower() or "Write" in msg