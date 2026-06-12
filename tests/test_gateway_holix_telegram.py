"""Tests for /api/holix/profiles/{id}/telegram routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

_TELEGRAM_ENV_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "HOLIX_TELEGRAM_BOT_TOKEN",
    "HOLIX_TELEGRAM_ALLOWED_USERS",
    "HOLIX_TELEGRAM_ACCESS_REQUESTS",
    "HOLIX_TELEGRAM_ALLOW_ALL",
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    for key in _TELEGRAM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


@pytest.fixture
def telegram_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import asyncio

    import api.deps
    import api.gateway
    import api.state
    from fastapi.testclient import TestClient

    mock_companions = MagicMock()
    mock_companions.status = MagicMock(return_value={"telegram_running": True, "cron_running": False})
    mock_companions.reload = AsyncMock(return_value={"telegram_running": True, "cron_running": False})

    async def _fake_key():
        return {"permissions": ["read", "write", "execute", "admin"], "rate_limit": 1000}

    monkeypatch.setattr(api.state, "companions", mock_companions)
    monkeypatch.setattr(api.state, "host_profile", "default")
    monkeypatch.setattr(api.state, "_agent_request_lock", asyncio.Lock())

    api.gateway.app.dependency_overrides[api.deps.verify_api_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.verify_admin_key] = _fake_key

    client = TestClient(api.gateway.app)
    yield client
    api.gateway.app.dependency_overrides.clear()


def test_telegram_status_unconfigured(
    holix_home: Path,
    telegram_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("tg-bot")

    response = telegram_client.get(
        "/api/holix/profiles/tg-bot/telegram/status",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "tg-bot"
    assert body["configured"] is False


def test_telegram_setup(
    holix_home: Path,
    telegram_client: TestClient,
    gateway_auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("tg-setup")

    async def _fake_verify(_token: str):
        return {"id": 999, "username": "holix_test_bot", "first_name": "Holix"}

    monkeypatch.setattr(
        "api.services.telegram_ops.verify_bot_token",
        _fake_verify,
    )

    response = telegram_client.post(
        "/api/holix/profiles/tg-setup/telegram/setup",
        headers=gateway_auth_headers,
        json={"bot_token": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bot_username"] == "holix_test_bot"
    assert "token_masked" in body
    assert body["reload_required"] is False

    status = telegram_client.get(
        "/api/holix/profiles/tg-setup/telegram/status",
        headers=gateway_auth_headers,
    )
    assert status.json()["configured"] is True


def test_telegram_requests_approve_reject(
    holix_home: Path,
    telegram_client: TestClient,
    gateway_auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services.telegram_ops import seed_pending_request_for_tests
    from cli.core import ProfileManager

    ProfileManager().create_profile("tg-req")
    ProfileManager().create_profile("alice")
    seed_pending_request_for_tests("tg-req", 4242, username="alice_user")

    monkeypatch.setattr(
        "integrations.telegram.notify.notify_access_approved_sync",
        lambda *args, **kwargs: None,
    )

    listed = telegram_client.get(
        "/api/holix/profiles/tg-req/telegram/requests",
        headers=gateway_auth_headers,
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    approved = telegram_client.post(
        "/api/holix/profiles/tg-req/telegram/requests/4242/approve",
        headers=gateway_auth_headers,
        json={"profile": "alice"},
    )
    assert approved.status_code == 200
    assert approved.json()["holix_profile"] == "alice"

    seed_pending_request_for_tests("tg-req", 5555)
    rejected = telegram_client.post(
        "/api/holix/profiles/tg-req/telegram/requests/5555/reject",
        headers=gateway_auth_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_telegram_map_and_admin(
    holix_home: Path,
    telegram_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager
    from integrations.telegram.env_store import save_telegram_env

    ProfileManager().create_profile("tg-map")
    save_telegram_env({"TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, profile="tg-map")

    mapped = telegram_client.post(
        "/api/holix/profiles/tg-map/telegram/map",
        headers=gateway_auth_headers,
        json={"user_id": 100, "profile": "default"},
    )
    assert mapped.status_code == 200

    listing = telegram_client.get(
        "/api/holix/profiles/tg-map/telegram/map",
        headers=gateway_auth_headers,
    )
    assert listing.json()["map"]["100"] == "default"

    admin = telegram_client.get(
        "/api/holix/profiles/tg-map/telegram/admin",
        headers=gateway_auth_headers,
    )
    assert admin.status_code == 200
    assert admin.json()["assigned"] is False


def test_telegram_sync_menu(
    holix_home: Path,
    telegram_client: TestClient,
    gateway_auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.core import ProfileManager
    from integrations.telegram.env_store import save_telegram_env

    ProfileManager().create_profile("tg-sync")
    save_telegram_env({"TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, profile="tg-sync")

    async def _fake_sync(_profile: str):
        return ["start", "models", "help"]

    monkeypatch.setattr(
        "integrations.telegram.commands.sync_bot_menu",
        _fake_sync,
    )

    response = telegram_client.post(
        "/api/holix/profiles/tg-sync/telegram/sync-menu",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    assert "models" in response.json()["commands"]