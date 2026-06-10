"""Helix .env loading from ~/.helix."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from core.env_loader import bootstrap_env, helix_env_path, init_helix_home


@pytest.fixture
def helix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_helix_env_overrides_project(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_TEST_VAR", raising=False)
    (helix_home / ".env").write_text("HELIX_TEST_VAR=from_helix\n", encoding="utf-8")
    (helix_home / "project.env").unlink(missing_ok=True)
    helix_home / ".env"
    # project .env is cwd - same dir here, write a separate project file via chdir subdir
    proj_dir = helix_home / "repo"
    proj_dir.mkdir()
    (proj_dir / ".env").write_text("HELIX_TEST_VAR=from_project\n", encoding="utf-8")
    monkeypatch.chdir(proj_dir)

    bootstrap_env(force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "from_helix"


def test_shell_env_wins_over_files(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_TEST_VAR", "from_shell")
    helix_env_path().write_text("HELIX_TEST_VAR=from_helix\n", encoding="utf-8")

    bootstrap_env(force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "from_shell"


def test_project_env_used_when_helix_missing(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_TEST_VAR", raising=False)
    proj_dir = helix_home / "repo"
    proj_dir.mkdir()
    (proj_dir / ".env").write_text("HELIX_TEST_VAR=from_project\n", encoding="utf-8")
    monkeypatch.chdir(proj_dir)

    bootstrap_env(force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "from_project"


def test_init_helix_home_seeds_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helix = tmp_path / "helix"
    monkeypatch.setenv("HELIX_HOME", str(helix))
    monkeypatch.chdir(tmp_path)
    template = tmp_path / ".env.example"
    template.write_text("HELIX_TEST_VAR=seeded\nHELIX_GATEWAY_PORT=9000\n", encoding="utf-8")

    init_helix_home()
    assert helix.is_dir()
    assert (helix / ".env.example").read_text(encoding="utf-8") == template.read_text(encoding="utf-8")
    assert (helix / ".env").read_text(encoding="utf-8") == template.read_text(encoding="utf-8")

    # Idempotent: existing files are not overwritten.
    (helix / ".env").write_text("HELIX_TEST_VAR=custom\n", encoding="utf-8")
    init_helix_home()
    assert (helix / ".env").read_text(encoding="utf-8") == "HELIX_TEST_VAR=custom\n"


def test_init_helix_home_uses_repo_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert (repo_root / ".env.example").is_file()

    helix = tmp_path / "new_helix_home"
    assert not helix.exists()
    monkeypatch.setenv("HELIX_HOME", str(helix))
    monkeypatch.chdir(repo_root)

    init_helix_home()
    assert helix.is_dir()
    assert (helix / ".env.example").is_file()
    assert (helix / ".env").is_file()
    assert "HELIX_GATEWAY_HOST" in (helix / ".env").read_text(encoding="utf-8")


def test_empty_values_not_set(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    helix_env_path().write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")

    bootstrap_env(force=True)
    assert "TELEGRAM_BOT_TOKEN" not in os.environ