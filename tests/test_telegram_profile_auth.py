"""Telegram sessions must not prompt for profile access keys after approval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cli.core import ProfileManager
from core.profile_keys import profile_has_access_key
from integrations.telegram.access_approval import approve_access_request
from integrations.telegram.access_requests import register_access_request
from integrations.telegram.agent_setup import create_agent
from integrations.telegram.bot import HolixTelegramBot
from integrations.telegram.config import TelegramSettings
from integrations.telegram.env_store import save_telegram_env
from integrations.telegram.profile_auth import (
    authorize_telegram_profile_access,
    init_profile_for_telegram,
    telegram_user_may_access_profile,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    cli_core._unlocked_profiles.clear()
    yield root
    cli_core._unlocked_profiles.clear()


def test_telegram_user_may_access_mapped_profile(holix_home) -> None:
    from integrations.telegram.user_profiles import set_user_profile

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 77, "lain")

    assert telegram_user_may_access_profile("shared", 77, "lain")
    assert not telegram_user_may_access_profile("shared", 77, "other")
    assert not telegram_user_may_access_profile("shared", 99, "lain")


def test_authorize_unlocks_mapped_profile_without_key(holix_home) -> None:
    import cli.core as cli_core
    from integrations.telegram.user_profiles import set_user_profile

    manager = ProfileManager()
    manager.create_profile("lain", with_access_key=True)
    assert profile_has_access_key("lain")

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 77, "lain")

    assert authorize_telegram_profile_access("shared", 77, "lain")
    assert "lain" in cli_core._unlocked_profiles


def test_init_profile_for_telegram_does_not_prompt(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.user_profiles import set_user_profile

    manager = ProfileManager()
    manager.create_profile("lain", with_access_key=True)

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 77, "lain")

    prompt = MagicMock(side_effect=AssertionError("must not prompt for profile key"))
    monkeypatch.setattr("typer.prompt", prompt)

    cfg = init_profile_for_telegram("lain", bot_profile="shared", telegram_user_id=77)
    assert cfg.profile_name == "lain"


@pytest.mark.asyncio
async def test_create_agent_seeds_llm_from_bot_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    import yaml
    from cli.core import ProfileManager
    from core.global_config import global_config_path
    from core.models.manager import ModelManager
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.user_profiles import set_user_profile

    global_config_path().parent.mkdir(parents=True, exist_ok=True)
    global_config_path().write_text("profile_name: _global\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("shared", inherit_global=True)
    bot_dir = manager.get_profile_dir("shared")
    (bot_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "profile_name": "shared",
                "default_provider": "litellm",
                "providers": {
                    "litellm": {
                        "base_url": "http://127.0.0.1:4000/v1",
                        "api_key": "sk-test",
                        "default_model": "gpt-4o-mini",
                    },
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    manager.create_profile("lain", with_access_key=True, inherit_global=True)
    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 77, "lain")

    fake_agent = MagicMock()
    fake_agent.initialize = AsyncMock()
    with patch("integrations.telegram.agent_setup.HolixAgent", return_value=fake_agent):
        await create_agent("lain", bot_profile="shared", telegram_user_id=77)

    mc = ModelManager(manager.load_profile("lain")).get_default_model_config()
    assert mc is not None
    assert mc.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_create_agent_after_approval_does_not_prompt(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile="shared",
    )
    register_access_request("shared", user_id=77, username="lain")
    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved_sync",
        lambda *args, **kwargs: None,
    )
    result = approve_access_request("shared", 77, create_profile="lain")
    assert result.holix_profile == "lain"
    assert profile_has_access_key("lain")

    prompt = MagicMock(side_effect=AssertionError("must not prompt for profile key"))
    monkeypatch.setattr("typer.prompt", prompt)

    fake_agent = MagicMock()
    fake_agent.initialize = AsyncMock()
    with patch("integrations.telegram.agent_setup.HolixAgent", return_value=fake_agent):
        agent = await create_agent(
            "lain",
            bot_profile="shared",
            telegram_user_id=77,
        )

    assert agent is fake_agent
    fake_agent.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_unlocks_keyed_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.user_profiles import set_user_profile

    manager = ProfileManager()
    manager.create_profile("lain", with_access_key=True)

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 77, "lain")

    prompt = MagicMock(side_effect=AssertionError("must not prompt for profile key"))
    monkeypatch.setattr("typer.prompt", prompt)

    bot = HolixTelegramBot(
        TelegramSettings(
            bot_token="1:abc",
            profile="shared",
            allowed_user_ids="77",
        )
    )

    fake_agent = MagicMock()
    fake_agent.initialize = AsyncMock()
    with patch("integrations.telegram.agent_setup.HolixAgent", return_value=fake_agent):
        session = await bot._get_session(chat_id=100, user_id=77)

    assert session.profile == "lain"
    assert session.agent is fake_agent