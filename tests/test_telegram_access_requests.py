"""Telegram access-request flow."""

from __future__ import annotations

import pytest
from integrations.telegram.access_requests import (
    STATUS_PENDING,
    list_pending_requests,
    register_access_request,
    reject_access_request,
)
from integrations.telegram.allowlist import add_allowed_user, load_allowed_user_ids
from integrations.telegram.config import TelegramSettings
from integrations.telegram.user_profiles import resolve_user_profile


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


def test_register_access_request_creates_pending(helix_home) -> None:
    req, created = register_access_request(
        "default",
        user_id=42,
        username="alice",
        first_name="Alice",
    )
    assert created is True
    assert req.status == STATUS_PENDING
    assert req.user_id == 42
    pending = list_pending_requests("default")
    assert len(pending) == 1
    assert pending[0].username == "alice"


def test_register_access_request_idempotent_pending(helix_home) -> None:
    register_access_request("default", user_id=42, username="alice")
    _, created_again = register_access_request("default", user_id=42, username="alice2")
    assert created_again is False
    assert len(list_pending_requests("default")) == 1


def test_add_allowed_user_persists(helix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HELIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    add_allowed_user("default", 99)
    assert load_allowed_user_ids("default") == {99}


def test_access_requests_settings_default_true() -> None:
    settings = TelegramSettings(bot_token="1:abc")
    assert settings.access_requests is True
    assert settings.can_start_without_allowlist() is True
    assert not settings.is_user_allowed(1)


@pytest.mark.asyncio
async def test_run_polling_allows_access_request_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.bot import HelixTelegramBot

    monkeypatch.setattr(
        "integrations.telegram.bot.HelixTelegramBot.build",
        lambda self: (_ for _ in ()).throw(AssertionError("build should not run")),
    )
    bot = HelixTelegramBot(
        TelegramSettings(bot_token="123:abc", access_requests=True),
    )
    with pytest.raises(AssertionError, match="build should not run"):
        await bot.run_polling()


def test_approve_flow_maps_profile(helix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HELIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="default",
    )
    register_access_request("default", user_id=77, username="bob")
    add_allowed_user("default", 77)
    from integrations.telegram.user_profiles import set_user_profile

    set_user_profile("default", 77, "bob-profile")
    assert resolve_user_profile("default", 77) == "bob-profile"


def test_reject_access_request(helix_home) -> None:
    register_access_request("default", user_id=55)
    rejected = reject_access_request("default", 55)
    assert rejected is not None
    assert rejected.status == "rejected"
    assert list_pending_requests("default") == []