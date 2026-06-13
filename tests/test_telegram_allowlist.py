"""Telegram user allowlist — default-deny behavior."""

import pytest
from integrations.telegram.bot import HolixTelegramBot
from integrations.telegram.config import TelegramSettings


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


def test_bot_allowed_delegates_to_settings(holix_home, monkeypatch: pytest.MonkeyPatch):
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {"TELEGRAM_BOT_TOKEN": "123:abc", "HOLIX_TELEGRAM_ALLOWED_USERS": "7"},
        profile="default",
    )
    bot = HolixTelegramBot(TelegramSettings(bot_token="123:abc", allowed_user_ids="7"))
    assert bot._allowed(7)
    assert not bot._allowed(8)


@pytest.mark.asyncio
async def test_run_polling_requires_allowlist_or_allow_all():
    bot = HolixTelegramBot(
        TelegramSettings(bot_token="123:abc", access_requests=False),
    )
    with pytest.raises(RuntimeError, match="HOLIX_TELEGRAM_ALLOWED_USERS"):
        await bot.run_polling()


@pytest.mark.asyncio
async def test_run_polling_allows_explicit_allow_all(monkeypatch):
    monkeypatch.setattr(
        "integrations.telegram.bot.HolixTelegramBot.build",
        lambda self: (_ for _ in ()).throw(AssertionError("build should not run")),
    )
    bot = HolixTelegramBot(
        TelegramSettings(bot_token="123:abc", allow_all=True),
    )
    with pytest.raises(AssertionError, match="build should not run"):
        await bot.run_polling()