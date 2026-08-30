"""Live LLM: new coding-agent tools (apply_patch, plan_mode, …)."""

from __future__ import annotations

import json

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]

_MUST = (
    "You MUST call the named Holix tool. Do not only describe it. "
    "Do not substitute a different tool unless the named one fails."
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


@pytest.mark.asyncio
async def test_live_60_tool_search_finds_apply_patch(live_harness):
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call tool_search with query='Codex multi-file patch'. "
        "In the final reply name the matching tool.",
        conversation_id="live_60",
        timeout_s=300,
    )
    _skip_unreliable(r)
    _assert_called(r, "tool_search")
    payloads = r.tool_payloads("tool_search")
    names = []
    for payload in payloads:
        if isinstance(payload, dict):
            for match in payload.get("matches") or []:
                if isinstance(match, dict) and match.get("name"):
                    names.append(str(match["name"]))
    assert "apply_patch" in names or soft_contains(
        r.text, "apply_patch", "apply patch", min_hits=1
    ), (names, r.text)


@pytest.mark.asyncio
async def test_live_61_apply_patch_adds_file(live_harness):
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call apply_patch (not write_file, not patch_file) with this exact patch:\n"
        "*** Begin Patch\n"
        "*** Add File: tmp_apply_patch_probe.py\n"
        "+hello_live = 1\n"
        "*** End Patch\n"
        "Then confirm the file exists.",
        conversation_id="live_61",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "apply_patch")
    assert live_harness.exists("tmp_apply_patch_probe.py"), (
        live_harness.list_workspace(),
        r.text,
    )
    body = live_harness.read("tmp_apply_patch_probe.py")
    assert "hello_live" in body, body


@pytest.mark.asyncio
async def test_live_62_ask_user_structured_question(live_harness):
    live_harness.stub_ask_user("dark")
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call ask_user with questions=[{id:'q1', prompt:'Light or dark theme?', "
        "allow_free_text:true, options:[{id:'light',label:'Light'},"
        "{id:'dark',label:'Dark'}]}]. "
        "Do not answer in text before the tool returns. Then report the chosen answer.",
        conversation_id="live_62",
        timeout_s=300,
    )
    _skip_unreliable(r)
    _assert_called(r, "ask_user")
    payloads = r.tool_payloads("ask_user")
    joined = json.dumps(payloads, ensure_ascii=False).lower() + r.text.lower()
    assert "dark" in joined or any(isinstance(p, dict) and p.get("ok") is True for p in payloads), (
        payloads,
        r.text,
    )


@pytest.mark.asyncio
async def test_live_63_plan_mode_enter_blocks_write(live_harness):
    live_harness.seed("keep.py", "keep = 1\n")
    r = await live_harness.run(
        f"{_MUST}\n"
        "1) Call plan_mode with action='enter'.\n"
        "2) Then try write_file on keep.py with content 'mutated = 1'.\n"
        "3) Report whether the write was blocked (plan_mode_blocked).\n"
        "Do not exit plan mode.",
        conversation_id="live_63",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "plan_mode")
    body = live_harness.read("keep.py")
    assert "mutated" not in body, body
    blocked = any(
        isinstance(payload, dict) and payload.get("code") == "plan_mode_blocked"
        for payload in r.tool_payloads("write_file")
    )
    # Entering plan_mode strips write tools from the schema, so the model may
    # never call write_file. File unchanged is then the proof.
    schema_stripped = "write_file" not in r.tool_names()
    assert (
        blocked
        or schema_stripped
        or soft_contains(
            r.text,
            "plan_mode_blocked",
            "blocked",
            "read-only",
            "недоступен",
            "отсутствует",
            min_hits=1,
        )
    ), (r.tool_names(), r.text)


@pytest.mark.asyncio
async def test_live_64_job_monitor_lists_background_job(live_harness):
    r = await live_harness.run(
        f"{_MUST}\n"
        "1) Call start_background_process with command='sleep 8' and label='live_job'.\n"
        "2) Then call job_monitor with action='list' (not list_background_processes).\n"
        "Reply with the job_id from job_monitor.",
        conversation_id="live_64",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "job_monitor")
    payloads = r.tool_payloads("job_monitor")
    assert payloads, r.tool_names()
    okish = any(
        isinstance(p, dict) and (p.get("ok") is True or "jobs" in p or "raw" in p) for p in payloads
    )
    assert okish or soft_contains(r.text, "job", "proc_", min_hits=1), (payloads, r.text)


@pytest.mark.asyncio
async def test_live_65_subagent_control_list(live_harness):
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call subagent_control with action='list'. Do not spawn a sub-agent. "
        "Report how many agents are running.",
        conversation_id="live_65",
        timeout_s=240,
    )
    _skip_unreliable(r)
    _assert_called(r, "subagent_control")
    payloads = r.tool_payloads("subagent_control")
    assert any(
        isinstance(p, dict) and (p.get("ok") is True or isinstance(p.get("agents"), list))
        for p in payloads
    ) or soft_contains(r.text, "agent", "list", "0", min_hits=1), (payloads, r.text)


@pytest.mark.asyncio
async def test_live_66_session_search_runs(live_harness):
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call session_search with query='kanban board statuses'. "
        "Report ok and how many matches (zero is fine).",
        conversation_id="live_66",
        timeout_s=240,
    )
    _skip_unreliable(r)
    _assert_called(r, "session_search")
    payloads = r.tool_payloads("session_search")
    assert any(isinstance(p, dict) and p.get("ok") is True for p in payloads) or payloads, (
        payloads,
        r.text,
    )


@pytest.mark.asyncio
async def test_live_67_notebook_edit_replaces_cell(live_harness):
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
    live_harness.seed("tmp_notebook.ipynb", json.dumps(nb, indent=2))
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call notebook_edit on path tmp_notebook.ipynb with edit_mode=replace, "
        "cell_id=cell-1, source='y = 2\\nprint(y)'. Do not use write_file.",
        conversation_id="live_67",
        timeout_s=360,
    )
    _skip_unreliable(r)
    _assert_called(r, "notebook_edit")
    loaded = json.loads(live_harness.read("tmp_notebook.ipynb"))
    src = "".join(loaded["cells"][0].get("source") or [])
    assert "y = 2" in src or "print(y)" in src, src


@pytest.mark.asyncio
async def test_live_68_lsp_hover_or_unavailable(live_harness):
    live_harness.seed("tmp_lsp_probe.py", "def add(a, b):\n    return a + b\n")
    r = await live_harness.run(
        f"{_MUST}\n"
        "Call lsp with action='hover', path='tmp_lsp_probe.py', line=1, character=4, "
        "language='python'. If lsp_unavailable, say so; do not pretend it worked.",
        conversation_id="live_68",
        timeout_s=300,
    )
    _skip_unreliable(r)
    _assert_called(r, "lsp")
    payloads = r.tool_payloads("lsp")
    codes = [str(p.get("code") or "") for p in payloads if isinstance(p, dict)]
    oks = [p.get("ok") for p in payloads if isinstance(p, dict)]
    # ok, missing server, or the language server ran and failed (still exercised lsp)
    assert (
        True in oks
        or "lsp_unavailable" in codes
        or "lsp_error" in codes
        or soft_contains(
            r.text,
            "lsp_unavailable",
            "lsp_error",
            "jedi",
            "unavailable",
            "pyright",
            min_hits=1,
        )
    ), (payloads, r.text)
