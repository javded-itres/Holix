"""Tests for /api/holix/profiles management routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def holix_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import asyncio

    import api.deps
    import api.gateway
    import api.state
    from fastapi.testclient import TestClient

    mock_agent = AsyncMock()
    mock_agent._initialized = True
    mock_agent.run = AsyncMock(return_value="ok")
    mock_agent.get_tools = MagicMock(return_value=["read_file"])
    mock_agent.get_skills = MagicMock(return_value={})

    mock_companions = MagicMock()
    mock_companions.status = MagicMock(return_value={"telegram": "stopped", "cron": "stopped"})
    mock_companions.stop_cron = AsyncMock()
    mock_companions.stop_telegram = AsyncMock()
    mock_companions.stop_max = AsyncMock()
    mock_companions.reload = AsyncMock(return_value={"telegram": "started", "cron": "started"})

    mock_registry = MagicMock()
    mock_registry.get_agent = AsyncMock(return_value=mock_agent)
    mock_registry.entry = MagicMock(return_value=MagicMock(agent=mock_agent))
    mock_registry.list_loaded_profiles = MagicMock(return_value=[])
    mock_registry.reload = AsyncMock(return_value={"status": "reloaded"})

    async def _fake_key():
        return {"permissions": ["read", "write", "execute", "admin"], "rate_limit": 1000}

    async def _fake_registry():
        return mock_registry

    monkeypatch.setattr(api.state, "companions", mock_companions)
    monkeypatch.setattr(api.state, "registry", mock_registry)
    monkeypatch.setattr(api.state, "host_profile", "default")
    monkeypatch.setattr(api.state, "_agent_request_lock", asyncio.Lock())

    api.gateway.app.dependency_overrides[api.deps.verify_api_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.verify_admin_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.get_registry] = _fake_registry

    client = TestClient(api.gateway.app)
    yield client
    api.gateway.app.dependency_overrides.clear()


def test_profiles_require_api_key(holix_home: Path) -> None:
    import api.gateway

    client = TestClient(api.gateway.app)
    assert client.get("/api/holix/profiles").status_code == 401


def test_profiles_list_and_create(holix_home: Path, holix_client: TestClient, gateway_auth_headers: dict) -> None:
    listed = holix_client.get("/api/holix/profiles", headers=gateway_auth_headers)
    assert listed.status_code == 200
    assert "profiles" in listed.json()

    created = holix_client.post(
        "/api/holix/profiles",
        headers=gateway_auth_headers,
        json={"name": "tenant-a", "with_access_key": True},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["profile"] == "tenant-a"
    assert body["protected"] is True
    assert body["access_key"].startswith("hp_")

    detail = holix_client.get("/api/holix/profiles/tenant-a", headers=gateway_auth_headers)
    assert detail.status_code == 200
    assert detail.json()["protected"] is True


def test_profile_reload(
    holix_home: Path,
    holix_client: TestClient,
    gateway_auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("reload-me")
    monkeypatch.setattr(
        "cli.services.gateway_companions.reload_os_companions",
            lambda _profile: {
                "docs": "not_configured",
                "telegram_subprocess": "in_process",
                "max_subprocess": "in_process",
            },
    )

    response = holix_client.post(
        "/api/holix/profiles/reload-me/reload",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reloaded"
    assert body["profile"] == "reload-me"
    assert body["os_companions"]["telegram_subprocess"] == "in_process"


def test_profile_key_init(holix_home: Path, holix_client: TestClient, gateway_auth_headers: dict) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("open-profile")

    response = holix_client.post(
        "/api/holix/profiles/open-profile/key/init",
        headers=gateway_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_key"].startswith("hp_")
    assert body["reload_required"] is True