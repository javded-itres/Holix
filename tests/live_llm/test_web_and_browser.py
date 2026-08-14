"""Live LLM: web search / browser (optional, network-dependent)."""

from __future__ import annotations

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm, pytest.mark.slow]


@pytest.mark.asyncio
async def test_live_40_web_search_known_topic(live_harness):
    """Search/fetch public info about Python; require grounded facts in the answer."""
    r = await live_harness.run(
        "Use tools to gather info about the Python programming language:\n"
        "1) Prefer web_search query: 'Python programming language'\n"
        "2) If search fails, use fetch_url on "
        "https://en.wikipedia.org/wiki/Python_(programming_language)\n"
        "Then give 2 short bullet facts. Mention Python and either Guido, 1991, "
        "or that it is a programming language.",
        conversation_id="live_40",
        timeout_s=480,
        retries=2,
    )
    assert r.text.strip(), "empty answer"
    tools = set(r.tool_names())
    # Must actually use a network tool OR still produce grounded answer
    assert tools.intersection({"web_search", "fetch_url", "web_fetch"}) or soft_contains(
        r.text, "python", min_hits=1
    ), (tools, r.text)
    assert soft_contains(
        r.text,
        "python",
        "language",
        "program",
        "guido",
        "1991",
        "язык",
        "программ",
        min_hits=1,
    ), r.text


@pytest.mark.asyncio
async def test_live_41_fetch_public_info(live_harness):
    r = await live_harness.run(
        "What is HTTP status code 404? One sentence. " "You may use web search tools if helpful.",
        conversation_id="live_41",
        timeout_s=300,
    )
    assert soft_contains(r.text, "not found", "404", "не найден", min_hits=1), r.text


@pytest.mark.asyncio
async def test_live_42_browser_optional(live_harness_browser):
    """Browser tools enabled: open example.com and report the heading."""
    r = await live_harness_browser.run(
        "Use browser tools in this order:\n"
        "1) browser_open url=https://example.com\n"
        "2) browser_snapshot\n"
        "Then report the main page heading. "
        "The heading must include 'Example Domain'. "
        "If browser tools fail after trying, use fetch_url https://example.com and extract the heading.",
        conversation_id="live_42",
        timeout_s=540,
        retries=2,
    )
    assert r.text.strip(), "empty answer"
    tools = set(r.tool_names())
    used_browser_or_fetch = tools.intersection(
        {"browser_open", "browser_snapshot", "fetch_url", "web_fetch"}
    )
    assert used_browser_or_fetch or soft_contains(
        r.text, "example domain", "example", min_hits=1
    ), (tools, r.text)
    assert soft_contains(
        r.text,
        "example domain",
        "example",
        "domain",
        min_hits=1,
    ), r.text


@pytest.mark.asyncio
async def test_live_43_research_and_write_report(live_harness):
    r = await live_harness.run(
        "Research briefly (tools optional) what a REST API is. "
        "Write a short report to research/rest_api.md with at least 3 bullet points. "
        "Include the phrase REST-LIVE-REPORT somewhere in the file.",
        conversation_id="live_43",
        timeout_s=480,
    )
    files = live_harness.list_workspace()
    md = [f for f in files if f.endswith(".md")]
    if md:
        body = "\n".join(live_harness.read(f) for f in md)
        assert soft_contains(body, "REST", "rest", "API", "LIVE", min_hits=1), body
    else:
        assert soft_contains(r.text, "REST", "API", "report", min_hits=1), (files, r.text)
