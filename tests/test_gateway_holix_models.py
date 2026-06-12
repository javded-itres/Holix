"""Tests for /api/holix/profiles/{id}/models routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_models_presets_and_fallbacks(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("models-test")

    presets = gateway_client.get(
        "/api/holix/profiles/models-test/models/presets",
        headers=gateway_auth_headers,
    )
    assert presets.status_code == 200
    data = presets.json()
    assert data["count"] > 0
    assert any(p["id"] == "ollama" for p in data["presets"])

    fallbacks = gateway_client.patch(
        "/api/holix/profiles/models-test/models/fallbacks",
        headers=gateway_auth_headers,
        json={"providers": []},
    )
    assert fallbacks.status_code == 200
    assert fallbacks.json()["reload_required"] is True

    agents = gateway_client.patch(
        "/api/holix/profiles/models-test/models/agent-models",
        headers=gateway_auth_headers,
        json={"agent_models": {"main": {"provider": "ollama", "model": "qwen", "temperature": 0.5}}},
    )
    assert agents.status_code == 200
    assert agents.json()["agent_models"]["main"]["model"] == "qwen"


def test_add_provider_skip_test(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("provider-test")

    added = gateway_client.post(
        "/api/holix/profiles/provider-test/models/providers",
        headers=gateway_auth_headers,
        json={"preset_id": "ollama", "skip_test": True},
    )
    assert added.status_code == 200
    assert added.json()["reload_required"] is True

    listed = gateway_client.get(
        "/api/holix/profiles/provider-test/models/providers",
        headers=gateway_auth_headers,
    )
    assert listed.status_code == 200
    assert "ollama" in listed.json()["providers"]