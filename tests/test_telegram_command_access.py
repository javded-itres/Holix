"""Telegram command and menu access for non-admin users."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.admin import set_admin_user
from integrations.telegram.command_access import (
    ADMIN_ONLY_COMMANDS,
    commands_for_user,
    is_command_allowed,
    is_mcp_management_allowed,
    is_menu_action_allowed,
)
from integrations.telegram.commands import help_message_html
from integrations.telegram.env_store import save_telegram_env
from integrations.telegram.keyboards import status_menu_keyboard
from integrations.telegram.session import ChatSession


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


def _isolated_bot(bot_profile: str = "shared") -> None:
    import os

    os.environ.pop("HOLIX_TELEGRAM_ALLOW_ALL", None)
    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile=bot_profile,
    )
    set_admin_user(bot_profile, 900)


def test_non_admin_commands_filtered(holix_home) -> None:
    _isolated_bot()
    names = {spec.command for spec in commands_for_user("shared", 77, locale="en")}
    assert "help" in names
    assert "status" in names
    assert "cron" in names
    assert "mcp" in names
    assert ADMIN_ONLY_COMMANDS.isdisjoint(names)


def test_admin_sees_all_commands(holix_home) -> None:
    _isolated_bot()
    names = {spec.command for spec in commands_for_user("shared", 900, locale="en")}
    assert "message" in names
    assert "cron" in names
    assert "mcp" in names


def test_is_command_allowed_blocks_message_for_non_admin(holix_home) -> None:
    _isolated_bot()
    assert not is_command_allowed("message", "shared", 77)
    assert is_command_allowed("message", "shared", 900)
    assert is_command_allowed("help", "shared", 77)
    assert is_command_allowed("cron", "shared", 77)
    assert is_command_allowed("mcp", "shared", 77)


def test_help_html_hides_admin_commands_for_non_admin(holix_home) -> None:
    _isolated_bot()
    html = help_message_html("en", bot_profile="shared", user_id=77)
    assert "<code>/message</code>" not in html
    assert "<code>/cron</code>" in html
    assert "<code>/mcp</code>" in html
    assert "<code>/help</code>" in html


def test_status_menu_hides_profile_but_shows_cron_for_non_admin() -> None:
    pytest.importorskip("aiogram.types")
    kb = status_menu_keyboard("en", is_admin=False)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Profile" not in labels
    assert "Cron" in labels
    assert "Mode" in labels


def test_menu_action_allows_cron_for_non_admin(holix_home) -> None:
    _isolated_bot()
    assert is_menu_action_allowed("cron", "shared", 77)
    assert not is_menu_action_allowed("profile", "shared", 77)
    assert is_menu_action_allowed("profile", "shared", 900)


def test_mcp_management_admin_only_in_isolated_mode(holix_home) -> None:
    _isolated_bot()
    assert not is_mcp_management_allowed("shared", 77)
    assert is_mcp_management_allowed("shared", 900)


@pytest.mark.asyncio
async def test_interactive_allows_cron_for_non_admin(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolated_bot()
    from integrations.telegram.interactive import TelegramInteractive

    host = MagicMock()
    host._session = ChatSession(
        chat_id=1,
        user_id=77,
        profile="alice",
        conversation_id="tg_alice_1",
        bot_profile="shared",
    )
    host.profile = "alice"
    host._send_html_with_keyboard = AsyncMock()
    host._execution_modes = ["react"]
    host.streaming_enabled = False
    host.agent = None

    show_cron = AsyncMock()
    monkeypatch.setattr(TelegramInteractive, "show_cron_menu", show_cron)

    handled = await TelegramInteractive(host).handle_slash("/cron")
    assert handled is True
    show_cron.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_menu_read_only_for_non_admin(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolated_bot()
    from integrations.telegram.interactive import TelegramInteractive

    host = MagicMock()
    host._session = ChatSession(
        chat_id=1,
        user_id=77,
        profile="alice",
        conversation_id="tg_alice_1",
        bot_profile="shared",
    )
    host.profile = "alice"
    host._send_html_with_keyboard = AsyncMock()
    host._send_html = AsyncMock()

    monkeypatch.setattr(
        "cli.core.get_profile_manager",
        lambda: MagicMock(
            load_profile=MagicMock(return_value=MagicMock(mcp_servers={}, mcp_assignments={}))
        ),
    )

    await TelegramInteractive(host).show_mcp_menu("/mcp")
    kb = host._send_html_with_keyboard.await_args.args[1]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Install popular" not in " ".join(labels)
    assert "List" in " ".join(labels)