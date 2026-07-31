"""Model discovery: extract and enrich context_window from LiteLLM / catalogs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.models.discovery import ModelDiscovery, extract_context_length


def test_extract_context_length_from_flat_dict() -> None:
    assert extract_context_length({"max_input_tokens": 128_000}) == 128_000
    assert extract_context_length({"context_window": 200_000}) == 200_000
    assert extract_context_length({"max_model_len": 8192}) == 8192
    assert extract_context_length({"max_tokens": 0}) is None
    assert extract_context_length({}) is None


def test_extract_context_length_nested_model_info() -> None:
    payload = {
        "model_name": "smart",
        "model_info": {
            "max_input_tokens": 131_072,
            "max_output_tokens": 8192,
        },
    }
    assert extract_context_length(payload) == 131_072


def test_extract_context_length_from_sdk_object() -> None:
    obj = SimpleNamespace(
        id="gpt-4o",
        model_extra={"max_model_len": 128_000},
    )
    assert extract_context_length(obj) == 128_000


def test_lookup_catalog_context_known_model() -> None:
    pytest.importorskip("litellm")
    n = ModelDiscovery.lookup_catalog_context("gpt-4o")
    assert n is not None
    assert n >= 100_000


def test_lookup_catalog_context_unknown_alias() -> None:
    n = ModelDiscovery.lookup_catalog_context("totally-unknown-model-xyz-123")
    # None when litellm missing or model unmapped
    assert n is None

@pytest.mark.asyncio
async def test_discover_models_enriches_from_object_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        id="gpt-4o",
        created=1,
        owned_by="openai",
        model_extra={"max_input_tokens": 128_000},
    )
    client = MagicMock()
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=[model]))

    monkeypatch.setattr(
        "core.models.discovery.create_openai_client",
        lambda **_k: client,
    )
    monkeypatch.setattr(
        ModelDiscovery,
        "detect_provider_type",
        staticmethod(lambda *_a, **_k: "openai"),
    )
    # avoid network to litellm proxy
    monkeypatch.setattr(
        ModelDiscovery,
        "_get_litellm_context_lengths",
        staticmethod(AsyncMock(return_value={})),
    )

    rows = await ModelDiscovery.discover_models(
        "https://api.openai.com/v1",
        "sk-test",
    )
    assert len(rows) == 1
    assert rows[0]["id"] == "gpt-4o"
    assert rows[0]["context_length"] == 128_000


@pytest.mark.asyncio
async def test_discover_models_uses_litellm_model_info_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        id="smart",
        created=1,
        owned_by="openai",
        model_extra={},
    )
    client = MagicMock()
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=[model]))

    monkeypatch.setattr(
        "core.models.discovery.create_openai_client",
        lambda **_k: client,
    )
    monkeypatch.setattr(
        ModelDiscovery,
        "detect_provider_type",
        staticmethod(lambda *_a, **_k: "litellm"),
    )
    monkeypatch.setattr(
        ModelDiscovery,
        "_get_litellm_context_lengths",
        staticmethod(AsyncMock(return_value={"smart": 200_000})),
    )
    monkeypatch.setattr(
        ModelDiscovery,
        "lookup_catalog_context",
        staticmethod(lambda _mid: None),
    )

    rows = await ModelDiscovery.discover_models(
        "http://127.0.0.1:4000/v1",
        "sk-test",
    )
    assert rows[0]["context_length"] == 200_000


def test_model_manager_prefers_model_contexts_over_profile() -> None:
    from core.models.manager import ModelManager

    profile = SimpleNamespace(
        providers={
            "litellm": {
                "base_url": "http://127.0.0.1:4000/v1",
                "api_key": "sk",
                "default_model": "smart",
                "model_contexts": {"smart": 200_000, "free": 32_000},
            }
        },
        default_provider="litellm",
        context_window=8_000,  # must NOT override per-model
        temperature=0.7,
        agent_models={},
        models_via_providers=True,
        model="",
        base_url="",
        api_key="",
        fallback_providers=[],
    )
    mm = ModelManager(profile)
    cfg = mm.get_default_model_config()
    assert cfg is not None
    assert cfg.model == "smart"
    assert cfg.context_window == 200_000

    free = mm.get_provider_model_config("litellm", model_id="free")
    assert free is not None
    assert free.context_window == 32_000
