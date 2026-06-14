"""MAX bot unauthorized / access-request flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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
async def test_bot_started_registers_access_request(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="bot")
    settings = MaxSettings(
        access_token="a" * 32,
        profile="bot",
        access_requests=True,
    )
    bot = HelixMaxBot(settings)
    client = MagicMock()
    client.send_message = AsyncMock(return_value={})
    monkeypatch.setattr(bot, "_notify_admin_new_request", AsyncMock())

    await bot.handle_update(
        client,
        {"update_type": "bot_started", "user": {"user_id": 555, "name": "Alice"}},
    )

    client.send_message.assert_awaited()
    from integrations.max.access_requests import list_pending_requests

    assert len(list_pending_requests("bot")) == 1


@pytest.mark.asyncio
async def test_allowed_user_passes(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env(
        {"MAX_ACCESS_TOKEN": "a" * 32, "HOLIX_MAX_ALLOWED_USERS": "555"},
        profile="bot",
    )
    settings = MaxSettings(
        access_token="a" * 32,
        profile="bot",
        allowed_user_ids="555",
        access_requests=True,
    )
    bot = HelixMaxBot(settings)
    monkeypatch.setattr(bot, "warmup", AsyncMock())
    monkeypatch.setattr(
        "integrations.max.commands.register_bot_commands",
        AsyncMock(return_value=[]),
    )
    client = MagicMock()
    client.send_message = AsyncMock(return_value={})

    await bot.handle_update(
        client,
        {"update_type": "bot_started", "user": {"user_id": 555}},
    )

    text_arg = client.send_message.await_args.args[0]
    assert "Запрос на доступ" not in text_arg