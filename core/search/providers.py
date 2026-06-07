"""Individual search provider implementations."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from core.config_utils import resolve_env_refs


class SearchHit:
    __slots__ = ("title", "url", "snippet", "source")

    def __init__(
        self,
        title: str,
        url: str,
        snippet: str = "",
        *,
        source: str = "",
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source


async def search_duckduckgo(
    query: str,
    *,
    max_results: int = 5,
    **_cfg: Any,
) -> list[SearchHit]:
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    }
    hits: list[SearchHit] = []

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"DuckDuckGo HTTP {resp.status}")
            data = await resp.json()

    if data.get("Abstract"):
        hits.append(
            SearchHit(
                title=data.get("Heading") or "Summary",
                url=data.get("AbstractURL") or "",
                snippet=str(data.get("Abstract", ""))[:500],
                source="duckduckgo",
            )
        )

    for topic in data.get("RelatedTopics") or []:
        if len(hits) >= max_results:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            hits.append(
                SearchHit(
                    title=str(topic.get("Text", ""))[:200],
                    url=str(topic.get("FirstURL", "")),
                    snippet=str(topic.get("Text", ""))[:400],
                    source="duckduckgo",
                )
            )

    return hits[:max_results]


async def search_searxng(
    query: str,
    *,
    max_results: int = 5,
    base_url: str = "",
    categories: str = "general",
    language: str = "",
    safesearch: int = 0,
    **_cfg: Any,
) -> list[SearchHit]:
    base = str(resolve_env_refs(base_url or "")).rstrip("/")
    if not base:
        raise RuntimeError("SearXNG base_url is not configured")

    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "categories": categories or "general",
        "safesearch": int(safesearch),
    }
    if language:
        params["language"] = language

    endpoint = f"{base}/search"
    hits: list[SearchHit] = []

    async with aiohttp.ClientSession() as session:
        async with session.get(
            endpoint,
            params=params,
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"SearXNG HTTP {resp.status}: {body[:200]}")
            data = await resp.json(content_type=None)

    for item in data.get("results") or []:
        if len(hits) >= max_results:
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if title or url:
            hits.append(SearchHit(title=title or url, url=url, snippet=snippet[:500], source="searxng"))

    return hits


async def search_firecrawl(
    query: str,
    *,
    max_results: int = 5,
    api_key: str = "",
    base_url: str = "https://api.firecrawl.dev/v2",
    country: str = "US",
    **_cfg: Any,
) -> list[SearchHit]:
    key = str(resolve_env_refs(api_key or "")).strip()
    if not key:
        raise RuntimeError("Firecrawl API key is not configured (set FIRECRAWL_API_KEY)")

    root = str(resolve_env_refs(base_url or "https://api.firecrawl.dev/v2")).rstrip("/")
    endpoint = f"{root}/search"
    payload = {
        "query": query,
        "limit": max(1, min(max_results, 20)),
        "country": country or "US",
        "sources": [{"type": "web"}],
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Firecrawl HTTP {resp.status}: {body[:300]}")
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Firecrawl invalid JSON: {e}") from e

    if not data.get("success", True) and data.get("error"):
        raise RuntimeError(str(data.get("error")))

    block = data.get("data") or {}
    items = block.get("web") or block.get("results") or []
    hits: list[SearchHit] = []

    for item in items:
        if len(hits) >= max_results:
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(
            item.get("description")
            or item.get("markdown")
            or item.get("snippet")
            or ""
        ).strip()
        if title or url:
            hits.append(
                SearchHit(title=title or url, url=url, snippet=snippet[:600], source="firecrawl")
            )

    return hits


PROVIDER_FN = {
    "duckduckgo": search_duckduckgo,
    "searxng": search_searxng,
    "firecrawl": search_firecrawl,
}