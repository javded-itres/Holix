"""Holix .env loading from ~/.holix."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from core.env_loader import bootstrap_env, holix_env_path, init_holix_home


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_holix_env_overrides_project(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_TEST_VAR", raising=False)
    (holix_home / ".env").write_text("HOLIX_TEST_VAR=from_helix\n", encoding="utf-8")
    (holix_home / "project.env").unlink(missing_ok=True)
    holix_home / ".env"
    # project .env is cwd - same dir here, write a separate project file via chdir subdir
    proj_dir = holix_home / "repo"
    proj_dir.mkdir()
    (proj_dir / ".env").write_text("HOLIX_TEST_VAR=from_project\n", encoding="utf-8")
    monkeypatch.chdir(proj_dir)

    bootstrap_env(force=True)
    assert os.environ.get("HOLIX_TEST_VAR") == "from_helix"


def test_shell_env_wins_over_files(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_TEST_VAR", "from_shell")
    holix_env_path().write_text("HOLIX_TEST_VAR=from_helix\n", encoding="utf-8")

    bootstrap_env(force=True)
    assert os.environ.get("HOLIX_TEST_VAR") == "from_shell"


def test_project_env_used_when_holix_missing(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_TEST_VAR", raising=False)
    proj_dir = holix_home / "repo"
    proj_dir.mkdir()
    (proj_dir / ".env").write_text("HOLIX_TEST_VAR=from_project\n", encoding="utf-8")
    monkeypatch.chdir(proj_dir)

    bootstrap_env(force=True)
    assert os.environ.get("HOLIX_TEST_VAR") == "from_project"


def test_init_holix_home_seeds_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holix = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(holix))
    monkeypatch.chdir(tmp_path)
    template = tmp_path / ".env.example"
    template.write_text("HOLIX_TEST_VAR=seeded\nHOLIX_GATEWAY_PORT=9000\n", encoding="utf-8")

    init_holix_home()
    assert holix.is_dir()
    assert (holix / ".env.example").read_text(encoding="utf-8") == template.read_text(encoding="utf-8")
    assert (holix / ".env").read_text(encoding="utf-8") == template.read_text(encoding="utf-8")

    # Idempotent: existing files are not overwritten.
    (holix / ".env").write_text("HOLIX_TEST_VAR=custom\n", encoding="utf-8")
    init_holix_home()
    assert (holix / ".env").read_text(encoding="utf-8") == "HOLIX_TEST_VAR=custom\n"


def test_init_holix_home_uses_repo_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert (repo_root / ".env.example").is_file()

    holix = tmp_path / "new_holix_home"
    assert not holix.exists()
    monkeypatch.setenv("HOLIX_HOME", str(holix))
    monkeypatch.chdir(repo_root)

    init_holix_home()
    assert holix.is_dir()
    assert (holix / ".env.example").is_file()
    assert (holix / ".env").is_file()
    assert "HOLIX_GATEWAY_HOST" in (holix / ".env").read_text(encoding="utf-8")


def test_empty_values_not_set(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    holix_env_path().write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")

    bootstrap_env(force=True)
    assert "TELEGRAM_BOT_TOKEN" not in os.environ


def test_legacy_helix_env_aliases_mapped_to_holix(
    holix_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLIX_DOCS_CHAT_ENABLED", raising=False)
    monkeypatch.delenv("HELIX_DOCS_CHAT_ENABLED", raising=False)
    monkeypatch.delenv("HOLIX_DOCS_CHAT_TOKEN", raising=False)
    monkeypatch.delenv("HELIX_DOCS_CHAT_TOKEN", raising=False)
    holix_env_path().write_text(
        "HELIX_DOCS_CHAT_ENABLED=1\n"
        "HELIX_DOCS_CHAT_TOKEN=legacy-secret\n",
        encoding="utf-8",
    )

    bootstrap_env(force=True)
    assert os.environ.get("HOLIX_DOCS_CHAT_ENABLED") == "1"
    assert os.environ.get("HOLIX_DOCS_CHAT_TOKEN") == "legacy-secret"


def test_holix_env_wins_over_legacy_helix_alias(
    holix_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLIX_DOCS_CHAT_ENABLED", raising=False)
    monkeypatch.delenv("HELIX_DOCS_CHAT_ENABLED", raising=False)
    holix_env_path().write_text(
        "HELIX_DOCS_CHAT_ENABLED=1\nHOLIX_DOCS_CHAT_ENABLED=0\n",
        encoding="utf-8",
    )

    bootstrap_env(force=True)
    assert os.environ.get("HOLIX_DOCS_CHAT_ENABLED") == "0"