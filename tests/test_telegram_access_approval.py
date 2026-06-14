"""Telegram inline approval for access requests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.access_approval import (
    approve_access_request,
    handle_access_admin_callback,
    is_telegram_admin,
    reject_access_request_op,
    suggest_holix_profile_name,
)
from integrations.telegram.access_requests import register_access_request
from integrations.telegram.admin import set_admin_user
from integrations.telegram.allowlist import load_allowed_user_ids
from integrations.telegram.user_profiles import resolve_user_profile


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


def test_suggest_profile_from_username(holix_home) -> None:
    req, _ = register_access_request("default", user_id=1, username="Alice_Test")
    assert suggest_holix_profile_name(req) == "alice_test"


@pytest.mark.asyncio
async def test_admin_callback_approve(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    set_admin_user("default", 900)
    register_access_request("default", user_id=77, username="newbie")

    captured: dict = {}

    async def _fake_send(token, chat_id, text, **kwargs):
        captured["chat_id"] = chat_id
        captured["text"] = text

    monkeypatch.setattr(
        "integrations.telegram.notify.send_user_message",
        _fake_send,
    )

    message = MagicMock()
    message.edit_text = AsyncMock()
    msg = await handle_access_admin_callback(
        "default",
        actor_user_id=900,
        action="ara",
        value="77",
        message=message,
        bot=MagicMock(),
    )
    assert "одобрен" in msg.lower()
    assert "(уведомление:" not in msg.lower()
    assert load_allowed_user_ids("default") == {77}
    assert resolve_user_profile("default", 77) == "newbie"
    assert captured.get("chat_id") == 77
    assert "newbie" in captured.get("text", "")
    message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_admin_cannot_approve(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    set_admin_user("default", 900)
    register_access_request("default", user_id=77)

    msg = await handle_access_admin_callback(
        "default",
        actor_user_id=42,
        action="ara",
        value="77",
    )
    assert "администратор" in msg.lower()
    assert not is_telegram_admin("default", 42)


def test_reject_notifies_user(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    register_access_request("default", user_id=55, username="x")
    rejected_mock = MagicMock()
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_rejected_sync",
        rejected_mock,
    )
    result = reject_access_request_op("default", 55)
    assert "отклонён" in result.message.lower()
    rejected_mock.assert_called_once_with("default", 55)


def test_approve_creates_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import ProfileManager
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    register_access_request("default", user_id=88, username="carol")
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved_sync",
        lambda *args, **kwargs: None,
    )
    result = approve_access_request("default", 88)
    assert result.holix_profile == "carol"
    assert ProfileManager().profile_exists("carol")