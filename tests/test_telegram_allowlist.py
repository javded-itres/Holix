"""Telegram user allowlist — default-deny behavior."""

import pytest

from integrations.telegram.bot import HelixTelegramBot
from integrations.telegram.config import TelegramSettings


def test_default_deny_without_allowlist():
    settings = TelegramSettings(bot_token="123:abc")
    assert not settings.is_user_allowed(42)
    assert not settings.is_user_allowed(99)


def test_allowlist_permits_only_listed_users():
    settings = TelegramSettings(bot_token="123:abc", allowed_user_ids="42, 99")
    assert settings.is_user_allowed(42)
    assert settings.is_user_allowed(99)
    assert not settings.is_user_allowed(1)


def test_allow_all_permits_everyone():
    settings = TelegramSettings(bot_token="123:abc", allow_all=True)
    assert settings.is_user_allowed(1)
    assert settings.is_user_allowed(999999)


def test_bot_allowed_delegates_to_settings():
    bot = HelixTelegramBot(TelegramSettings(bot_token="123:abc", allowed_user_ids="7"))
    assert bot._allowed(7)
    assert not bot._allowed(8)


@pytest.mark.asyncio
async def test_run_polling_requires_allowlist_or_allow_all():
    bot = HelixTelegramBot(TelegramSettings(bot_token="123:abc"))
    with pytest.raises(RuntimeError, match="HELIX_TELEGRAM_ALLOWED_USERS"):
        await bot.run_polling()


@pytest.mark.asyncio
async def test_run_polling_allows_explicit_allow_all(monkeypatch):
    monkeypatch.setattr(
        "integrations.telegram.bot.HelixTelegramBot.build",
        lambda self: (_ for _ in ()).throw(AssertionError("build should not run")),
    )
    bot = HelixTelegramBot(
        TelegramSettings(bot_token="123:abc", allow_all=True),
    )
    with pytest.raises(AssertionError, match="build should not run"):
        await bot.run_polling()