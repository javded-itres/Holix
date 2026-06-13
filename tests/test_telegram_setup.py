"""Telegram interactive setup helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from integrations.telegram.env_store import (
    format_env_lines,
    load_telegram_env_files,
    mask_token,
    merge_project_env,
    save_telegram_env,
    token_looks_valid,
)
from integrations.telegram.setup_api import _user_id_from_update


def test_token_looks_valid() -> None:
    assert token_looks_valid("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    assert not token_looks_valid("bad-token")


def test_mask_token() -> None:
    masked = mask_token("12345:ABCDEFghijklmnop")
    assert "12345" in masked
    assert "ABCDEF" not in masked


def test_load_telegram_env_overrides_empty_shell_token(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:from_profile_env"}, profile="default")
    load_telegram_env_files("default")
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "1:from_profile_env"


def test_save_telegram_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))

    path = save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ALLOWED_USERS": "42",
        },
        profile="default",
    )
    text = path.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=1:abc" in text
    assert "HOLIX_TELEGRAM_ALLOWED_USERS=42" in text


def test_merge_project_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nTELEGRAM_BOT_TOKEN=old\n", encoding="utf-8")
    merge_project_env(
        env,
        {
            "TELEGRAM_BOT_TOKEN": "2:newtoken",
            "HOLIX_TELEGRAM_ALLOWED_USERS": "99",
        },
    )
    text = env.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert "TELEGRAM_BOT_TOKEN=2:newtoken" in text
    assert "old" not in text


def test_user_id_from_update() -> None:
    uid = _user_id_from_update(
        {"update_id": 1, "message": {"from": {"id": 12345}, "text": "/start"}}
    )
    assert uid == 12345


def test_format_env_lines() -> None:
    body = format_env_lines({"TELEGRAM_BOT_TOKEN": "1:x", "HOLIX_TELEGRAM_PROFILE": "work"})
    assert "holix telegram setup" in body.lower() or "Holix Telegram" in body