"""Provider removal and LLM config resolution."""

from __future__ import annotations

from cli.core import ProfileConfig
from core.models.manager import ModelManager
from core.models.profile_cleanup import (
    profile_has_llm_config,
    remove_provider_from_profile,
    sanitize_model_routing_data,
)


def test_remove_last_provider_clears_legacy_and_agent_models():
    cfg = ProfileConfig(
        profile_name="t",
        model="qwen2.5-coder:32b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        default_provider="ollama",
        providers={
            "ollama": {
                "name": "ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "default_model": "qwen2.5-coder:32b",
                "available_models": ["qwen2.5-coder:32b"],
            }
        },
        agent_models={
            "researcher": {"provider": "ollama", "model": "llama3", "temperature": 0.5},
        },
    )

    remove_provider_from_profile(cfg, "ollama")

    assert cfg.providers == {}
    assert cfg.default_provider is None
    assert cfg.model == ""
    assert cfg.base_url == ""
    assert cfg.agent_models == {}
    assert ModelManager(cfg).get_default_model_config() is None
    assert not profile_has_llm_config(cfg)


def test_remove_one_of_two_providers_keeps_legacy_and_switches_default():
    cfg = ProfileConfig(
        profile_name="t",
        model="legacy-model",
        base_url="http://legacy/v1",
        default_provider="a",
        providers={
            "a": {
                "base_url": "http://a/v1",
                "api_key": "k",
                "default_model": "ma",
            },
            "b": {
                "base_url": "http://b/v1",
                "api_key": "k",
                "default_model": "mb",
            },
        },
        agent_models={"x": {"provider": "a", "model": "ma", "temperature": 0.7}},
    )

    remove_provider_from_profile(cfg, "a")

    assert "a" not in cfg.providers
    assert cfg.default_provider == "b"
    assert cfg.model == "legacy-model"
    assert "x" not in cfg.agent_models
    mc = ModelManager(cfg).get_default_model_config()
    assert mc is not None
    assert mc.provider == "b"


def test_legacy_only_profile_still_resolves():
    cfg = ProfileConfig(
        profile_name="t",
        model="m",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )
    mc = ModelManager(cfg).get_default_model_config()
    assert mc is not None
    assert mc.provider == "legacy"
    assert profile_has_llm_config(cfg)


def test_stale_default_provider_without_providers_returns_none():
    cfg = ProfileConfig(
        profile_name="t",
        model="qwen2.5-coder:32b",
        base_url="http://localhost:11434/v1",
        default_provider="ollama",
        providers={},
    )
    assert ModelManager(cfg).get_default_model_config() is None
    assert not profile_has_llm_config(cfg)


def test_sanitize_after_old_provider_removal():
    data = {
        "model": "qwen2.5-coder:32b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "providers": {},
        "default_provider": None,
        "agent_models": {"researcher": {"provider": "ollama", "model": "llama3"}},
    }
    clean = sanitize_model_routing_data(data)
    assert clean["agent_models"] == {}
    assert clean["model"] == ""
    assert clean["models_via_providers"] is True


def test_models_via_providers_blocks_legacy_after_all_removed():
    cfg = ProfileConfig(
        profile_name="t",
        model="qwen2.5-coder:32b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        models_via_providers=True,
        providers={},
        default_provider=None,
    )
    assert ModelManager(cfg).get_default_model_config() is None
    assert not profile_has_llm_config(cfg)