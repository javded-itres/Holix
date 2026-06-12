"""Tests for Holix env file patching."""

from __future__ import annotations

from api.services.env_store import patch_env_file


def test_patch_env_file_escapes_newlines(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text("EXISTING=1\n", encoding="utf-8")

    patch_env_file(path, {"INJECTED": "line1\nFAKE_KEY=evil"})

    text = path.read_text(encoding="utf-8")
    assert "FAKE_KEY=evil" not in text.splitlines()[1:]
    assert 'INJECTED="line1\\nFAKE_KEY=evil"' in text