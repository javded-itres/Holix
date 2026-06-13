"""Tests for GET /v1/models (LLM model list, not profiles)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_v1_models_returns_llm_models_not_profiles(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    from cli.core import ProfileManager

    manager = ProfileManager()
    manager.create_profile("docs", inherit_global=False)
    cfg = manager.load_profile("docs")
    cfg.providers = {
        "litellm": {
            "name": "litellm",
            "base_url": "http://localhost:4000/v1",
            "api_key": "sk-test",
            "default_model": "gpt-4o-mini",
            "available_models": ["gpt-4o-mini", "claude-3-5-sonnet"],
        }
    }
    manager.save_profile("docs", cfg)

    monkeypatch.setattr("api.state.host_profile", "docs")

    response = gateway_client.get("/v1/models", headers=gateway_auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    ids = {item["id"] for item in payload["data"]}
    assert "gpt-4o-mini" in ids
    assert "claude-3-5-sonnet" in ids
    assert "docs" not in ids
    assert "default" not in ids


def test_v1_models_respects_profile_header(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    from cli.core import ProfileManager

    manager = ProfileManager()
    manager.create_profile("alpha", inherit_global=False)
    manager.create_profile("beta", inherit_global=False)
    for name, model in (("alpha", "model-alpha"), ("beta", "model-beta")):
        cfg = manager.load_profile(name)
        cfg.model = model
        manager.save_profile(name, cfg)

    monkeypatch.setattr("api.state.host_profile", "alpha")

    response = gateway_client.get(
        "/v1/models",
        headers={**gateway_auth_headers, "X-Holix-Profile": "beta"},
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["data"]}
    assert ids == {"model-beta"}


def test_v1_models_live_probe_when_cache_empty(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    from cli.core import ProfileManager

    manager = ProfileManager()
    manager.create_profile("probe", inherit_global=False)
    cfg = manager.load_profile("probe")
    cfg.providers = {
        "ollama": {
            "name": "ollama",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "available_models": [],
        }
    }
    manager.save_profile("probe", cfg)
    monkeypatch.setattr("api.state.host_profile", "probe")

    fake_models = [{"id": "qwen2.5-coder:32b", "owned_by": "ollama", "created": 1}]
    with patch(
        "api.services.model_catalog.probe_provider",
        return_value=(True, fake_models, None),
    ):
        response = gateway_client.get(
            "/v1/models",
            headers=gateway_auth_headers,
        )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["data"]}
    assert ids == {"qwen2.5-coder:32b"}