"""Refresh and default-model updates for connected providers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from core.models.provider_models import (
    refresh_provider_config,
    replace_provider_models,
    set_provider_default_model,
)


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        default_provider="hub",
        model="old",
        providers={
            "hub": {
                "name": "hub",
                "base_url": "http://hub/v1",
                "api_key": "sk-test",
                "default_model": "old",
                "available_models": ["old", "gone"],
                "model_contexts": {"old": 8192},
            },
            "other": {
                "name": "other",
                "base_url": "http://other/v1",
                "api_key": "k",
                "default_model": "keep",
                "available_models": ["keep", "extra"],
            },
        },
        agent_models={
            "main": {"provider": "hub", "model": "old", "temperature": 0.7},
            "researcher": {"provider": "hub", "model": "gone", "temperature": 0.2},
            "side": {"provider": "other", "model": "keep", "temperature": 0.2},
        },
    )


def test_replace_provider_models_updates_list_and_retargets_stale_agents():
    cfg = _config()
    stats = replace_provider_models(
        cfg,
        "hub",
        [
            {"id": "old", "context_length": 16384},
            {"id": "new", "context_length": 32000},
        ],
    )
    assert stats.added == ["new"]
    assert stats.removed == ["gone"]
    assert stats.default_model == "old"
    hub = cfg.providers["hub"]
    assert hub["available_models"] == ["old", "new"]
    assert hub["model_contexts"]["new"] == 32000
    assert hub["model_contexts"]["old"] == 16384
    assert cfg.model == "old"
    assert cfg.agent_models["main"]["model"] == "old"
    assert cfg.agent_models["researcher"]["model"] == "old"
    assert cfg.agent_models["side"]["model"] == "keep"


def test_replace_drops_missing_default_on_profile_provider():
    cfg = _config()
    stats = replace_provider_models(cfg, "hub", [{"id": "only"}])
    assert stats.default_model == "only"
    assert cfg.model == "only"
    assert cfg.providers["hub"]["default_model"] == "only"
    assert cfg.agent_models["main"]["model"] == "only"
    assert cfg.agent_models["researcher"]["model"] == "only"


def test_set_default_on_profile_provider_updates_main():
    cfg = _config()
    chosen = set_provider_default_model(cfg, "hub", "new-alias")
    assert chosen == "new-alias"
    assert cfg.providers["hub"]["default_model"] == "new-alias"
    assert "new-alias" in cfg.providers["hub"]["available_models"]
    assert cfg.model == "new-alias"
    assert cfg.agent_models["main"]["model"] == "new-alias"
    assert cfg.agent_models["researcher"]["model"] == "gone"


def test_set_default_on_secondary_provider_leaves_profile_model():
    cfg = _config()
    set_provider_default_model(cfg, "other", "extra")
    assert cfg.providers["other"]["default_model"] == "extra"
    assert cfg.model == "old"
    assert cfg.agent_models["main"]["model"] == "old"
    assert cfg.default_provider == "hub"


def test_set_default_unknown_provider():
    cfg = _config()
    with pytest.raises(ValueError, match="Unknown provider"):
        set_provider_default_model(cfg, "missing", "x")


def test_refresh_provider_config_probes_and_writes(monkeypatch: pytest.MonkeyPatch):
    cfg = _config()

    async def _probe(base_url, api_key, metadata):
        assert base_url == "http://hub/v1"
        assert api_key == "sk-test"
        return True, [{"id": "fresh", "context_length": 1000}], None

    monkeypatch.setattr("core.models.provider_models.probe_provider", _probe)
    stats = asyncio.run(refresh_provider_config(cfg, "hub"))
    assert stats.models == ["fresh"]
    assert cfg.providers["hub"]["default_model"] == "fresh"
    assert cfg.model == "fresh"
