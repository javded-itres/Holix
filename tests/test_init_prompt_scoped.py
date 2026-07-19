"""Scoped `/init` prompt for subdirectories."""

from __future__ import annotations

from core.project.init_prompt import _holix_md_rel_path, build_init_user_message


def test_holix_md_rel_path_for_subdirectory() -> None:
    assert _holix_md_rel_path("apps/api") == "apps/api/.holix/HOLIX.md"
    assert _holix_md_rel_path("") == ".holix/HOLIX.md"
    assert _holix_md_rel_path("  docs/  ") == "docs/.holix/HOLIX.md"


def test_build_init_user_message_includes_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "services" / "core").mkdir(parents=True)
    (tmp_path / "services" / "core" / "README.md").write_text("# Core\n", encoding="utf-8")
    msg = build_init_user_message(locale="en", target_dir="services/core")
    assert "services/core/.holix/HOLIX.md" in msg
    assert "services/core/" in msg
    assert (tmp_path / "services/core/.holix").is_dir()
    assert "Pre-scan" in msg
    assert "~20 `read_file`" in msg
    assert "skeleton file already exists" in msg
    assert "update_holix_section" in msg
    assert "patch_file" in msg
    assert "Never" in msg and "write_file" in msg