"""Runtime model switching."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.models.manager import ModelConfig
from integrations.telegram.keyboards import _cb, models_provider_keyboard
from integrations.telegram.model_switch import (
    ModelChoice,
    ProviderMenu,
    apply_model_choice_sync,
    apply_preset_index,
    build_model_choices,
    build_models_menu,
    choice_for_provider_model,
    resolve_model_config,
)


def test_build_models_menu_separates_providers():
    state = build_models_menu("default")
    if not state.presets and not state.providers:
        pytest.skip("no default profile")
    if state.providers:
        prov = state.providers[0]
        assert isinstance(prov, ProviderMenu)
        assert prov.name not in (prov.models[0] if prov.models else "")


def test_build_model_choices_includes_main():
    choices = build_model_choices("default")
    if not choices:
        pytest.skip("no default profile")
    assert any(c.slot_id == "main" for c in choices)


def test_resolve_model_config_main():
    choices = build_model_choices("default")
    if not choices:
        pytest.skip("no default profile")
    main = next(c for c in choices if c.slot_id == "main")
    mc = resolve_model_config("default", main)
    assert mc.model


def test_provider_keyboard_callback_length():
    models = [f"model-{i}" for i in range(50)]
    kb = models_provider_keyboard("ollama", models, "", 0, page=3, page_size=10)
    for row in kb.inline_keyboard:
        for btn in row:
            assert len(btn.callback_data) <= 64


def test_agent_set_active_model_config():
    from core.agent import HolixAgent

    cfg = HolixRuntimeConfig.from_settings()
    agent = HolixAgent(config=cfg, enable_monitoring=False)
    new_mc = ModelConfig(
        provider="test",
        model="other-model",
        base_url="http://localhost:11434/v1",
        api_key="k",
        temperature=0.5,
    )
    new_mc.context_window = 32_768
    agent.set_active_model_config(new_mc, model_slot_id="coder")
    assert agent.model == "other-model"
    assert agent.loop.model == "other-model"
    assert agent.agent_slot == "coder"
    assert agent.context_manager.context_window == 32_768


def test_apply_preset_index():
    choice = ModelChoice(slot_id="main", label="main", provider="p", model="m")

    session = MagicMock()
    session.ui_model_presets = [choice]
    session.active_model_slot = ""
    session.active_model_label = ""

    agent = MagicMock()
    host = MagicMock()
    host.profile = "default"
    host._session = session
    host.agent = agent

    import asyncio

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "integrations.telegram.model_switch.resolve_model_config",
            lambda _p, _c: ModelConfig(
                provider="p",
                model="m",
                base_url="http://x/v1",
                api_key="k",
            ),
        )
        asyncio.run(apply_preset_index(host, 0))

    agent.set_active_model_config.assert_called_once()


def test_apply_model_choice_sync_tui_host():
    choice = ModelChoice(slot_id="main", label="main", provider="p", model="m")
    agent = MagicMock()
    host = MagicMock()
    host.profile = "default"
    host.agent = agent
    host._session = None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "integrations.telegram.model_switch.resolve_model_config",
            lambda _p, _c: ModelConfig(
                provider="p",
                model="m",
                base_url="http://x/v1",
                api_key="k",
            ),
        )
        label = apply_model_choice_sync(host, choice)

    assert label == "p/m"
    agent.set_active_model_config.assert_called_once()
    assert host._resolved_model == "m"


def test_choice_for_provider_model_slot():
    c = choice_for_provider_model("ollama", "llama3:8b")
    assert c.slot_id == "prov:ollama:llama3:8b"
    assert c.label == "llama3:8b"
    assert _cb("mm", "0:5")  # fits in 64 bytes