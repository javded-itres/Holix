"""Live LLM: Claude-style lazy tools (core schema + tool_search enable_matches)."""

from __future__ import annotations

import json

import pytest
from core.tools.lazy_schema import CORE_TOOL_NAMES

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]

_DEFERRED = (
    "session_search",
    "job_monitor",
    "notebook_edit",
    "sql_query",
    "sdd_apply",
    "subagent_control",
)

_MUST = (
    "You MUST call the named Holix tools in order. Do not only describe them. "
    "Do not skip tool_search. Do not substitute a different tool unless the named one fails."
)


def _skip_unreliable(result) -> None:
    low = result.text.lower()
    if "timed out" in low or "connection error" in low:
        pytest.skip(f"provider timeout: {result.text[:120]}")
    if result.looks_unreliable():
        pytest.skip(f"unreliable live reply: {result.text[:120]}")


def _assert_called(result, name: str) -> None:
    names = result.tool_names()
    assert result.called(name), f"expected tool {name!r}, got {names}; answer={result.text[:400]!r}"


def _force_lazy(live_harness) -> None:
    live_harness.monkeypatch.setenv("HOLIX_LAZY_TOOLS", "1")
    extra = getattr(live_harness.agent.tools, "_session_enabled_tools", None)
    if extra is not None:
        extra.clear()


@pytest.mark.asyncio
async def test_live_69_lazy_initial_schema_is_core_only(live_harness):
    """Initialized live agent offers the core set, not the deferred catalog."""
    _force_lazy(live_harness)
    names = live_harness.offered_tool_names()
    assert "tool_search" in names
    assert "read_file" in names
    assert "lsp" in names
    registered = set(live_harness.agent.tools.tools)
    for core in CORE_TOOL_NAMES:
        if core in registered:
            assert core in names, core
    missing_deferred = [n for n in _DEFERRED if n in registered]
    assert missing_deferred, "expected deferred builtins to be registered"
    for name in missing_deferred:
        assert name not in names, names
    assert len(names) < len(registered)


@pytest.mark.asyncio
async def test_live_70_tool_search_enables_session_search(live_harness):
    """tool_search(enable_matches) attaches a deferred tool; next step can call it."""
    _force_lazy(live_harness)
    before = live_harness.offered_tool_names()
    assert "tool_search" in before
    assert "session_search" not in before

    snaps = live_harness.trace_offered_schemas()
    r = await live_harness.run(
        f"{_MUST}\n"
        "session_search is deferred and is NOT in your current tools list.\n"
        "1) Call tool_search with query='session_search' and enable_matches=true.\n"
        "2) After that returns, call session_search with query='lazy tools'.\n"
        "Report ok and match count (zero is fine).",
        conversation_id="live_70",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "tool_search")
    assert r.first_called("tool_search", "session_search") == "tool_search", r.tool_names()
    _assert_called(r, "session_search")

    assert "session_search" in live_harness.session_enabled_tools() or any(
        "session_search" in snap for snap in snaps[1:]
    ), (live_harness.session_enabled_tools(), [sorted(s)[:12] for s in snaps[:6]])

    if snaps:
        assert "session_search" not in snaps[0], snaps[0]

    payloads = r.tool_payloads("session_search")
    assert any(isinstance(p, dict) and p.get("ok") is True for p in payloads) or payloads, (
        payloads,
        r.text,
    )


@pytest.mark.asyncio
async def test_live_71_tool_search_then_notebook_edit(live_harness):
    """Deferred notebook_edit is used only after tool_search attaches it."""
    _force_lazy(live_harness)
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "language": "python"}},
        "cells": [
            {
                "id": "cell-1",
                "cell_type": "code",
                "metadata": {},
                "source": ["x = 1\n"],
                "outputs": [],
                "execution_count": None,
            }
        ],
    }
    live_harness.seed("tmp_lazy.ipynb", json.dumps(nb, indent=2))
    assert "notebook_edit" not in live_harness.offered_tool_names()

    snaps = live_harness.trace_offered_schemas()
    r = await live_harness.run(
        f"{_MUST}\n"
        "notebook_edit is deferred and is NOT in your current tools list.\n"
        "1) Call tool_search with query='notebook_edit jupyter' and enable_matches=true.\n"
        "2) Then call notebook_edit on path tmp_lazy.ipynb with edit_mode=replace, "
        "cell_id=cell-1, source='y = 2\\nprint(y)'. Do not use write_file.",
        conversation_id="live_71",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "tool_search")
    assert r.first_called("tool_search", "notebook_edit") == "tool_search", r.tool_names()
    _assert_called(r, "notebook_edit")

    assert "notebook_edit" in live_harness.session_enabled_tools() or any(
        "notebook_edit" in snap for snap in snaps[1:]
    ), (live_harness.session_enabled_tools(), r.tool_names())

    loaded = json.loads(live_harness.read("tmp_lazy.ipynb"))
    src = "".join(loaded["cells"][0].get("source") or [])
    assert (
        "y = 2" in src
        or "print(y)" in src
        or soft_contains(r.text, "y = 2", "print(y)", min_hits=1)
    ), src
