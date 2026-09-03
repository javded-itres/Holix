"""Fan-out real page URLs to page_analyst sub-agents (site/resource analysis)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from core.config_utils import is_subagents_enabled
from core.tools.base import BaseTool
from core.tools.web_fetch_memory import lookup_fetch, normalize_fetch_url, remember_fetch

logger = logging.getLogger(__name__)

PAGE_ANALYST_TYPE = "page_analyst"
DEFAULT_MAX_PAGES = 8
HARD_MAX_PAGES = 12
PAGE_WAIT_TIMEOUT_S = 180.0
SLOT_WAIT_TIMEOUT_S = 120.0
REPORT_MAX_CHARS = 4000
DIRECT_FETCH_MAX_CHARS = 2000

_SKIP_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)
_SPLIT_URLS = re.compile(r"[\s,;]+")


@dataclass
class SelectedUrls:
    to_fetch: list[str] = field(default_factory=list)
    cached: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    capped: list[str] = field(default_factory=list)
    preferred_host: str = ""


def coerce_url_list(urls: Any) -> list[str]:
    """Accept a list, JSON array string, or whitespace/comma-separated string."""
    if urls is None:
        return []
    if isinstance(urls, str):
        text = urls.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return coerce_url_list(parsed)
        return [part.strip().strip("<>") for part in _SPLIT_URLS.split(text) if part.strip()]
    if isinstance(urls, dict):
        raw = urls.get("url") or urls.get("href") or urls.get("link")
        return coerce_url_list(str(raw) if raw else "")
    if isinstance(urls, (list, tuple, set)):
        out: list[str] = []
        for item in urls:
            out.extend(coerce_url_list(item))
        return out
    return coerce_url_list(str(urls))


def _host(url: str) -> str:
    return (urlsplit(url).netloc or "").lower()


def _is_http_url(url: str) -> bool:
    scheme = (urlsplit(url).scheme or "").lower()
    return scheme in {"http", "https"} and bool(urlsplit(url).netloc)


def _looks_like_asset(url: str) -> bool:
    path = (urlsplit(url).path or "").lower()
    return path.endswith(_SKIP_SUFFIXES)


def select_research_urls(
    urls: Any,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    conversation_id: str | None = None,
) -> SelectedUrls:
    """Dedupe, drop junk, prefer the first URL's host, honour fetch memory."""
    try:
        cap = int(max_pages)
    except (TypeError, ValueError):
        cap = DEFAULT_MAX_PAGES
    cap = max(1, min(cap, HARD_MAX_PAGES))

    selected = SelectedUrls()
    seen: set[str] = set()
    same_host: list[str] = []
    other_host: list[str] = []

    for raw in coerce_url_list(urls):
        key = normalize_fetch_url(raw)
        if not key:
            selected.invalid.append(raw)
            continue
        if not _is_http_url(key) or _looks_like_asset(key):
            selected.invalid.append(raw)
            continue
        if key in seen:
            continue
        seen.add(key)
        if not selected.preferred_host:
            selected.preferred_host = _host(key)
        if selected.preferred_host and _host(key) == selected.preferred_host:
            same_host.append(key)
        else:
            other_host.append(key)

    ordered = same_host + other_host
    kept: list[str] = []
    for url in ordered:
        if conversation_id:
            prior = lookup_fetch(conversation_id, url)
            if prior is not None:
                status, excerpt = prior
                selected.cached.append(
                    {
                        "url": url,
                        "success": int(status) < 400,
                        "http_status": int(status),
                        "report": (excerpt or "").strip()[:REPORT_MAX_CHARS],
                        "cached": True,
                        "job_id": None,
                    }
                )
                continue
        kept.append(url)

    selected.to_fetch = kept[:cap]
    selected.capped = kept[cap:]
    return selected


def page_analyst_task(url: str, goal: str) -> str:
    want = (goal or "").strip() or "Summarize what this page is and any facts relevant to the user."
    return (
        f"Fetch this exact URL with fetch_url once. Do not fetch any other URL. "
        f"Do not search the web. Do not invent paths.\n\n"
        f"URL: {url}\n\n"
        f"Parent task / what to extract:\n{want}\n\n"
        "Then write a short briefing (facts, products, contacts, claims) from that page only. "
        "If HTTP 404/403/410, report the status and stop. "
        "You may list a few same-host links from `## Links on this page` that look relevant; "
        "do not fetch them."
    )


def _max_concurrent(parent: Any) -> int:
    cfg = getattr(parent, "config", None)
    try:
        n = int(getattr(cfg, "subagent_max_concurrent", 4) or 4)
    except (TypeError, ValueError):
        n = 4
    return max(1, n)


def _clip_report(text: str) -> str:
    body = (text or "").strip()
    if len(body) <= REPORT_MAX_CHARS:
        return body
    return body[:REPORT_MAX_CHARS] + f"\n\n... (truncated, total length: {len(body)})"


async def _wait_until_slot(mgr: Any, *, cap: int, timeout: float = SLOT_WAIT_TIMEOUT_S) -> None:
    limit = max(1, int(cap))
    deadline = time.monotonic() + max(1.0, float(timeout))
    while True:
        active = mgr.list_active() if hasattr(mgr, "list_active") else []
        if len(active) < limit:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"No free sub-agent slot within {int(timeout)}s ({len(active)}/{limit} running)."
            )
        await asyncio.sleep(0.2)


class ResearchSitePagesTool(BaseTool):
    """Spawn page_analyst workers for a bounded list of real page URLs."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "research_site_pages"
        self.description = (
            "Analyze several pages of one site/resource in parallel. "
            "Pass URLs copied from `## Links on this page` after the first fetch_url "
            "(never invent paths). Spawns page_analyst sub-agents in waves of "
            "subagent_max_concurrent, waits, and returns their briefings. "
            "Use when the task is site/resource analysis or finding information on "
            "that resource and the first page listed many links. "
            "Do not fetch those URLs yourself on the main agent; "
            "do not use web_researcher for same-site link fan-out."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Real http(s) URLs from `## Links on this page` (same host first). "
                        "Do not guess /admin, /dashboard, /employee, …"
                    ),
                },
                "goal": {
                    "type": "string",
                    "description": "What to extract or decide from those pages (the user task).",
                },
                "max_pages": {
                    "type": "integer",
                    "description": (
                        f"Max pages to fetch (default {DEFAULT_MAX_PAGES}, hard cap {HARD_MAX_PAGES})."
                    ),
                    "default": DEFAULT_MAX_PAGES,
                },
            },
            "required": ["urls", "goal"],
        }

    async def execute(
        self,
        urls: Any,
        goal: str,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> str:
        want = (goal or "").strip()
        if not want:
            return json.dumps(
                {"ok": False, "error": "goal is required (what to extract from the pages)."},
                ensure_ascii=False,
            )

        from core.tools.execution_context import get_conversation_id

        cid = get_conversation_id()
        selected = select_research_urls(urls, max_pages=max_pages, conversation_id=cid)
        if not selected.to_fetch and not selected.cached:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "No usable http(s) URLs. Copy links from `## Links on this page`; "
                        "do not invent paths."
                    ),
                    "invalid": selected.invalid[:20],
                },
                ensure_ascii=False,
            )

        pages: list[dict[str, Any]] = list(selected.cached)
        agent = self._parent
        cfg = getattr(agent, "config", None)
        used_subagents = False

        if selected.to_fetch and is_subagents_enabled(cfg) and getattr(agent, "subagents", None):
            used_subagents = True
            try:
                spawned = await self._spawn_and_collect(selected.to_fetch, want)
                pages.extend(spawned)
            except Exception as exc:
                logger.warning("research_site_pages sub-agent fan-out failed: %s", exc)
                pages.append(
                    {
                        "url": None,
                        "success": False,
                        "error": f"Sub-agent fan-out failed: {exc}",
                    }
                )
                direct = await self._direct_fetch(selected.to_fetch, cid)
                pages.extend(direct)
                used_subagents = False
        elif selected.to_fetch:
            pages.extend(await self._direct_fetch(selected.to_fetch, cid))

        if used_subagents:
            mode = "page_analyst"
        elif any(not page.get("cached") for page in pages):
            mode = "direct_fetch"
        else:
            mode = "cached"
        payload: dict[str, Any] = {
            "ok": True,
            "goal": want,
            "mode": mode,
            "preferred_host": selected.preferred_host,
            "pages": pages,
            "skipped_invalid": selected.invalid[:20],
            "skipped_over_cap": selected.capped,
            "hint": (
                "Synthesize the briefing from these reports. "
                "Do not fetch more URLs unless a report names a still-needed link "
                "from `## Links on this page`. Never invent paths."
            ),
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _spawn_and_collect(self, urls: list[str], goal: str) -> list[dict[str, Any]]:
        mgr = self._parent.subagents
        remaining = list(urls)
        reports: list[dict[str, Any]] = []
        cap = _max_concurrent(self._parent)

        while remaining:
            try:
                await _wait_until_slot(mgr, cap=cap)
            except TimeoutError as exc:
                for url in remaining:
                    reports.append(
                        {
                            "url": url,
                            "success": False,
                            "error": str(exc),
                            "cached": False,
                        }
                    )
                break
            active = len(mgr.list_active()) if hasattr(mgr, "list_active") else 0
            slots = max(1, cap - active)
            wave = remaining[:slots]
            remaining = remaining[slots:]
            spawned: list[tuple[str, Any]] = []
            deferred = False
            for index, url in enumerate(wave):
                task = page_analyst_task(url, goal)
                try:
                    handle, _ = await mgr.spawn_typed(PAGE_ANALYST_TYPE, task, wait=False)
                except RuntimeError as exc:
                    if "limit" in str(exc).lower():
                        remaining = wave[index:] + remaining
                        deferred = True
                        break
                    reports.append(
                        {
                            "url": url,
                            "success": False,
                            "error": str(exc),
                            "cached": False,
                        }
                    )
                    continue
                except Exception as exc:
                    reports.append(
                        {
                            "url": url,
                            "success": False,
                            "error": str(exc),
                            "cached": False,
                        }
                    )
                    continue
                spawned.append((url, handle))
            if deferred and not spawned:
                await asyncio.sleep(0.2)
                continue

            for url, handle in spawned:
                name = getattr(handle, "name", "") or PAGE_ANALYST_TYPE
                try:
                    result = await mgr.wait_for(name, timeout=PAGE_WAIT_TIMEOUT_S)
                except TimeoutError as exc:
                    reports.append(
                        {
                            "url": url,
                            "job_id": name,
                            "success": False,
                            "error": str(exc) or "wait timed out",
                            "cached": False,
                        }
                    )
                    continue
                except Exception as exc:
                    reports.append(
                        {
                            "url": url,
                            "job_id": name,
                            "success": False,
                            "error": str(exc),
                            "cached": False,
                        }
                    )
                    continue
                reports.append(
                    {
                        "url": url,
                        "job_id": name,
                        "success": bool(getattr(result, "success", False)),
                        "report": _clip_report(getattr(result, "response", "") or ""),
                        "error": getattr(result, "error", None),
                        "steps_taken": getattr(result, "steps_taken", 0),
                        "duration_ms": getattr(result, "duration_ms", 0),
                        "cached": False,
                    }
                )
        return reports

    async def _direct_fetch(self, urls: list[str], conversation_id: str) -> list[dict[str, Any]]:
        from core.search.content import fetch_page_content

        sem = asyncio.Semaphore(_max_concurrent(self._parent))

        async def one(url: str) -> dict[str, Any]:
            async with sem:
                try:
                    status, content = await fetch_page_content(
                        url, max_chars=DIRECT_FETCH_MAX_CHARS
                    )
                    remember_fetch(conversation_id, url, int(status), str(content or ""))
                    return {
                        "url": url,
                        "success": int(status) < 400,
                        "http_status": int(status),
                        "report": _clip_report(str(content or "")),
                        "cached": False,
                        "mode": "direct_fetch",
                    }
                except Exception as exc:
                    return {
                        "url": url,
                        "success": False,
                        "error": str(exc),
                        "cached": False,
                        "mode": "direct_fetch",
                    }

        return list(await asyncio.gather(*[one(u) for u in urls]))
