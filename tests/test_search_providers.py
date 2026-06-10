"""Tests for multi-provider web search."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from core.search.config import SearchConfig
from core.search.engine import SearchEngine
from core.search.providers import search_duckduckgo, search_firecrawl, search_searxng


@pytest.mark.asyncio
async def test_duckduckgo_parses_related_topics() -> None:
    payload = {
        "Abstract": "Helix is an agent.",
        "AbstractURL": "https://example.com",
        "Heading": "Helix",
        "RelatedTopics": [
            {"Text": "Topic one", "FirstURL": "https://a.example"},
        ],
    }

    class FakeResp:
        status = 200

        async def json(self):
            return payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def get(self, *a, **k):
            return FakeResp()

    with patch("core.search.providers.aiohttp.ClientSession", return_value=FakeSession()):
        hits = await search_duckduckgo("helix", max_results=3)
    assert len(hits) >= 2
    assert hits[0].source == "duckduckgo"


@pytest.mark.asyncio
async def test_searxng_parses_results() -> None:
    payload = {
        "results": [
            {"title": "A", "url": "https://a.test", "content": "snippet a"},
        ]
    }

    class FakeResp:
        status = 200

        async def json(self, content_type=None):
            return payload

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def get(self, *a, **k):
            return FakeResp()

    with patch("core.search.providers.aiohttp.ClientSession", return_value=FakeSession()):
        hits = await search_searxng(
            "query",
            max_results=5,
            base_url="http://127.0.0.1:8080",
        )
    assert len(hits) == 1
    assert hits[0].url == "https://a.test"


@pytest.mark.asyncio
async def test_firecrawl_parses_web_array() -> None:
    payload = {
        "success": True,
        "data": {
            "web": [
                {"title": "Page", "url": "https://x.dev", "description": "desc"},
            ]
        },
    }

    class FakeResp:
        status = 200

        async def text(self):
            return json.dumps(payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def post(self, *a, **k):
            return FakeResp()

    with patch("core.search.providers.aiohttp.ClientSession", return_value=FakeSession()):
        hits = await search_firecrawl(
            "ai",
            max_results=3,
            api_key="fc-test",
        )
    assert hits[0].title == "Page"


@pytest.mark.asyncio
async def test_engine_first_success_stops_after_provider() -> None:
    cfg = SearchConfig.from_dict(
        {
            "strategy": "first_success",
            "providers": ["duckduckgo", "searxng"],
            "duckduckgo": {"enabled": True},
            "searxng": {"enabled": True, "base_url": "http://localhost"},
        }
    )
    engine = SearchEngine(cfg)

    async def fake_ddg(*a, **k):
        from core.search.providers import SearchHit

        return [SearchHit("T", "https://t", source="duckduckgo")]

    async def fake_searx(*a, **k):
        raise AssertionError("should not call searxng after duckduckgo success")

    with patch.dict(
        "core.search.engine.PROVIDER_FN",
        {"duckduckgo": fake_ddg, "searxng": fake_searx},
    ):
        out = await engine.search("q", max_results=2)
    assert "duckduckgo" in out
    assert "https://t" in out


def test_search_config_enabled_providers() -> None:
    sc = SearchConfig.from_dict(
        {
            "providers": ["firecrawl", "duckduckgo"],
            "duckduckgo": {"enabled": False},
            "firecrawl": {"enabled": True, "api_key": "x"},
        }
    )
    assert sc.enabled_providers() == ["firecrawl"]