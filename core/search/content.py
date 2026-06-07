"""Fetch page content and convert HTML to readable text."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any

import aiohttp

from core.config_utils import resolve_env_refs
from core.search.config import SearchConfig
from core.search.engine import get_search_config
from core.tools.browser.policy import validate_fetch_url

_STRIP_TAGS = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S)
_BLOCK_BREAK = re.compile(r"</(p|div|section|article|li|h[1-6]|tr|br)\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "tr", "br"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", " ".join(self._parts))


def html_to_text(raw: str) -> str:
    """Best-effort HTML → plain text without extra dependencies."""
    if not raw or "<" not in raw:
        return raw.strip()

    cleaned = _STRIP_TAGS.sub(" ", raw)
    cleaned = _BLOCK_BREAK.sub("\n", cleaned)

    try:
        parser = _HTMLTextExtractor()
        parser.feed(cleaned)
        parser.close()
        text = parser.get_text()
    except Exception:
        text = _TAG_RE.sub(" ", cleaned)

    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _firecrawl_cfg(config: SearchConfig) -> dict[str, Any]:
    block = getattr(config, "firecrawl", {}) or {}
    if not block.get("enabled"):
        return {}
    key = str(resolve_env_refs(block.get("api_key") or "")).strip()
    if not key:
        return {}
    return {
        "api_key": key,
        "base_url": str(
            resolve_env_refs(block.get("base_url") or "https://api.firecrawl.dev/v2")
        ).rstrip("/"),
    }


async def scrape_firecrawl(url: str, *, api_key: str, base_url: str) -> str:
    endpoint = f"{base_url.rstrip('/')}/scrape"
    payload = {"url": url, "formats": ["markdown"]}
    headers = {
        "Authorization": f"Bearer {api_key}",
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
                raise RuntimeError(f"Firecrawl scrape HTTP {resp.status}: {body[:300]}")
            data = json.loads(body)

    if not data.get("success", True) and data.get("error"):
        raise RuntimeError(str(data.get("error")))

    block = data.get("data") or {}
    content = str(block.get("markdown") or block.get("content") or "").strip()
    if not content:
        raise RuntimeError("Firecrawl scrape returned empty content")
    return content


async def fetch_page_content(
    url: str,
    *,
    method: str = "GET",
    search_config: SearchConfig | None = None,
    max_chars: int = 8000,
) -> tuple[int, str]:
    """Fetch a URL and return readable text (markdown/text, not raw HTML when possible)."""
    url = validate_fetch_url(url)
    cfg = search_config or get_search_config()
    fc = _firecrawl_cfg(cfg)

    if method.upper() == "GET" and fc:
        try:
            text = await scrape_firecrawl(url, **fc)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (truncated, total length: {len(text)})"
            return 200, text
        except Exception:
            pass

    headers = {
        "User-Agent": "HelixAgent/1.0",
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.8",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        if method.upper() == "GET":
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                status = response.status
                content_type = (response.headers.get("Content-Type") or "").lower()
                raw = await response.text()
        else:
            async with session.post(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                status = response.status
                content_type = (response.headers.get("Content-Type") or "").lower()
                raw = await response.text()

    if "html" in content_type or raw.lstrip().startswith("<"):
        content = html_to_text(raw)
        if not content:
            content = raw
    else:
        content = raw

    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n... (truncated, total length: {len(content)})"

    return status, content