"""Telegram plugin API: command merge, gates, extension registration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from integrations.telegram.plugin_api import (
    MessageGateResult,
    TelegramBotCommand,
    TelegramPluginAPI,
    apply_telegram_handlers,
    extension_bot_commands,
    load_telegram_plugins,
    run_message_gates,
    set_active_telegram_plugin_api,
)


def test_add_command_normalized():
    api = TelegramPluginAPI(bot_profile="default", settings=SimpleNamespace())
    api.add_command("/Pay", "Pay now")
    assert api.commands[0].command == "pay"
    assert api.commands[0].description == "Pay now"


@pytest.mark.asyncio
async def test_message_gates_first_deny_wins():
    api = TelegramPluginAPI(bot_profile="default", settings=SimpleNamespace())

    async def allow_gate(**kwargs):
        return MessageGateResult(allow=True)

    async def deny_gate(**kwargs):
        return MessageGateResult(allow=False, reply_text="blocked")

    api.add_message_gate(allow_gate)
    api.add_message_gate(deny_gate)
    result = await run_message_gates(
        api, user_id=1, chat_id=1, text="hi", is_command=False
    )
    assert result.allow is False
    assert result.reply_text == "blocked"


@pytest.mark.asyncio
async def test_apply_handlers_calls_registrars():
    api = TelegramPluginAPI(
        bot_profile="default",
        settings=SimpleNamespace(),
        bot=MagicMock(),
        dispatcher=MagicMock(),
    )
    seen = []

    def reg(a):
        seen.append(a)

    api.add_handlers(reg)
    apply_telegram_handlers(api)
    assert seen == [api]


def test_load_plugins_invokes_register_telegram(monkeypatch):
    class FakeExt:
        name = "fake_bill"

        def register_telegram(self, api):
            api.add_command("pay", "Pay")

    monkeypatch.setattr(
        "integrations.telegram.plugin_api._load_from_host_extensions",
        lambda api: FakeExt().register_telegram(api) or api._extensions_loaded.append("fake_bill"),
    )
    monkeypatch.setattr(
        "integrations.telegram.plugin_api._load_from_telegram_entrypoints",
        lambda api: None,
    )
    api = TelegramPluginAPI(bot_profile="default", settings=SimpleNamespace())
    names = load_telegram_plugins(api)
    assert "fake_bill" in names
    set_active_telegram_plugin_api(api)
    cmds = extension_bot_commands()
    assert any(c.command == "pay" for c in cmds)
    set_active_telegram_plugin_api(None)


def test_all_command_specs_includes_extension(monkeypatch):
    from integrations.telegram.commands import all_command_specs

    set_active_telegram_plugin_api(
        TelegramPluginAPI(
            bot_profile="default",
            settings=SimpleNamespace(),
            commands=[TelegramBotCommand("pay", "Pay")],
        )
    )
    try:
        specs = all_command_specs("en")
        assert any(s.command == "pay" for s in specs)
        assert any(s.command == "help" for s in specs)
    finally:
        set_active_telegram_plugin_api(None)
