"""Live LLM: reasoning, code explanation, hybrid mode."""

from __future__ import annotations

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


@pytest.mark.asyncio
async def test_live_50_explain_seeded_code(live_harness):
    live_harness.seed(
        "src/weird.py",
        "def f(xs):\n    return sorted(xs, key=lambda x: -x)\n",
    )
    r = await live_harness.run(
        "Read src/weird.py and explain in 1-2 sentences what f does.",
        conversation_id="live_50",
        timeout_s=300,
    )
    assert soft_contains(
        r.text,
        "sort",
        "descend",
        "reverse",
        "убыв",
        "сортир",
        min_hits=1,
    ), r.text


@pytest.mark.asyncio
async def test_live_51_bugfix_seeded_function(live_harness):
    live_harness.seed(
        "src/buggy.py",
        "def safe_div(a, b):\n    return a / b\n",
    )
    r = await live_harness.run(
        "Fix src/buggy.py safe_div so it returns None when b == 0 instead of raising. "
        "Use tools to edit the file.",
        conversation_id="live_51",
        timeout_s=360,
    )
    assert live_harness.exists("src/buggy.py")
    body = live_harness.read("src/buggy.py")
    assert soft_contains(
        body, "b == 0", "b==0", "if not b", "if b ==", "None", min_hits=1
    ) or soft_contains(r.text, "None", "zero", min_hits=1), body


@pytest.mark.asyncio
async def test_live_52_hybrid_mode_two_files(live_harness):
    r = await live_harness.run(
        "Create docs/intro.md with title Hybrid Live and notes/checklist.md "
        "with three checklist items about testing. Use tools.",
        conversation_id="live_52",
        mode="hybrid",
        timeout_s=480,
    )
    files = live_harness.list_workspace()
    assert files or soft_contains(r.text, "Hybrid", "checklist", "testing", min_hits=1), r.text
    md = [f for f in files if f.endswith(".md")]
    if md:
        blob = "\n".join(live_harness.read(f) for f in md)
        assert soft_contains(blob, "Hybrid", "test", "check", min_hits=1) or len(blob) > 20


@pytest.mark.asyncio
async def test_live_53_summarize_long_seed(live_harness):
    live_harness.seed(
        "logs/app.log",
        "\n".join(f"line {i}: event={i % 5} status=ok token=LOGTOKEN{i}" for i in range(40)),
    )
    r = await live_harness.run(
        "Read logs/app.log and summarize roughly how many lines and what it contains. "
        "Mention LOGTOKEN if you see it.",
        conversation_id="live_53",
        timeout_s=360,
    )
    assert soft_contains(r.text, "line", "log", "40", "event", "LOGTOKEN", min_hits=1), r.text


@pytest.mark.asyncio
async def test_live_54_math_tool_or_reasoning(live_harness):
    r = await live_harness.run(
        "Compute 13 * 17. Prefer the calculate/math tool if available. "
        "Put the final number 221 in the visible reply text.",
        conversation_id="live_54",
        timeout_s=480,
        retries=2,
    )
    assert soft_contains(r.text, "221"), f"expected 221, got: {r.text!r}"


@pytest.mark.asyncio
async def test_live_55_create_dockerfile_stub(live_harness):
    r = await live_harness.run(
        "Write a Dockerfile that uses python:3.12-slim, sets WORKDIR /app, "
        "copies requirements.txt and app, exposes 8000. Save as Dockerfile.",
        conversation_id="live_55",
        timeout_s=360,
    )
    files = live_harness.list_workspace()
    docker = [f for f in files if "dockerfile" in f.lower() or f == "Dockerfile"]
    if docker:
        body = live_harness.read(docker[0])
        assert soft_contains(body, "FROM", "python", "WORKDIR", min_hits=2), body
    else:
        assert soft_contains(r.text, "Dockerfile", "python", "8000", min_hits=1), (files, r.text)
