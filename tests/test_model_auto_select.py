"""Global model auto-select stays off until configured and fails open."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from core.decision.model_select import (
    apply_model_auto_select,
    chat_candidates,
    choose_chat_model,
    read_model_auto_select,
)
from core.models.manager import ModelManager


def test_missing_block_is_off() -> None:
    assert read_model_auto_select({}).enabled is False
    assert read_model_auto_select({"model_auto_select": {"enabled": False}}).enabled is False


def test_empty_mark_list_uses_chat_models_only() -> None:
    found = chat_candidates(
        ["auto", "coder", "nimble", "laya", "image-z-image-turbo"],
        (),
    )
    assert found == ["auto", "coder"]


def test_marked_models_must_be_available() -> None:
    assert chat_candidates(["auto", "coder", "ornith"], ("ornith", "missing", "coder")) == [
        "ornith",
        "coder",
    ]


def _agent(models: list[str]):
    config = SimpleNamespace(
        profile_name="auto-select-test",
        decision={
            "enabled": True,
            "preset": "custom",
            "base_url": "http://decision.example",
            "model": "nimble",
            "thresholds": {"confidence": 0.6},
        },
        providers={
            "mikrollm": {
                "base_url": "http://hub.example/v1",
                "api_key": "dummy",
                "default_model": "auto",
                "available_models": models,
            }
        },
        default_provider="mikrollm",
        temperature=0.2,
        context_window=8000,
        model="auto",
    )
    agent = SimpleNamespace(
        agent_slot="main",
        config=config,
        model="auto",
        model_manager=ModelManager(config),
        active_model_config=None,
        switched=None,
    )

    def _set(model_config, model_slot_id=None):
        del model_slot_id
        agent.model = model_config.model
        agent.switched = model_config.model

    agent.set_active_model_config = _set
    return agent


@pytest.fixture
def no_profile_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "core.decision.model_select.profile_env_secret", lambda *_a, **_k: "test-key"
    )


async def test_disabled_does_not_call(monkeypatch, no_profile_key) -> None:
    called = False

    async def boom(*_a, **_k):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("core.decision.model_select.call_systemone", boom)
    agent = _agent(["auto", "coder"])
    assert await choose_chat_model(agent, "привет", read_model_auto_select({})) is None
    assert called is False


async def test_choice_switches_only_the_live_model(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return json.dumps({"model": {"choice": "coder", "confidence": 0.9}})

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    agent = _agent(["auto", "coder", "nimble"])
    settings = read_model_auto_select({"model_auto_select": {"enabled": True, "models": []}})
    assert await choose_chat_model(agent, "спроектируй миграцию схемы", settings) == "coder"
    assert agent.switched is None


async def test_apply_uses_global_block(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return json.dumps({"model": {"choice": "coder"}})

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    monkeypatch.setattr(
        "core.decision.model_select.read_model_auto_select",
        lambda raw=None: read_model_auto_select(
            {"model_auto_select": {"enabled": True, "models": ["coder", "auto"]}}
        ),
    )
    agent = _agent(["auto", "coder"])
    await apply_model_auto_select(agent, "длинная задача на несколько шагов")
    assert agent.switched == "coder"


async def test_low_confidence_keeps_the_current_model(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return json.dumps({"model": {"choice": "coder", "confidence": 0.1}})

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    agent = _agent(["auto", "coder"])
    settings = read_model_auto_select({"model_auto_select": {"enabled": True}})
    assert await choose_chat_model(agent, "ок", settings) is None


async def test_error_string_keeps_the_current_model(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return "System One error: connection failed"

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    agent = _agent(["auto", "coder"])
    settings = read_model_auto_select({"model_auto_select": {"enabled": True}})
    assert await choose_chat_model(agent, "ок", settings) is None


async def test_same_model_is_still_reported(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return json.dumps({"model": {"choice": "auto", "confidence": 0.95}})

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    agent = _agent(["auto", "coder"])
    settings = read_model_auto_select({"model_auto_select": {"enabled": True}})
    assert await choose_chat_model(agent, "привет", settings) == "auto"


def test_live_status_shows_the_chosen_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.i18n.live_ui.live_auto_model_label",
        lambda _profile, model: f"Модель: {model}",
    )
    from core.presenters.live_buffer import LiveTranscriptBuffer

    text = LiveTranscriptBuffer(profile="admin", auto_model="ornith-1.5:35b").render_plain()
    assert "Модель: ornith-1.5:35b" in text


async def test_resume_does_not_switch(monkeypatch, no_profile_key) -> None:
    async def answer(*_a, **_k):
        return json.dumps({"model": {"choice": "coder"}})

    monkeypatch.setattr("core.decision.model_select.call_systemone", answer)
    monkeypatch.setattr(
        "core.decision.model_select.read_model_auto_select",
        lambda raw=None: read_model_auto_select({"model_auto_select": {"enabled": True}}),
    )
    agent = _agent(["auto", "coder"])
    await apply_model_auto_select(agent, "продолжи", resume=True)
    assert agent.switched is None
