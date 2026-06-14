"""MAX setup helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from integrations.max.config import load_max_settings
from integrations.max.env_store import (
    format_env_lines,
    mask_token,
    max_env_path,
    merge_project_env,
    save_max_env,
    token_looks_valid,
)
from integrations.max.models import user_id_from_update


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def _block_max_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "integrations.max.env_store.load_max_env_files",
        lambda profile=None: None,
    )


def test_token_looks_valid() -> None:
    assert token_looks_valid("a" * 20)
    assert not token_looks_valid("short")
    assert not token_looks_valid("has space inside token")


def test_mask_token() -> None:
    masked = mask_token("abcdefghijklmnop")
    assert "abcd" in masked
    assert "mnop" in masked
    assert "ghij" not in masked


def test_save_max_env(holix_home) -> None:
    path = save_max_env(
        {
            "MAX_ACCESS_TOKEN": "x" * 24,
            "HOLIX_MAX_ALLOWED_USERS": "42",
            "HOLIX_MAX_PROFILE": "default",
            "HOLIX_MAX_MODE": "polling",
        },
        profile="default",
    )
    assert path == max_env_path("default")
    text = path.read_text(encoding="utf-8")
    assert "MAX_ACCESS_TOKEN=" in text
    assert "HOLIX_MAX_ALLOWED_USERS=42" in text


def test_merge_project_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nMAX_ACCESS_TOKEN=old\n", encoding="utf-8")
    merge_project_env(
        env,
        {
            "MAX_ACCESS_TOKEN": "newtoken1234567890",
            "HOLIX_MAX_ALLOWED_USERS": "99",
        },
    )
    text = env.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert "MAX_ACCESS_TOKEN=newtoken1234567890" in text
    assert "old" not in text


def test_user_id_from_bot_started() -> None:
    uid = user_id_from_update({"update_type": "bot_started", "user": {"user_id": 555}})
    assert uid == 555


def test_poll_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.delenv("HELIX_MAX_POLL_TIMEOUT", raising=False)
    assert load_max_settings().poll_timeout_s == 5


def test_poll_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("HELIX_MAX_POLL_TIMEOUT", "15")
    assert load_max_settings().poll_timeout_s == 15


def test_poll_timeout_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("HELIX_MAX_POLL_TIMEOUT", "120")
    assert load_max_settings().poll_timeout_s == 90
    monkeypatch.setenv("HELIX_MAX_POLL_TIMEOUT", "not-a-number")
    assert load_max_settings().poll_timeout_s == 5


def test_format_env_lines() -> None:
    body = format_env_lines({"MAX_ACCESS_TOKEN": "t" * 20, "HOLIX_MAX_PROFILE": "work"})
    assert "MAX_ACCESS_TOKEN" in body
    assert "HOLIX_MAX_PROFILE=work" in body


def test_max_cli_registered() -> None:
    from cli.main import app
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["max", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "setup" in result.stdout
    assert "requests" in result.stdout