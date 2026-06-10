"""Per-session model persistence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from core.session_models import SessionModelStore, restore_session_model


def test_session_model_store_roundtrip(tmp_path: Path, monkeypatch):
    from cli.core import ProfileManager

    profile = "sess_model_test"

    def fake_dir(p: str) -> Path:
        d = tmp_path / p
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(ProfileManager, "get_profile_dir", lambda self, p: fake_dir(p))

    store = SessionModelStore(profile)
    store.set(
        "tui_default_1",
        __import__("core.session_models", fromlist=["SessionModelRecord"]).SessionModelRecord(
            slot_id="prov:ollama:llama3",
            label="llama3",
            provider="ollama",
            model="llama3",
        ),
    )
    got = store.get("tui_default_1")
    assert got is not None
    assert got.model == "llama3"
    assert store.get("other") is None


def test_restore_session_model_applies_saved_choice(tmp_path: Path, monkeypatch):
    from cli.core import ProfileManager
    from core.models.manager import ModelConfig
    from core.session_models import SessionModelRecord, SessionModelStore

    profile = "restore_test"

    def fake_dir(p: str) -> Path:
        d = tmp_path / p
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(ProfileManager, "get_profile_dir", lambda self, p: fake_dir(p))

    SessionModelStore(profile).set(
        "conv_a",
        SessionModelRecord(
            slot_id="main",
            label="main",
            provider="test",
            model="saved-model",
        ),
    )

    agent = MagicMock()
    host = MagicMock()
    host.profile = profile
    host.conversation_id = "conv_a"
    host.agent = agent
    host._session = None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "integrations.telegram.model_switch.resolve_model_config",
            lambda _p, _c: ModelConfig(
                provider="test",
                model="saved-model",
                base_url="http://x/v1",
                api_key="k",
            ),
        )
        label = restore_session_model(host)

    assert label == "test/saved-model"
    agent.set_active_model_config.assert_called_once()
    assert host._model_synced_for == "conv_a"