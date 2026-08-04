"""Messenger toggle for profile enable_subagents."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cli.core import ProfileManager
from core.di.runtime_config import HolixRuntimeConfig
from integrations.messenger.subagents_settings import (
    is_subagents_enabled_for_host,
    set_subagents_enabled_for_host,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_set_subagents_enabled_persists_and_updates_agent(holix_home) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    cfg = mgr.load_profile("alice")
    cfg.enable_subagents = True
    mgr.save_profile("alice", cfg)

    rt = HolixRuntimeConfig.from_settings().with_overrides(
        enable_subagents=True,
        profile_name="alice",
    )
    tools = MagicMock()
    tools.get_tool_names.return_value = ["delegate_to_subagent", "list_subagents"]
    agent = SimpleNamespace(config=rt, tools=tools)
    host = SimpleNamespace(profile="alice", agent=agent)

    assert is_subagents_enabled_for_host(host) is True
    set_subagents_enabled_for_host(host, False)
    assert agent.config.enable_subagents is False
    assert is_subagents_enabled_for_host(host) is False
    assert tools.unregister.call_count >= 1

    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.enable_subagents is False

    set_subagents_enabled_for_host(host, True)
    assert agent.config.enable_subagents is True
    reloaded = ProfileManager().load_profile("alice")
    assert reloaded.enable_subagents is True

def test_status_menu_includes_subagents_button() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Sub-agents" in labels


def test_status_menu_includes_subagents_button_max() -> None:
    from integrations.max.keyboards import status_menu_keyboard

    kb = status_menu_keyboard("en", is_admin=True)
    labels = [btn["text"] for row in kb["payload"]["buttons"] for btn in row]
    assert "Sub-agents" in labels


def test_subagents_picker_keyboard_callback() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import parse_callback, subagents_picker_keyboard

    kb = subagents_picker_keyboard(True, "en")
    payloads = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "hx:sa:1" in payloads
    assert "hx:sa:0" in payloads
    assert parse_callback("hx:sa:0") == ("sa", "0")
