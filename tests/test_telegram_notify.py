"""Telegram approval notifications."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from integrations.telegram.notify import format_access_approved_message


def test_format_access_approved_with_key() -> None:
    text = format_access_approved_message("ivan", access_key="hp_secret123")
    assert "ivan" in text
    assert "hp_secret123" in text
    assert "/profile" in text


def test_format_access_approved_open_profile() -> None:
    text = format_access_approved_message("default")
    assert "default" in text
    assert "hp_" not in text


@pytest.fixture
def helix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "helix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HELIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HELIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_approve_create_profile_sends_key(helix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.access_requests import register_access_request
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            "HELIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    register_access_request("default", user_id=42, username="alice")

    captured: dict = {}

    async def _fake_notify(bot_profile, user_id, profile, **kwargs):
        captured["bot_profile"] = bot_profile
        captured["user_id"] = user_id
        captured["profile"] = profile
        captured.update(kwargs)

    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved",
        _fake_notify,
    )

    from cli.commands.telegram_requests import telegram_requests_approve

    telegram_requests_approve(
        "default",
        42,
        create_profile="alice",
    )

    assert captured.get("access_key", "").startswith("hp_")
    assert captured.get("profile") == "alice"
    assert captured.get("user_id") == 42

    from core.profile_keys import profile_has_access_key

    assert profile_has_access_key("alice")