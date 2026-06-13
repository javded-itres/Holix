"""Global install helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.installer.system import (
    MIN_PYTHON,
    detect_repo_root,
    ensure_path_in_shell,
    scripts_bin_dir,
)


def test_detect_repo_root() -> None:
    root = detect_repo_root()
    assert (root / "pyproject.toml").is_file()
    assert "holix" in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_scripts_bin_dir_user() -> None:
    path = scripts_bin_dir("python3", scope="user")
    assert path.name in ("bin", "Scripts")


def test_ensure_path_in_shell_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    rc = home / ".zshrc"
    rc.write_text("# shell\n", encoding="utf-8")
    monkeypatch.setattr("cli.installer.system.platform.system", lambda: "Linux")
    monkeypatch.setattr("cli.installer.system.Path.home", lambda: home)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    updated1, _ = ensure_path_in_shell(bin_dir)
    updated2, msg2 = ensure_path_in_shell(bin_dir)
    assert updated1 is True
    assert "updated" in msg2 or "already" in msg2
    assert "# holix" in rc.read_text(encoding="utf-8")


def test_min_python_version_tuple() -> None:
    assert MIN_PYTHON >= (3, 14)