"""Tests for auto profile resolution in Telegram bot sessions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from integrations.telegram.bot import HelixTelegramBot
from integrations.telegram.config import TelegramSettings


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


@pytest.mark.asyncio
async def test_get_session_uses_mapped_profile(helix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.user_profiles import set_user_profile

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 999, "alice")

    settings = TelegramSettings(
        bot_token="1:abc",
        allowed_user_ids="999",
        profile="shared",
        allow_all=False,
    )
    bot = HelixTelegramBot(settings=settings)

    fake_agent = object()
    with patch(
        "integrations.telegram.agent_setup.create_agent",
        new=AsyncMock(return_value=fake_agent),
    ):
        session = await bot._get_session(chat_id=100, user_id=999)

    assert session.profile == "alice"
    assert session.conversation_id == "tg_alice_100"
    assert session.agent is fake_agent


@pytest.mark.asyncio
async def test_get_session_falls_back_to_bot_profile(helix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_TELEGRAM_USER_PROFILES", raising=False)
    settings = TelegramSettings(
        bot_token="1:abc",
        allowed_user_ids="999",
        profile="shared",
        allow_all=False,
    )
    bot = HelixTelegramBot(settings=settings)

    fake_agent = object()
    with patch(
        "integrations.telegram.agent_setup.create_agent",
        new=AsyncMock(return_value=fake_agent),
    ):
        session = await bot._get_session(chat_id=100, user_id=999)

    assert session.profile == "shared"
    assert session.conversation_id == "tg_shared_100"