"""Tests for /api/holix/profiles/{id}/max routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.setenv("HOLIX_PROFILE", "default")
    monkeypatch.chdir(tmp_path)
    for key in (
        "MAX_ACCESS_TOKEN",
        "HOLIX_MAX_ACCESS_TOKEN",
        "HELIX_MAX_ACCESS_TOKEN",
        "HOLIX_MAX_ALLOWED_USERS",
        "HELIX_MAX_ALLOWED_USERS",
        "HOLIX_MAX_ACCESS_REQUESTS",
        "HELIX_MAX_ACCESS_REQUESTS",
    ):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


@pytest.fixture
def max_client(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import asyncio

    import api.deps
    import api.gateway
    import api.state
    from fastapi.testclient import TestClient

    mock_companions = MagicMock()
    mock_companions.status = MagicMock(return_value={"max_webhook": True})
    mock_companions.reload = AsyncMock(return_value={"max_webhook": True})

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


def test_max_status_unconfigured(
    holix_home: Path,
    max_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("max-bot")

    response = max_client.get(
        "/api/holix/profiles/max-bot/max/status",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "max-bot"
    assert body["configured"] is False, body


def test_max_requests_empty(
    holix_home: Path,
    max_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager
    from integrations.max.env_store import save_max_env

    ProfileManager().create_profile("max-bot")
    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="max-bot")

    response = max_client.get(
        "/api/holix/profiles/max-bot/max/requests",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_max_approve_request(
    holix_home: Path,
    max_client: TestClient,
    gateway_auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services import max_ops
    from cli.core import ProfileManager

    ProfileManager().create_profile("max-bot")
    max_ops.seed_pending_request_for_tests("max-bot", 12345, first_name="Tester")
    monkeypatch.setattr(
        "integrations.max.notify.notify_access_approved_sync",
        lambda *a, **k: None,
    )

    response = max_client.post(
        "/api/holix/profiles/max-bot/max/requests/12345/approve",
        headers=gateway_auth_headers,
        json={"create_profile": "tester"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["holix_profile"] == "tester"
    assert body["user_id"] == 12345