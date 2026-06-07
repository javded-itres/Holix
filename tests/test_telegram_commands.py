"""Telegram bot command menu."""

from integrations.telegram.commands import TELEGRAM_MENU_COMMANDS, command_specs, help_message_html


def test_menu_has_help_and_status() -> None:
    names = {c for c, _ in TELEGRAM_MENU_COMMANDS}
    assert "help" in names
    assert "status" in names
    assert "models" in names
    assert "compress" in names
    assert len(command_specs()) == len(TELEGRAM_MENU_COMMANDS)


def test_help_html_lists_commands() -> None:
    html = help_message_html()
    assert "<b>Helix" in html
    assert "<code>/help</code>" in html
    assert "<code>/memory</code>" in html
    assert "<code>/compress</code>" in html