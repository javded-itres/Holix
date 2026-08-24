"""Built-in overlays and messenger Code mode presentation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.core import ProfileManager
from core.subagents.registry import get_subagent_config, list_available_subagents
from core.subagents.store import SubAgentOverlayStore, SubAgentTypeStore
from core.tools.registry import ToolRegistry
from integrations.messenger.presentation_settings import (
    presentation_for_host,
    set_presentation_for_host,
    slot_presentation_for_host,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_overlay_changes_builtin_prompt_and_temp(holix_home: Path) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    SubAgentOverlayStore("alice").merge(
        "coder",
        system_prompt="You are overlay coder.",
        temperature=0.9,
        description="overlay desc",
    )
    cfg = get_subagent_config("coder", profile="alice")
    assert cfg.system_prompt == "You are overlay coder."
    assert cfg.temperature == 0.9
    names = {i["name"]: i for i in list_available_subagents(profile="alice")}
    assert names["coder"]["description"] == "overlay desc"
    assert names["coder"]["builtin"] is True


def test_custom_type_listed_immediately(holix_home: Path) -> None:
    from core.subagents.from_description import build_custom_type_from_brief

    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    custom = build_custom_type_from_brief(
        "Python backend specialist who writes FastAPI services with tests"
    )
    SubAgentTypeStore("alice").upsert(custom)
    names = [i["name"] for i in list_available_subagents(profile="alice")]
    assert custom.name in names
    assert "coder" in names


def test_presentation_settings_persist(holix_home: Path) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    tools = ToolRegistry(profile_name="alice", tools_presentation="native")
    tools.register_all()
    from core.di.runtime_config import HolixRuntimeConfig

    agent = SimpleNamespace(
        config=HolixRuntimeConfig.from_settings().with_overrides(profile_name="alice"),
        tools=tools,
    )
    host = SimpleNamespace(profile="alice", agent=agent)
    assert presentation_for_host(host) == "native"
    set_presentation_for_host(host, "code")
    assert presentation_for_host(host) == "code"
    assert ProfileManager().load_profile("alice").tools_presentation == "code"
    set_presentation_for_host(host, "both", slot="coder")
    assert slot_presentation_for_host(host, "coder") == "both"
    by_slot = ProfileManager().load_profile("alice").tools_presentation_by_slot
    assert by_slot.get("coder") == "both"


def test_spawn_model_slot_uses_overlay(holix_home: Path) -> None:
    from core.subagents.spawn import spawn_model_slot

    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    SubAgentOverlayStore("alice").merge("coder", model_slot="prov:litellm:smart")
    cfg = SimpleNamespace(agent_models={})
    assert spawn_model_slot("coder", cfg, "alice") == "prov:litellm:smart"


def test_overlay_tools_replace_builtin(holix_home: Path) -> None:
    mgr = ProfileManager()
    mgr.create_profile("alice", inherit_global=False)
    SubAgentOverlayStore("alice").merge("coder", tools=["read_file", "grep"])
    cfg = get_subagent_config("coder", profile="alice")
    assert cfg.tools == ["read_file", "grep"]
    assert "write_file" not in cfg.tools
