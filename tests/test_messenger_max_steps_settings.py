"""Messenger picker for profile max_steps (Telegram / MAX)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.core import ProfileManager
from core.di.runtime_config import HolixRuntimeConfig
from integrations.messenger.max_steps_settings import (
    DEFAULT_MAX_STEPS,
    MAX_MAX_STEPS,
    MIN_MAX_STEPS,
    get_max_steps_for_host,
    normalize_max_steps,
    parse_max_steps,
    set_max_steps_for_host,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_normalize_and_parse_max_steps() -> None:
    assert normalize_max_steps(None) == DEFAULT_MAX_STEPS
    assert normalize_max_steps("120") == 120
    assert normalize_max_steps(1) == MIN_MAX_STEPS
    assert normalize_max_steps(9999) == MAX_MAX_STEPS
    assert parse_max_steps("180") == 180
    with pytest.raises(ValueError):
        parse_max_steps("nope")
    with pytest.raises(ValueError):
        parse_max_steps("5")
    with pytest.raises(ValueError):
        parse_max_steps("900")


def test_max_steps_default_is_90(holix_home) -> None:
    mgr = ProfileManager()
    mgr.create_profile("bob", inherit_global=False)
    host = SimpleNamespace(profile="bob", agent=None)
    assert get_max_steps_for_host(host) == DEFAULT_MAX_STEPS


def test_set_max_steps_persists_and_updates_agent(holix_home) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)

    rt = HolixRuntimeConfig.from_settings().with_overrides(
        max_steps=90,
        profile_name="alice",
    )
    agent = SimpleNamespace(config=rt)
    host = SimpleNamespace(profile="alice", agent=agent)

    assert get_max_steps_for_host(host) == 90
    set_max_steps_for_host(host, 180)
    assert agent.config.max_steps == 180
    assert get_max_steps_for_host(host) == 180

    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.max_steps == 180

    set_max_steps_for_host(host, 60)
    assert agent.config.max_steps == 60
    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.max_steps == 60


def test_set_max_steps_requires_profile() -> None:
    host = SimpleNamespace(profile="", agent=None)
    with pytest.raises(ValueError, match="No active profile"):
        set_max_steps_for_host(host, 90)


def test_status_menu_includes_steps_button() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Steps" in labels
    payloads = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "hx:r:steps" in payloads


def test_status_menu_includes_steps_button_max() -> None:
    from integrations.max.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn["text"] for row in kb["payload"]["buttons"] for btn in row]
    assert "Steps" in labels
    payloads = [btn["payload"] for row in kb["payload"]["buttons"] for btn in row]
    assert "hx:r:steps" in payloads


def test_status_menu_steps_label_ru() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("ru", is_admin=True)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Шаги" in labels


def test_max_steps_picker_keyboard_callback() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import max_steps_picker_keyboard, parse_callback

    kb = max_steps_picker_keyboard(90, "en")
    payloads = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "hx:ms:90" in payloads
    assert "hx:ms:180" in payloads
    assert parse_callback("hx:ms:120") == ("ms", "120")
    assert any(text.startswith("✓ ") and "90" in text for text in labels)


def test_max_steps_picker_keyboard_callback_max() -> None:
    from integrations.max.keyboards import max_steps_picker_keyboard, parse_callback

    kb = max_steps_picker_keyboard(120, "en")
    payloads = [btn["payload"] for row in kb["payload"]["buttons"] for btn in row]
    labels = [btn["text"] for row in kb["payload"]["buttons"] for btn in row]
    assert "hx:ms:90" in payloads
    assert "hx:ms:120" in payloads
    assert parse_callback("hx:ms:180") == ("ms", "180")
    assert any(text.startswith("✓ ") and "120" in text for text in labels)
