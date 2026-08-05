"""Messenger toggle for profile enable_self_refinement (Reflexion)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.core import ProfileManager
from core.di.runtime_config import HolixRuntimeConfig
from integrations.messenger.reflexion_settings import (
    is_reflexion_enabled_for_host,
    set_reflexion_enabled_for_host,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_reflexion_default_off(holix_home) -> None:
    mgr = ProfileManager()
    mgr.create_profile("bob", inherit_global=False)
    host = SimpleNamespace(profile="bob", agent=None)
    assert is_reflexion_enabled_for_host(host) is False


def test_set_reflexion_enabled_persists_and_updates_agent(holix_home) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)

    rt = HolixRuntimeConfig.from_settings().with_overrides(
        enable_self_refinement=False,
        profile_name="alice",
    )
    agent = SimpleNamespace(config=rt)
    host = SimpleNamespace(profile="alice", agent=agent)

    assert is_reflexion_enabled_for_host(host) is False
    set_reflexion_enabled_for_host(host, True)
    assert agent.config.enable_self_refinement is True
    assert is_reflexion_enabled_for_host(host) is True

    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.enable_self_refinement is True

    set_reflexion_enabled_for_host(host, False)
    assert agent.config.enable_self_refinement is False
    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.enable_self_refinement is False


def test_status_menu_includes_reflexion_button() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Reflexion" in labels


def test_status_menu_includes_reflexion_button_max() -> None:
    from integrations.max.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn["text"] for row in kb["payload"]["buttons"] for btn in row]
    assert "Reflexion" in labels


def test_reflexion_picker_keyboard_callback() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import parse_callback, reflexion_picker_keyboard

    kb = reflexion_picker_keyboard(False, "en")
    payloads = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "hx:rf:1" in payloads
    assert "hx:rf:0" in payloads
    assert parse_callback("hx:rf:1") == ("rf", "1")


def test_reflexion_picker_keyboard_callback_max() -> None:
    from integrations.max.keyboards import parse_callback, reflexion_picker_keyboard

    kb = reflexion_picker_keyboard(False, "en")
    payloads = [btn["payload"] for row in kb["payload"]["buttons"] for btn in row]
    assert "hx:rf:1" in payloads
    assert "hx:rf:0" in payloads
    assert parse_callback("hx:rf:1") == ("rf", "1")
