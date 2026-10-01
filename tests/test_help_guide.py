"""Interactive `/help` scenario guide (Telegram / MAX)."""

from __future__ import annotations

import pytest
from core.host.help_guide import (
    HOME_CHILDREN,
    HOW_CHILDREN,
    SUB_CHILDREN,
    help_keyboard_rows,
    help_page_text,
    render_help_page,
    resolve_help_topic,
)


def test_resolve_aliases() -> None:
    assert resolve_help_topic("") == "home"
    assert resolve_help_topic("sub") == "sub"
    assert resolve_help_topic("субагенты") == "sub"
    assert resolve_help_topic("настройка") == "subc"
    assert resolve_help_topic("/skills") == "skill"


def test_how_to_work_menu_has_examples() -> None:
    assert resolve_help_topic("как") == "how"
    assert resolve_help_topic("промпт") == "howp"
    assert resolve_help_topic("документы") == "howd"
    rows = help_keyboard_rows("how", "ru")
    ids = [topic for row in rows for _, topic in row]
    for child in HOW_CHILDREN:
        assert child in ids
    assert ids[-1] == "home"
    for topic in ("how", "howa", "howp", "howc", "hows", "howd"):
        text = help_page_text(topic, "ru", html=True)
        assert len(text) < 3900
        assert "<b>" in text
    prompts = help_page_text("howp", "ru", html=False)
    assert "почини проект" in prompts
    assert "api/routers" in prompts
    assert "search_document" in help_page_text("howd", "en", html=False)
    assert "how" in [topic for row in help_keyboard_rows("home", "en") for _, topic in row]


def test_home_keyboard_lists_scenarios() -> None:
    rows = help_keyboard_rows("home", "ru")
    ids = [topic for row in rows for _, topic in row]
    assert "sub" in ids
    assert "sdd" in ids
    assert "cmds" in ids
    assert set(HOME_CHILDREN) <= set(ids)
    assert all(topic != "back" for topic in ids)


def test_sub_submenu_has_configure_and_back() -> None:
    rows = help_keyboard_rows("sub", "en")
    ids = [topic for row in rows for _, topic in row]
    for child in SUB_CHILDREN:
        assert child in ids
    assert ids[-1] == "home"
    labels = [label for row in rows for label, _ in row]
    assert any("Configure" in label for label in labels)
    assert labels[-1].startswith("←")


def test_sub_configure_page_covers_messenger_flow() -> None:
    ru = help_page_text("subc", "ru", html=False)
    assert "/subagent-types" in ru
    assert "/code-mode" in ru
    assert "types.json" in ru
    assert "native" in ru
    en = help_page_text("subc", "en", html=True)
    assert "<code>/subagent-types</code>" in en
    assert "<b>" in en
    assert len(en) < 3900


def test_render_help_page_html_and_buttons() -> None:
    html, rows = render_help_page("home", "en", html=True)
    assert "Holix" in html or "scenario" in html.lower() or "task" in html.lower()
    assert "<b>" in html
    assert rows
    assert rows[0][0][1] == "start"


def test_cmds_page_lists_slash_commands() -> None:
    text, _rows = render_help_page("cmds", "en", html=False)
    assert "/help" in text
    assert "/memory" in text
    html, _ = render_help_page(
        "cmds",
        "en",
        html=True,
        command_lines=[("help", "Usage guide"), ("status", "Status")],
    )
    assert "<code>/help</code>" in html
    assert "Usage guide" in html


def test_telegram_help_keyboard_callback_prefix() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import help_guide_keyboard, parse_callback

    rows = help_keyboard_rows("sub", "ru")
    kb = help_guide_keyboard(rows)
    data = kb.inline_keyboard[0][0].callback_data
    parsed = parse_callback(data)
    assert parsed == ("hp", rows[0][0][1])
    assert len(data) <= 64


@pytest.mark.asyncio
async def test_telegram_help_button_edits_the_same_message() -> None:
    pytest.importorskip("aiogram.types")
    from types import SimpleNamespace

    from integrations.telegram.interactive import TelegramInteractive

    edited: list[int] = []
    sent: list[str] = []

    async def edit_message_text(html, *, chat_id, message_id, parse_mode, reply_markup):
        edited.append(message_id)
        assert reply_markup is not None
        assert html

    async def send_html(html, reply_markup):
        sent.append("tg")

    host = SimpleNamespace(
        profile="default",
        _ui_message_id=55,
        _session=SimpleNamespace(chat_id=9),
        _bot=SimpleNamespace(edit_message_text=edit_message_text),
        _send_html_with_keyboard=send_html,
    )
    await TelegramInteractive(host).show_help_guide("sub")
    assert edited == [55]
    assert sent == []

    fresh = SimpleNamespace(
        profile="default",
        _session=SimpleNamespace(chat_id=9),
        _bot=SimpleNamespace(edit_message_text=edit_message_text),
        _send_html_with_keyboard=send_html,
    )
    await TelegramInteractive(fresh).show_help_guide("home")
    assert sent == ["tg"]


@pytest.mark.asyncio
async def test_max_help_button_edits_the_same_message() -> None:
    from types import SimpleNamespace

    from integrations.max.interactive import MaxInteractive

    edited: list[str] = []
    sent: list[str] = []

    async def edit_message(message_id, text, *, attachments):
        edited.append(message_id)
        assert text
        assert attachments

    async def send_text(text, keyboard):
        sent.append("max")

    host = SimpleNamespace(
        profile="default",
        _ui_message_id="mid-9",
        _session=SimpleNamespace(bot_profile="default", user_id=1),
        _client=SimpleNamespace(edit_message=edit_message),
        _send_text_with_keyboard=send_text,
    )
    await MaxInteractive(host).show_help_guide("home")
    assert edited == ["mid-9"]
    assert sent == []


def test_max_help_keyboard_payload() -> None:
    from integrations.max.keyboards import help_guide_keyboard, parse_callback

    rows = help_keyboard_rows("home", "ru")
    kb = help_guide_keyboard(rows)
    first = kb["payload"]["buttons"][0][0]
    parsed = parse_callback(first["payload"])
    assert parsed == ("hp", "start")
