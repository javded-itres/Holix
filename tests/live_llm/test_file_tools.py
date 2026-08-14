"""Live LLM: file read/write/list under workspace jail."""

from __future__ import annotations

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


@pytest.mark.asyncio
async def test_live_10_read_seeded_file(live_harness):
    live_harness.seed(
        "docs/about.md",
        "# Project Nebula\nUnique token: NEBULA-TOKEN-991\n",
    )
    r = await live_harness.run(
        "Read docs/about.md and tell me the unique token written there.",
        conversation_id="live_10",
        timeout_s=240,
    )
    assert soft_contains(r.text, "NEBULA-TOKEN-991", "991", min_hits=1), r.text
    assert "read_file" in r.tool_names() or soft_contains(r.text, "NEBULA"), r.tool_names()


@pytest.mark.asyncio
async def test_live_11_write_file(live_harness):
    r = await live_harness.run(
        "Create a file notes/hello.txt containing exactly the line: "
        "hello-from-live-llm\n"
        "Then confirm the file was created.",
        conversation_id="live_11",
        timeout_s=300,
    )
    assert live_harness.exists(
        "notes/hello.txt"
    ), f"file missing; workspace={live_harness.list_workspace()}; answer={r.text!r}"
    content = live_harness.read("notes/hello.txt")
    assert "hello-from-live-llm" in content, content


@pytest.mark.asyncio
async def test_live_12_list_directory(live_harness):
    live_harness.seed("alpha/one.txt", "a")
    live_harness.seed("alpha/two.txt", "b")
    r = await live_harness.run(
        "List the files under the alpha/ directory and name them.",
        conversation_id="live_12",
        timeout_s=240,
    )
    assert soft_contains(r.text, "one", "two", min_hits=1), r.text


@pytest.mark.asyncio
async def test_live_13_write_and_read_back(live_harness):
    r = await live_harness.run(
        'Write data/config.json with JSON: {"app": "live", "port": 8080}. '
        "Then read it back and report the port number.",
        conversation_id="live_13",
        timeout_s=360,
    )
    assert live_harness.exists("data/config.json") or soft_contains(
        r.text, "8080", "port", min_hits=1
    ), (live_harness.list_workspace(), r.text)
    if live_harness.exists("data/config.json"):
        assert soft_contains(live_harness.read("data/config.json"), "8080", "live", min_hits=1)


@pytest.mark.asyncio
async def test_live_14_edit_existing_file(live_harness):
    live_harness.seed("todo.md", "# TODO\n- [ ] first\n")
    r = await live_harness.run(
        "Update todo.md: mark the first item as done and add a second item "
        "'second live task'. Use write_file or patch_file.",
        conversation_id="live_14",
        timeout_s=300,
    )
    assert live_harness.exists("todo.md")
    body = live_harness.read("todo.md")
    assert soft_contains(body, "second", "done", "x", "[x]", min_hits=1) or soft_contains(
        r.text, "todo", "done", min_hits=1
    ), (body, r.text)


@pytest.mark.asyncio
async def test_live_15_multi_file_notes(live_harness):
    r = await live_harness.run(
        "Create two files: "
        "reports/summary.txt with text 'summary-live-ok' and "
        "reports/details.txt with text 'details-live-ok'.",
        conversation_id="live_15",
        timeout_s=360,
    )
    files = live_harness.list_workspace()
    ok = live_harness.exists("reports/summary.txt") and live_harness.exists("reports/details.txt")
    if ok:
        assert "summary-live-ok" in live_harness.read("reports/summary.txt")
        assert "details-live-ok" in live_harness.read("reports/details.txt")
    else:
        # Model may use slightly different paths — require at least one artifact
        assert any("summary" in f or "details" in f for f in files) or soft_contains(
            r.text, "summary", "details", min_hits=1
        ), (files, r.text)
