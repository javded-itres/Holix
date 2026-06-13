"""Holix update system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cli.installer.manifest import InstallManifest, load_manifest, save_manifest
from cli.installer.update import (
    UpdateOptions,
    _parse_version,
    _read_project_version,
    _version_lt,
    resolve_update_context,
)


def test_version_compare() -> None:
    assert _version_lt("0.1.0", "0.2.0")
    assert not _version_lt("0.2.0", "0.1.0")
    assert _parse_version("v1.2.3") == (1, 2, 3)


def test_read_project_version() -> None:
    from cli import __version__

    root = Path(__file__).resolve().parents[1]
    assert _read_project_version(root) == __version__


def test_manifest_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.installer.manifest.HOLIX_HOME", tmp_path)
    monkeypatch.setattr("cli.installer.manifest.MANIFEST_PATH", tmp_path / "install.json")

    manifest = InstallManifest(
        version="0.1.0",
        method="uv-tool",
        scope="user",
        source="git",
        extras=["telegram"],
        installed_at="2026-01-01T00:00:00Z",
        repo_root="/tmp/Holix",
    )
    save_manifest(manifest)
    loaded = load_manifest()
    assert loaded is not None
    assert loaded.method == "uv-tool"
    assert loaded.extras == ["telegram"]


def test_resolve_update_context_from_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(__file__).resolve().parents[1]
    manifest_path = tmp_path / "install.json"
    monkeypatch.setattr("cli.installer.manifest.HOLIX_HOME", tmp_path)
    monkeypatch.setattr("cli.installer.manifest.MANIFEST_PATH", manifest_path)
    manifest_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "method": "pip",
                "scope": "user",
                "source": "git",
                "extras": [],
                "installed_at": "now",
                "repo_root": str(repo),
            }
        ),
        encoding="utf-8",
    )

    manifest, resolved_repo = resolve_update_context(UpdateOptions())
    assert manifest.source == "git"
    assert resolved_repo == repo