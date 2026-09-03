"""Per-conversation fetch_url memory (do not refetch in the same session)."""

from __future__ import annotations

import pytest
from core.tools.web_fetch_memory import (
    already_fetched_message,
    lookup_fetch,
    normalize_fetch_url,
    remember_fetch,
    reset_fetch_memory,
)
from core.tools.web_search import WebFetchTool


@pytest.fixture(autouse=True)
def _clear_fetch_memory():
    reset_fetch_memory()
    yield
    reset_fetch_memory()


def test_normalize_fetch_url_strips_slash_and_fragment() -> None:
    assert normalize_fetch_url("https://Bot24u.ru/en/#hero") == "https://bot24u.ru/en"


def test_remember_and_lookup_roundtrip() -> None:
    remember_fetch("cid-a", "https://example.com/page/", 200, "Hello world")
    hit = lookup_fetch("cid-a", "https://example.com/page")
    assert hit == (200, "Hello world")
    assert lookup_fetch("cid-b", "https://example.com/page") is None


def test_already_fetched_message_warns_on_404() -> None:
    text = already_fetched_message("https://x", 404, '{"detail":"Not Found"}')
    assert "HTTP 404" in text
    assert "Do not refetch" in text
    assert "sibling" in text


@pytest.mark.asyncio
async def test_fetch_url_refuses_duplicate_in_same_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.tools import execution_context as ctx

    calls = {"n": 0}

    async def fake_fetch(url: str, method: str = "GET"):
        calls["n"] += 1
        return 200, f"body for {url}"

    monkeypatch.setattr("core.tools.web_search.fetch_page_content", fake_fetch)
    token = ctx.conversation_scope("sess-1")
    try:
        tool = WebFetchTool()
        first = await tool.execute("https://bot24u.ru/")
        second = await tool.execute("https://bot24u.ru")
    finally:
        ctx.reset_conversation_scope(token)

    assert first.startswith("HTTP 200")
    assert "Already fetched" in second
    assert calls["n"] == 1
