"""Telegram/MAX sub-agent type manager (Code mode + overlays)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.core import ProfileManager
from core.subagents.registry import get_subagent_config, list_available_subagents
from core.subagents.store import SubAgentOverlayStore, SubAgentTypeStore
from integrations.messenger.subagent_types_ui import (
    TYPE_ACTIONS,
    detail_keyboard_rows,
    format_detail_text,
    format_list_text,
    handle_subagent_types_action,
    list_keyboard_rows,
    tools_keyboard_rows,
    try_consume_compose,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _host(profile: str = "alice") -> SimpleNamespace:
    session = SimpleNamespace(
        ui_subagent_types=[],
        ui_subagent_page=0,
        ui_subagent_current="",
        ui_subagent_tools_view=False,
        ui_subagent_model_page=0,
        ui_subagent_confirm="",
        pending_subagent_compose=None,
    )
    return SimpleNamespace(profile=profile, agent=None, _session=session)


def _actions(rows: list[list[tuple[str, str, str]]]) -> set[str]:
    return {action for row in rows for _label, action, _value in row}


def _payloads(rows: list[list[tuple[str, str, str]]]) -> list[str]:
    return [f"hx:{action}:{value}" for row in rows for _label, action, value in row]


def test_callback_actions_do_not_collide_with_sessions(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    assert "sp" not in TYPE_ACTIONS
    assert "sp" not in _actions(list_keyboard_rows(host))
    host._session.ui_subagent_current = "coder"
    assert "sp" not in _actions(detail_keyboard_rows(host))
    assert "cm" in _actions(detail_keyboard_rows(host))
    assert "tp" in _actions(list_keyboard_rows(host))


def test_list_shows_builtins_and_create(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    text = format_list_text(host)
    assert "coder" in text
    rows = list_keyboard_rows(host)
    payloads = _payloads(rows)
    assert any(p.startswith("hx:tp:") for p in payloads)
    assert "hx:sc:x" in payloads
    assert any(p.startswith("hx:sd:") for p in payloads)


@pytest.mark.asyncio
async def test_create_from_description_listed_immediately(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    toast = await handle_subagent_types_action(host, "sc", "x")
    assert toast
    assert host._session.pending_subagent_compose == "create"
    result = await try_consume_compose(
        host,
        "Python backend specialist who writes FastAPI services with tests",
    )
    assert result is not None
    assert "created" in result.lower() or "создан" in result.lower()
    names = [i["name"] for i in list_available_subagents(profile="alice")]
    created = host._session.ui_subagent_current
    assert created
    assert created in names
    assert SubAgentTypeStore("alice").get(created) is not None


@pytest.mark.asyncio
async def test_builtin_overlay_temp_presentation_and_reset(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    host._session.ui_subagent_current = "coder"
    original_temp = get_subagent_config("coder", profile="alice").temperature
    toast = await handle_subagent_types_action(host, "su", "4")  # 0.7
    assert "0.7" in toast
    toast = await handle_subagent_types_action(host, "cm", "code")
    assert "code" in toast
    cfg = get_subagent_config("coder", profile="alice")
    assert cfg.temperature == 0.7
    overlay = SubAgentOverlayStore("alice").get("coder")
    assert overlay is not None
    assert overlay.tools_presentation == "code"
    by_slot = ProfileManager().load_profile("alice").tools_presentation_by_slot
    assert by_slot.get("coder") == "code"
    await handle_subagent_types_action(host, "sz", "x")
    cfg = get_subagent_config("coder", profile="alice")
    assert abs(cfg.temperature - original_temp) < 0.05
    assert SubAgentOverlayStore("alice").get("coder") is None
    by_slot = ProfileManager().load_profile("alice").tools_presentation_by_slot
    assert "coder" not in (by_slot or {})


@pytest.mark.asyncio
async def test_toggle_tools_on_builtin(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    host._session.ui_subagent_current = "coder"
    before = list(get_subagent_config("coder", profile="alice").tools)
    assert "web_search" not in before
    from core.subagents.store import SUBAGENT_TOOL_CHOICES

    idx = SUBAGENT_TOOL_CHOICES.index("web_search")
    await handle_subagent_types_action(host, "tt", str(idx))
    cfg = get_subagent_config("coder", profile="alice")
    assert "web_search" in cfg.tools
    assert "write_file" in cfg.tools
    if "start_background_process" in before:
        assert "start_background_process" in cfg.tools
    rows = tools_keyboard_rows(host)
    assert "tt" in _actions(rows)


@pytest.mark.asyncio
async def test_write_description_and_personality_overlay(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    host._session.ui_subagent_current = "coder"
    await handle_subagent_types_action(host, "ds", "x")
    toast = await try_consume_compose(host, "Fast overlay coder for Holix")
    assert toast
    names = {i["name"]: i for i in list_available_subagents(profile="alice")}
    assert "overlay coder" in names["coder"]["description"].lower()
    await handle_subagent_types_action(host, "swp", "x")
    toast = await try_consume_compose(host, "You are a terse Holix coder who always runs tests.")
    assert toast
    cfg = get_subagent_config("coder", profile="alice")
    assert "terse" in cfg.system_prompt.lower() or "test" in cfg.system_prompt.lower()
    detail = format_detail_text(host)
    assert "coder" in detail


@pytest.mark.asyncio
async def test_delete_custom_requires_confirm(holix_home: Path) -> None:
    from core.subagents.from_description import build_custom_type_from_brief

    ProfileManager().create_profile("alice", inherit_global=False)
    custom = build_custom_type_from_brief("docs writer for API readmes")
    SubAgentTypeStore("alice").upsert(custom)
    host = _host()
    host._session.ui_subagent_current = custom.name
    toast = await handle_subagent_types_action(host, "sx", "x")
    assert SubAgentTypeStore("alice").get(custom.name) is not None
    assert host._session.ui_subagent_confirm == "delete"
    toast = await handle_subagent_types_action(host, "sx", "1")
    assert custom.name in toast or "удал" in toast.lower()
    assert SubAgentTypeStore("alice").get(custom.name) is None


@pytest.mark.asyncio
async def test_compose_cancel(holix_home: Path) -> None:
    ProfileManager().create_profile("alice", inherit_global=False)
    host = _host()
    await handle_subagent_types_action(host, "sc", "x")
    assert host._session.pending_subagent_compose == "create"
    result = await try_consume_compose(host, "/cancel")
    assert result is not None
    assert host._session.pending_subagent_compose is None
    assert await try_consume_compose(host, "hello") is None
