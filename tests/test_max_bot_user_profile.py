"""Tests for auto profile resolution in MAX bot sessions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from integrations.max.bot import HelixMaxBot
from integrations.max.config import MaxSettings


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


@pytest.mark.asyncio
async def test_get_session_uses_mapped_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import ProfileManager
    from integrations.max.env_store import save_max_env
    from integrations.max.user_profiles import set_user_profile

    ProfileManager().create_profile("shared", inherit_global=True)
    ProfileManager().create_profile("alice", inherit_global=True)
    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="shared")
    set_user_profile("shared", 999, "alice")

    settings = MaxSettings(
        access_token="a" * 32,
        allowed_user_ids="999",
        profile="shared",
        allow_all=False,
    )
    bot = HelixMaxBot(settings=settings)

    fake_agent = object()
    with patch(
        "integrations.max.bot.create_agent",
        new=AsyncMock(return_value=fake_agent),
    ):
        session = await bot._get_session(999, reply_user_id=999, reply_chat_id=None)

    assert session.profile == "alice"
    assert session.conversation_id == "max_shared_999"
    assert session.agent is fake_agent


@pytest.mark.asyncio
async def test_get_session_falls_back_to_bot_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("shared", inherit_global=True)
    settings = MaxSettings(
        access_token="a" * 32,
        allowed_user_ids="999",
        profile="shared",
        allow_all=False,
    )
    bot = HelixMaxBot(settings=settings)

    fake_agent = object()
    with patch(
        "integrations.max.bot.create_agent",
        new=AsyncMock(return_value=fake_agent),
    ):
        session = await bot._get_session(999, reply_user_id=999, reply_chat_id=None)

    assert session.profile == "shared"
    assert session.conversation_id == "max_shared_999"