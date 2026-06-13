"""Telegram administrator profile and notifications."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.access_requests import register_access_request
from integrations.telegram.admin import (
    clear_admin_user,
    load_admin_holix_profile,
    load_admin_user_id,
    set_admin_user,
)
from integrations.telegram.notify import format_access_request_admin_message


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


def test_set_and_load_admin_user(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    set_admin_user("default", 1001)
    assert load_admin_user_id("default") == 1001
    assert load_admin_holix_profile("default") == "admin"


def test_clear_admin_user(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    set_admin_user("default", 1001)
    assert clear_admin_user("default") is True
    assert load_admin_user_id("default") is None


def test_format_access_request_admin_message(holix_home) -> None:
    req, _ = register_access_request(
        "default",
        user_id=55,
        username="bob",
        first_name="Bob",
    )
    text = format_access_request_admin_message(req, "default")
    assert "55" in text
    assert "Одобрите" in text or "кнопками" in text
    assert "Bob" in text


@pytest.mark.asyncio
async def test_notify_admin_access_request_skips_without_admin(
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.notify import notify_admin_access_request

    save_telegram_env(
        {"TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"},
        profile="default",
    )
    req, _ = register_access_request("default", user_id=77)
    send_mock = AsyncMock()
    monkeypatch.setattr(
        "integrations.telegram.notify.send_user_message",
        send_mock,
    )
    await notify_admin_access_request("default", req)
    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_admin_access_request_sends_to_admin(
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.notify import notify_admin_access_request

    save_telegram_env(
        {"TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"},
        profile="default",
    )
    set_admin_user("default", 900)
    req, _ = register_access_request("default", user_id=77, username="newbie")
    send_mock = AsyncMock()
    bot_instance = MagicMock()
    bot_instance.send_message = send_mock
    bot_instance.session = MagicMock()
    bot_instance.session.close = AsyncMock()

    class _FakeBot:
        def __init__(self, token: str) -> None:
            pass

        async def __aenter__(self):
            return bot_instance

        def __call__(self, token: str):
            return bot_instance

    monkeypatch.setattr("aiogram.Bot", lambda token: bot_instance)
    await notify_admin_access_request("default", req)
    send_mock.assert_awaited_once()
    assert send_mock.await_args.args[0] == 900


def test_approve_set_admin_creates_admin_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    register_access_request("default", user_id=42, username="admin_user")

    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved_sync",
        lambda *args, **kwargs: None,
    )

    from cli.commands.telegram_requests import telegram_requests_approve

    telegram_requests_approve("default", 42, set_admin=True)

    assert load_admin_user_id("default") == 42
    from integrations.telegram.user_profiles import resolve_user_profile

    assert resolve_user_profile("default", 42) == "admin"
    from cli.core import ProfileManager

    assert ProfileManager().profile_exists("admin")


def test_only_one_admin_allowed(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    set_admin_user("default", 1)
    register_access_request("default", user_id=2)

    from cli.commands.telegram_requests import telegram_requests_approve

    with pytest.raises(SystemExit):
        telegram_requests_approve("default", 2, set_admin=True)