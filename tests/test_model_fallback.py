"""Tests for LLM provider fallback routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cli.core import ProfileConfig, ProfileManager
from core.models.fallback import chat_completions_with_fallback, is_llm_unavailable_error
from core.models.manager import ModelManager
from openai import APIConnectionError


@pytest.fixture
def helix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    return tmp_path


def _profile_with_providers() -> ProfileConfig:
    return ProfileConfig(
        profile_name="test",
        default_provider="primary",
        fallback_providers=["backup"],
        providers={
            "primary": {
                "base_url": "http://primary/v1",
                "api_key": "k1",
                "default_model": "model-a",
            },
            "backup": {
                "base_url": "http://backup/v1",
                "api_key": "k2",
                "default_model": "model-b",
            },
        },
    )


def test_iter_fallback_configs_order() -> None:
    cfg = _profile_with_providers()
    cfg.providers["primary"]["fallback_providers"] = ["local"]
    cfg.providers["local"] = {
        "base_url": "http://local/v1",
        "api_key": "k3",
        "default_model": "model-c",
    }
    cfg.fallback_providers = ["backup"]

    mm = ModelManager(cfg)
    chain = mm.iter_fallback_configs("main")
    assert [c.provider for c in chain] == ["primary", "local", "backup"]


def test_is_llm_unavailable_detects_connection_error() -> None:
    assert is_llm_unavailable_error(APIConnectionError(request=MagicMock()))


@pytest.mark.asyncio
async def test_chat_completions_falls_back_on_connection_error() -> None:
    cfg = _profile_with_providers()
    mm = ModelManager(cfg)

    primary_client = MagicMock()
    primary_client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    backup_client = MagicMock()
    backup_response = MagicMock()
    backup_client.chat.completions.create = AsyncMock(return_value=backup_response)

    with patch.object(mm, "get_client", side_effect=[primary_client, backup_client]):
        result = await chat_completions_with_fallback(
            mm,
            messages=[{"role": "user", "content": "hi"}],
        )

    assert result is backup_response
    backup_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_completions_raises_when_no_fallback() -> None:
    cfg = ProfileConfig(
        profile_name="solo",
        default_provider="only",
        providers={
            "only": {
                "base_url": "http://only/v1",
                "api_key": "k",
                "default_model": "m",
            }
        },
    )
    mm = ModelManager(cfg)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    with patch.object(mm, "get_client", return_value=client):
        with pytest.raises(APIConnectionError):
            await chat_completions_with_fallback(mm, messages=[])


def test_fallback_persisted_in_profile_yaml(helix_home: Path) -> None:
    manager = ProfileManager()
    cfg = _profile_with_providers()
    manager.create_profile("fb", config=cfg, inherit_global=False)
    loaded = manager.load_profile("fb")
    assert loaded.fallback_providers == ["backup"]