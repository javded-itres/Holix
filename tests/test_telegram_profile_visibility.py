"""Non-admin Telegram users must not see other profiles in isolated mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cli.core import ProfileManager
from cli.shared.commands.agent_commands import AgentCommands
from integrations.telegram.admin import set_admin_user
from integrations.telegram.env_store import save_telegram_env
from integrations.telegram.profile_visibility import (
    is_profile_list_hidden,
    list_visible_profiles,
)
from integrations.telegram.session import ChatSession
from integrations.telegram.user_profiles import set_user_profile


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


def _isolated_bot_env(bot_profile: str = "shared") -> None:
    import os

    os.environ.pop("HOLIX_TELEGRAM_ALLOW_ALL", None)
    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
        },
        profile=bot_profile,
    )


def test_non_admin_hides_profile_list(holix_home) -> None:
    _isolated_bot_env()
    set_admin_user("shared", 900)
    assert is_profile_list_hidden("shared", 77)
    assert not is_profile_list_hidden("shared", 900)


def test_allow_all_shows_profiles_to_everyone(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            "HOLIX_TELEGRAM_ALLOW_ALL": "true",
        },
        profile="open",
    )
    assert not is_profile_list_hidden("open", 77)


def test_visible_profiles_for_mapped_user(holix_home) -> None:
    _isolated_bot_env()
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=True)
    manager.create_profile("bob", inherit_global=True)
    set_user_profile("shared", 77, "alice")

    visible = list_visible_profiles("shared", 77, current="alice")
    assert visible == ["alice"]


def test_admin_sees_all_profiles(holix_home) -> None:
    _isolated_bot_env()
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=True)
    manager.create_profile("bob", inherit_global=True)
    set_admin_user("shared", 900)

    visible = list_visible_profiles("shared", 900, current="shared")
    assert "alice" in visible
    assert "bob" in visible


@pytest.mark.asyncio
async def test_profile_command_hides_list_for_non_admin(holix_home) -> None:
    _isolated_bot_env()
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=True)
    manager.create_profile("bob", inherit_global=True)
    set_user_profile("shared", 77, "alice")

    host = MagicMock()
    host.profile = "alice"
    host._session = ChatSession(
        chat_id=1,
        user_id=77,
        profile="alice",
        conversation_id="tg_alice_1",
        bot_profile="shared",
    )
    host._get_available_profiles.return_value = ["alice"]
    host.transcript_write = MagicMock()
    host.run_worker = MagicMock()

    await AgentCommands(host)._profile("/profile")

    text = host.transcript_write.call_args[0][0]
    assert "bob" not in text
    assert "alice" in text
    assert "ключ" in text.lower() or "access-key" in text.lower()


@pytest.mark.asyncio
async def test_profile_switch_with_key_allows_hidden_profile(holix_home) -> None:
    _isolated_bot_env()
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True, inherit_global=True)
    manager.create_profile("bob", with_access_key=True, inherit_global=True)
    bob_key = manager.pop_last_created_access_key()
    set_user_profile("shared", 77, "alice")

    host = MagicMock()
    host.profile = "alice"
    host._session = ChatSession(
        chat_id=1,
        user_id=77,
        profile="alice",
        conversation_id="tg_alice_1",
        bot_profile="shared",
    )
    host._get_available_profiles.return_value = ["alice"]
    host._switch_profile = AsyncMock()
    host.transcript_write = MagicMock()
    host.run_worker = MagicMock()

    await AgentCommands(host)._profile(f"/profile bob {bob_key}")

    host._switch_profile.assert_called_once_with("bob", profile_key=bob_key)
    host.run_worker.assert_called_once()