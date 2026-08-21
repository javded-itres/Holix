"""AGENTS.md / CLAUDE.md / rules.md discovery for agent context."""

from __future__ import annotations

from pathlib import Path

from core.project.instruction_files import (
    discover_instruction_files,
    format_instruction_files_block,
)


def test_discovers_root_agent_files(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    (tmp_path / "rules.md").write_text("rules\n", encoding="utf-8")

    names = {p.name for p in discover_instruction_files(tmp_path)}
    assert names == {"AGENTS.md", "CLAUDE.md", "rules.md"}


def test_rules_md_preferred_over_RULES_md_when_both_exist(tmp_path: Path) -> None:
    """On case-sensitive FS both files can exist; inject rules.md first, not twice if same file."""
    (tmp_path / "rules.md").write_text("lower\n", encoding="utf-8")
    try:
        (tmp_path / "RULES.md").write_text("upper\n", encoding="utf-8")
    except OSError:
        # Case-insensitive volume: single file.
        pass
    paths = discover_instruction_files(tmp_path)
    rules = [p for p in paths if p.name.lower() == "rules.md"]
    assert len(rules) == 1


def test_nested_agents_md_within_depth(tmp_path: Path) -> None:
    nested = tmp_path / "projects" / "shop" / "api"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text("nested agents\n", encoding="utf-8")
    paths = discover_instruction_files(tmp_path)
    assert any(p.name == "AGENTS.md" for p in paths)
    block = format_instruction_files_block(tmp_path)
    assert "nested agents" in block
    assert "projects/shop/api/AGENTS.md" in block


def test_empty_tree_returns_empty_block(tmp_path: Path) -> None:
    assert discover_instruction_files(tmp_path) == []
    assert format_instruction_files_block(tmp_path) == ""
