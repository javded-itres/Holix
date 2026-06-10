"""One Telegram bot serving many users — isolation and hot-reload access."""

from __future__ import annotations

import pytest
from integrations.telegram.bot import HelixTelegramBot
from integrations.telegram.config import TelegramSettings
from integrations.telegram.user_profiles import set_user_profile


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


def test_allowed_via_profile_mapping_without_allowlist_env(helix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HELIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="shared",
    )
    set_user_profile("shared", 1001, "alice")
    set_user_profile("shared", 1002, "bob")

    bot = HelixTelegramBot(
        TelegramSettings(
            bot_token="1:abc",
            profile="shared",
            access_requests=True,
        )
    )
    assert bot._allowed(1001)
    assert bot._allowed(1002)
    assert not bot._allowed(9999)


def test_allowed_hot_reload_after_cli_approve(helix_home) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HELIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="shared",
    )
    bot = HelixTelegramBot(
        TelegramSettings(
            bot_token="1:abc",
            profile="shared",
            access_requests=True,
        )
    )
    assert not bot._allowed(4242)

    set_user_profile("shared", 4242, "carol")
    assert bot._allowed(4242)


@pytest.mark.asyncio
async def test_sessions_isolated_per_chat(helix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 10, "alice")
    set_user_profile("shared", 20, "bob")

    bot = HelixTelegramBot(
        TelegramSettings(
            bot_token="1:abc",
            allowed_user_ids="10,20",
            profile="shared",
        )
    )

    fake_agents: dict[str, object] = {}

    async def _fake_create(profile: str):
        agent = object()
        fake_agents[profile] = agent
        return agent

    monkeypatch.setattr(
        "integrations.telegram.agent_setup.create_agent",
        _fake_create,
    )

    s_alice = await bot._get_session(chat_id=10, user_id=10)
    s_bob = await bot._get_session(chat_id=20, user_id=20)

    assert s_alice.profile == "alice"
    assert s_bob.profile == "bob"
    assert s_alice.conversation_id == "tg_alice_10"
    assert s_bob.conversation_id == "tg_bob_20"
    assert s_alice.agent is not s_bob.agent
    assert len(bot._sessions) == 2


@pytest.mark.asyncio
async def test_many_users_session_map_scales(helix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    user_count = 200
    for uid in range(1, user_count + 1):
        set_user_profile("shared", uid, f"user{uid}")

    bot = HelixTelegramBot(
        TelegramSettings(bot_token="1:abc", profile="shared", access_requests=True)
    )
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "integrations.telegram.agent_setup.create_agent",
        AsyncMock(side_effect=lambda profile: object()),
    )

    for uid in range(1, user_count + 1):
        assert bot._allowed(uid)
        session = await bot._get_session(chat_id=uid, user_id=uid)
        assert session.profile == f"user{uid}"

    assert len(bot._sessions) == user_count