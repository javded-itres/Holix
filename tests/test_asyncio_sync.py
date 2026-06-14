"""Sync/async bridge for messenger notifications."""

from __future__ import annotations

import pytest
from core.asyncio_sync import run_coroutine_sync


async def _returns_value() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_run_coroutine_sync_from_running_loop() -> None:
    assert run_coroutine_sync(_returns_value()) == "ok"


def test_run_coroutine_sync_without_running_loop() -> None:
    assert run_coroutine_sync(_returns_value()) == "ok"


@pytest.mark.asyncio
async def test_notify_access_approved_sync_from_running_loop(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cli.core as cli_core
    from integrations.telegram.access_requests import register_access_request
    from integrations.telegram.env_store import save_telegram_env
    from integrations.telegram.notify import notify_access_approved_sync

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="default")
    register_access_request("default", user_id=42, username="alice")

    captured: dict = {}

    async def _fake_send(token, chat_id, text, **kwargs):
        captured["token"] = token
        captured["chat_id"] = chat_id
        captured["text"] = text

    monkeypatch.setattr(
        "integrations.telegram.notify.send_user_message",
        _fake_send,
    )

    notify_access_approved_sync(
        "default",
        42,
        "alice",
        access_key="hp_secret123",
    )

    assert captured["chat_id"] == 42
    assert "hp_secret123" in captured["text"]
    assert "<b>Доступ одобрен</b>" in captured["text"]