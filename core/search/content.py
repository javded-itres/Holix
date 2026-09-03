"""Fetch page content and convert HTML to readable text."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

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


_SKIP_HREF_PREFIXES = ("javascript:", "mailto:", "tel:", "data:", "blob:")
_MAX_PAGE_LINKS = 40


class _HTMLLinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []
        self._in_a = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = ""
        for key, val in attrs:
            if key.lower() == "href":
                href = (val or "").strip()
                break
        self._in_a = True
        self._href = href
        self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._in_a:
            return
        label = " ".join(self._text).strip()
        if self._href:
            self.links.append((self._href, label))
        self._in_a = False
        self._href = ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            text = data.strip()
            if text:
                self._text.append(text)


def _normalize_page_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def extract_page_links(
    raw_html: str, *, page_url: str, limit: int = _MAX_PAGE_LINKS
) -> list[tuple[str, str]]:
    """Absolute http(s) links from ``<a href>``, same host first. Never invents paths."""
    if not raw_html or "<" not in raw_html:
        return []
    try:
        parser = _HTMLLinkExtractor()
        parser.feed(raw_html)
        parser.close()
        pairs = parser.links
    except Exception:
        pairs = []

    page_host = (urlsplit(page_url).netloc or "").lower()
    page_norm = _normalize_page_url(page_url)
    same: list[tuple[str, str]] = []
    other: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, label in pairs:
        raw = (href or "").strip()
        if not raw or raw.startswith("#") or raw.lower().startswith(_SKIP_HREF_PREFIXES):
            continue
        abs_url = urljoin(page_url, raw)
        parsed = urlsplit(abs_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        norm = _normalize_page_url(abs_url)
        if norm == page_norm or norm in seen:
            continue
        seen.add(norm)
        item = (
            urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")),
            label,
        )
        if parsed.netloc.lower() == page_host:
            same.append(item)
        else:
            other.append(item)
        if len(seen) >= limit:
            break
    return (same + other)[:limit]


_MD_LINK = re.compile(r"\[([^\]]{0,80})\]\((https?://[^)\s]+)\)")


def extract_markdown_links(
    text: str, *, page_url: str, limit: int = _MAX_PAGE_LINKS
) -> list[tuple[str, str]]:
    page_norm = _normalize_page_url(page_url)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, href in _MD_LINK.findall(text or ""):
        abs_url = urljoin(page_url, href.strip())
        parsed = urlsplit(abs_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        norm = _normalize_page_url(abs_url)
        if norm == page_norm or norm in seen:
            continue
        seen.add(norm)
        out.append(
            (
                urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")),
                label.strip(),
            )
        )
        if len(out) >= limit:
            break
    return out


_FANOUT_HINT_MIN = 4


def format_page_links(links: list[tuple[str, str]]) -> str:
    if not links:
        return ""
    lines = ["## Links on this page"]
    for href, label in links:
        if label and label not in href:
            lines.append(f"- {href} ({label})")
        else:
            lines.append(f"- {href}")
    if len(links) >= _FANOUT_HINT_MIN:
        lines.append("")
        lines.append("## Many links")
        lines.append(
            "If the task is analyzing this site/resource or finding information on it, "
            "call `research_site_pages` with a bounded subset of the links above "
            "(same host, never invent paths). Do not fetch dozens of pages on the main "
            "agent and do not use `web_researcher` for same-site links."
        )
    return "\n".join(lines)


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
            links = extract_markdown_links(text, page_url=url)
            link_block = format_page_links(links)
            if link_block and "## Links on this page" not in text:
                budget = max(max_chars - len(link_block) - 2, 500)
                if len(text) > budget:
                    text = text[:budget] + f"\n\n... (truncated, total length: {len(text)})"
                text = f"{text}\n\n{link_block}"
            elif len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (truncated, total length: {len(text)})"
            return 200, text
        except Exception:
            pass

    headers = {
        "User-Agent": "HolixAgent/1.0",
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

    link_block = ""
    if "html" in content_type or raw.lstrip().startswith("<"):
        links = extract_page_links(raw, page_url=url)
        link_block = format_page_links(links)
        content = html_to_text(raw)
        if not content:
            content = raw
    else:
        content = raw

    if link_block:
        # Keep the link map even when the body is truncated.
        budget = max(max_chars - len(link_block) - 2, 500)
        if len(content) > budget:
            content = content[:budget] + f"\n\n... (truncated, total length: {len(content)})"
        content = f"{content}\n\n{link_block}"
    elif len(content) > max_chars:
        content = content[:max_chars] + f"\n\n... (truncated, total length: {len(content)})"

    return status, content
