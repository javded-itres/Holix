"""Model discovery UI helpers during provider setup."""

from __future__ import annotations

import pytest
from core.models.catalog import get_provider_preset
from core.models.setup_helpers import (
    auto_pick_default_model,
    discover_and_select_default_model,
)


@pytest.mark.asyncio
async def test_discover_and_select_shows_api_models(monkeypatch: pytest.MonkeyPatch):
    preset = get_provider_preset("openai")
    assert preset is not None

    fake_models = [
        {"id": "gpt-4o", "context_length": 128000, "owned_by": "openai"},
        {"id": "gpt-4o-mini", "context_length": 128000, "owned_by": "openai"},
    ]

    async def fake_probe(*_a, **_k):
        return True, fake_models, None

    monkeypatch.setattr(
        "core.models.setup_helpers.probe_provider",
        fake_probe,
    )

    ok, models, err, default = await discover_and_select_default_model(
        preset,
        "https://api.openai.com/v1",
        "sk-test",
        interactive=False,
    )
    assert ok is True
    assert len(models) == 2
    assert err is None
    assert default in ("gpt-4o", "gpt-4o-mini")


def test_auto_pick_prefers_preset_default():
    preset = get_provider_preset("deepseek")
    assert preset is not None
    models = [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]
    assert auto_pick_default_model(models, preset) == preset.default_model