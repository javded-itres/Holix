"""Telegram integration as a Holix extension."""

from __future__ import annotations

from typing import Any

from core.extensions.base import CAPABILITY_CLI, CAPABILITY_HTTP, ExtensionBase


class TelegramExtension(ExtensionBase):
    name = "telegram"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    description = "Telegram bot: setup, run, and gateway management API"
    capabilities = frozenset({CAPABILITY_CLI, CAPABILITY_HTTP})
    permissions = frozenset({"network", "gateway", "tools"})

    def register_cli(self, root: Any) -> None:
        from cli.commands.telegram import register_telegram_command

        register_telegram_command(root)


def get_extension() -> TelegramExtension:
    return TelegramExtension()