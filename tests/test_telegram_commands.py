"""Telegram bot command menu."""

from unittest.mock import AsyncMock

import pytest
from integrations.telegram.commands import (
    authorized_telegram_user_ids,
    clear_default_bot_menu,
    command_specs,
    enable_chat_menu,
    help_message_html,
    hide_chat_menu,
    register_bot_commands,
    telegram_menu_commands,
)


def test_menu_has_help_and_status() -> None:
    names = {c for c, _ in telegram_menu_commands("en")}
    assert "help" in names
    assert "status" in names
    assert "models" in names
    assert "compress" in names
    assert "lang" in names
    assert len(command_specs("en")) == len(telegram_menu_commands("en"))


def test_help_html_lists_commands_en() -> None:
    html = help_message_html("en")
    assert "Holix" in html
    assert "<code>/help</code>" in html
    assert "<code>/memory</code>" in html
    assert "<code>/compress</code>" in html
    assert "<code>/lang</code>" in html


def test_help_html_lists_commands_ru() -> None:
    html = help_message_html("ru")
    assert "команд" in html.lower()
    assert "<code>/lang</code>" in html


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


def test_authorized_user_ids_merges_allowlist_and_profiles(holix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.user_profiles import save_user_profiles

    save_telegram_env(
        {"HOLIX_TELEGRAM_ALLOWED_USERS": "100,200"},
        profile="default",
    )
    save_user_profiles("default", {300: "alice"})

    ids = authorized_telegram_user_ids("default")
    assert ids == {100, 200, 300}


@pytest.mark.asyncio
async def test_clear_default_bot_menu_deletes_global_commands() -> None:
    aiogram_types = pytest.importorskip("aiogram.types")
    bot = AsyncMock()
    await clear_default_bot_menu(bot)
    bot.delete_my_commands.assert_awaited_once()
    scope = bot.delete_my_commands.await_args.kwargs["scope"]
    assert isinstance(scope, aiogram_types.BotCommandScopeDefault)
    bot.set_chat_menu_button.assert_awaited_once()
    assert isinstance(
        bot.set_chat_menu_button.await_args.kwargs["menu_button"],
        aiogram_types.MenuButtonDefault,
    )


@pytest.mark.asyncio
async def test_hide_chat_menu_targets_private_chat() -> None:
    aiogram_types = pytest.importorskip("aiogram.types")
    bot = AsyncMock()
    await hide_chat_menu(bot, 4242)
    scope = bot.delete_my_commands.await_args.kwargs["scope"]
    assert isinstance(scope, aiogram_types.BotCommandScopeChat)
    assert scope.chat_id == 4242
    bot.set_chat_menu_button.assert_awaited_once_with(
        chat_id=4242,
        menu_button=aiogram_types.MenuButtonDefault(),
    )


@pytest.mark.asyncio
async def test_enable_chat_menu_sets_commands_for_chat() -> None:
    aiogram_types = pytest.importorskip("aiogram.types")
    bot = AsyncMock()
    names = await enable_chat_menu(bot, 99, locale="en")
    assert "help" in names
    scope = bot.set_my_commands.await_args.kwargs["scope"]
    assert isinstance(scope, aiogram_types.BotCommandScopeChat)
    assert scope.chat_id == 99
    bot.set_chat_menu_button.assert_awaited_once_with(
        chat_id=99,
        menu_button=aiogram_types.MenuButtonCommands(),
    )


@pytest.mark.asyncio
async def test_register_bot_commands_per_user_when_not_allow_all(
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:token",
            "HOLIX_TELEGRAM_ALLOWED_USERS": "42",
        },
        profile="default",
    )
    bot = AsyncMock()
    monkeypatch.setattr(
        "integrations.telegram.commands.clear_default_bot_menu",
        AsyncMock(),
    )
    enable_mock = AsyncMock(return_value=["help"])
    monkeypatch.setattr("integrations.telegram.commands.enable_chat_menu", enable_mock)

    names = await register_bot_commands(bot, locale="en", bot_profile="default")

    assert names == []
    enable_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_bot_commands_global_when_allow_all(
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:token",
            "HOLIX_TELEGRAM_ALLOW_ALL": "true",
        },
        profile="default",
    )
    bot = AsyncMock()
    global_mock = AsyncMock(return_value=["help", "status"])
    monkeypatch.setattr(
        "integrations.telegram.commands.register_global_bot_commands",
        global_mock,
    )

    names = await register_bot_commands(bot, locale="en", bot_profile="default")

    assert names == ["help", "status"]
    global_mock.assert_awaited_once_with(bot, locale="en")