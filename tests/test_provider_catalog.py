"""Provider catalog and OpenAI client factory."""

from __future__ import annotations

import pytest
from core.models.catalog import (
    get_provider_preset,
    list_provider_presets,
    parse_host_value,
    resolve_preset_base_url,
)
from core.models.client_factory import (
    build_default_headers,
    resolve_provider_api_key,
    resolve_verify_ssl,
)
from core.models.setup_helpers import (
    apply_ssl_override,
    build_provider_entry,
    resolve_api_key_for_preset,
    resolve_ssl_metadata_extra,
)


def test_catalog_includes_major_providers():
    ids = {p.id for p in list_provider_presets()}
    assert "openai" in ids
    assert "openrouter" in ids
    assert "deepseek" in ids
    assert "moonshot" in ids
    assert "xai" in ids
    assert "groq" in ids
    assert "vllm" in ids


def test_ollama_litellm_vllm_configurable_host():
    for pid in ("ollama", "litellm", "vllm"):
        p = get_provider_preset(pid)
        assert p is not None
        assert p.configurable_host
        assert p.host_env
        assert p.default_port > 0


def test_parse_host_value():
    assert parse_host_value("192.168.1.5", default_port=11434) == "http://192.168.1.5:11434/v1"
    assert (
        parse_host_value("http://gpu.local:8000", default_port=8000)
        == "http://gpu.local:8000/v1"
    )
    assert (
        parse_host_value("http://nas:4000/v1", default_port=4000)
        == "http://nas:4000/v1"
    )


def test_resolve_preset_base_url_from_host():
    preset = get_provider_preset("ollama")
    assert preset is not None
    url = resolve_preset_base_url(preset, host="10.0.0.2:11434")
    assert url == "http://10.0.0.2:11434/v1"


def test_resolve_preset_base_url_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://192.168.88.10:11434")
    preset = get_provider_preset("ollama")
    assert preset is not None
    assert resolve_preset_base_url(preset) == "http://192.168.88.10:11434/v1"


def test_openrouter_preset_metadata():
    preset = get_provider_preset("openrouter")
    assert preset is not None
    meta = preset.default_metadata()
    assert meta["auth_type"] == "openrouter"
    assert "http_referer" in meta


def test_openrouter_headers_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.com")
    headers = build_default_headers({"auth_type": "openrouter", "x_title": "Holix"})
    assert headers.get("HTTP-Referer") == "https://example.com"
    assert headers.get("X-Title") == "Holix"


def test_resolve_api_key_placeholder():
    preset = get_provider_preset("openai")
    assert preset is not None
    key = resolve_api_key_for_preset(preset, use_env_value=False)
    assert key == "${OPENAI_API_KEY}"


def test_resolve_api_key_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    preset = get_provider_preset("deepseek")
    assert preset is not None
    assert resolve_provider_api_key("${DEEPSEEK_API_KEY}") == "sk-test"


def test_resolve_ssl_metadata_extra_no_verify():
    assert resolve_ssl_metadata_extra(no_verify_ssl=True) == {"verify_ssl": False}
    assert resolve_ssl_metadata_extra(
        "https://gpu.local/v1",
        no_verify_ssl=True,
    ) == {"verify_ssl": False}


def test_apply_ssl_override():
    assert apply_ssl_override({"auth_type": "bearer"}, no_verify_ssl=True) == {
        "auth_type": "bearer",
        "verify_ssl": False,
    }
    assert apply_ssl_override({"verify_ssl": True}, no_verify_ssl=False) == {
        "verify_ssl": True,
    }


def test_resolve_verify_ssl_defaults_true():
    assert resolve_verify_ssl(None) is True
    assert resolve_verify_ssl({}) is True
    assert resolve_verify_ssl({"verify_ssl": True}) is True
    assert resolve_verify_ssl({"verify_ssl": False}) is False
    assert resolve_verify_ssl({"verify_ssl": "false"}) is False
    assert resolve_verify_ssl({"ssl_verify": "0"}) is False


def test_build_provider_entry_merges_popular_models():
    preset = get_provider_preset("deepseek")
    assert preset is not None
    entry = build_provider_entry(preset, api_key="${DEEPSEEK_API_KEY}", discovered_models=[])
    assert "deepseek-chat" in entry["available_models"]
    assert entry["metadata"]["preset_id"] == "deepseek"