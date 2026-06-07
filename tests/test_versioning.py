"""Version bump helpers for local builds."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.versioning import (
    _BUILD_VERSION_ENV,
    bump_patch,
    bump_project_version,
    read_version,
    resolve_build_version,
    write_version,
)


def test_bump_patch() -> None:
    assert bump_patch("0.1.0") == "0.1.1"
    assert bump_patch("0.1.9") == "0.1.10"
    assert bump_patch("1.0.0") == "1.0.1"


def test_read_and_write_version(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "cli").mkdir()
    (root / "pyproject.toml").write_text('version = "0.2.3"\n', encoding="utf-8")
    (root / "cli" / "__init__.py").write_text('__version__ = "0.2.3"\n', encoding="utf-8")

    assert read_version(root) == "0.2.3"
    write_version("0.2.4", root)
    assert read_version(root) == "0.2.4"
    assert (root / "cli" / "__init__.py").read_text(encoding="utf-8").strip() == '__version__ = "0.2.4"'


def test_bump_project_version(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "cli").mkdir()
    (root / "pyproject.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
    (root / "cli" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    assert bump_project_version(root) == "0.1.1"
    assert read_version(root) == "0.1.1"


def test_resolve_build_version_bumps_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "cli").mkdir()
    (root / "pyproject.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
    (root / "cli" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    monkeypatch.delenv(_BUILD_VERSION_ENV, raising=False)
    monkeypatch.delenv("HELIX_NO_VERSION_BUMP", raising=False)

    first = resolve_build_version("0.1.0", root=root)
    second = resolve_build_version("0.1.0", root=root)
    assert first == "0.1.1"
    assert second == "0.1.1"
    assert read_version(root) == "0.1.1"


def test_resolve_build_version_respects_disable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "cli").mkdir()
    (root / "pyproject.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
    (root / "cli" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")

    monkeypatch.setenv("HELIX_NO_VERSION_BUMP", "1")
    monkeypatch.delenv(_BUILD_VERSION_ENV, raising=False)

    assert resolve_build_version("0.1.0", root=root) == "0.1.0"
    assert read_version(root) == "0.1.0"