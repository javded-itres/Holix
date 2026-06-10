"""Telegram /skills command delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.host import TelegramHost
from integrations.telegram.keyboards import SKILLS_PAGE_SIZE, skills_picker_keyboard


@pytest.mark.asyncio
async def test_send_html_split_chunks_long_message() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    session = MagicMock()
    session.chat_id = 1
    host = TelegramHost(bot, session)

    long_html = "<b>Skills</b>\n" + ("• <code>skill-name</code>\n" * 200)
    await host._send_html_split(long_html)

    assert bot.send_message.await_count >= 2
    for call in bot.send_message.await_args_list:
        assert len(call.args[1]) <= 4096


@pytest.mark.asyncio
async def test_run_skills_command_opens_picker_without_slot(tmp_path, monkeypatch) -> None:
    from cli.shared.commands.skills_commands import run_skills_command

    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    from cli.core import ProfileManager

    manager = ProfileManager()
    profile = "default"
    profile_dir = manager.get_profile_dir(profile)
    skills_dir = profile_dir / "data" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "demo-skill.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\n",
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text("profile_name: default\nmodel: test\n", encoding="utf-8")

    picker_called = False

    class Interactive:
        async def show_skills_picker(self, *, page: int = 0) -> None:
            nonlocal picker_called
            picker_called = True

    class S:
        chat_id = 1
        profile = "default"
        conversation_id = "tg_default_1"
        execution_modes = ["react"]
        execution_mode_index = 0
        streaming_enabled = False
        agent = None

    bot = MagicMock()
    bot.send_message = AsyncMock()
    host = TelegramHost(bot, S())
    host._interactive = Interactive()

    await run_skills_command(host, "/skills")
    assert picker_called is True
    bot.send_message.assert_not_awaited()


def test_skills_picker_keyboard_has_next_page() -> None:
    names = [f"skill-{i}" for i in range(SKILLS_PAGE_SIZE + 2)]
    kb = skills_picker_keyboard(names, page=0)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any(data.endswith(":skp:1") for data in flat)


@pytest.mark.asyncio
async def test_show_skills_picker_sends_keyboard(tmp_path, monkeypatch) -> None:
    from integrations.telegram.interactive import TelegramInteractive

    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    from cli.core import ProfileManager

    manager = ProfileManager()
    profile = "default"
    profile_dir = manager.get_profile_dir(profile)
    skills_dir = profile_dir / "data" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "alpha.md").write_text(
        "---\nname: alpha\ndescription: Alpha skill\n---\n",
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text("profile_name: default\nmodel: test\n", encoding="utf-8")

    class S:
        chat_id = 42
        profile = "default"
        conversation_id = "tg_default_42"
        execution_modes = ["react"]
        execution_mode_index = 0
        streaming_enabled = False
        agent = None
        ui_skills: list[str] = []
        ui_skills_page = 0

    bot = MagicMock()
    bot.send_message = AsyncMock()
    host = TelegramHost(bot, S())
    interactive = TelegramInteractive(host)

    await interactive.show_skills_picker()
    bot.send_message.assert_awaited_once()
    assert "alpha" in bot.send_message.await_args.args[1]
    assert bot.send_message.await_args.kwargs.get("reply_markup") is not None
    assert host._session.ui_skills == ["alpha"]