"""Playwright browser sessions keyed by conversation_id."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_playwright_module: Any = None
_manager: BrowserSessionManager | None = None


def _import_playwright():
    global _playwright_module
    if _playwright_module is None:
        try:
            from playwright import async_api as pw

            _playwright_module = pw
        except ImportError as e:
            raise ImportError(
                "Playwright is not installed. Run: uv sync --extra browser && playwright install chromium"
            ) from e
    return _playwright_module


@dataclass
class BrowserSession:
    conversation_id: str
    playwright: Any
    browser: Any
    context: Any
    page: Any
    refs: dict[str, str] = field(default_factory=dict)
    last_used: float = field(default_factory=time.time)
    headless: bool = True


class BrowserSessionManager:
    """One browser context per conversation_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()
        self._pw_instance: Any = None

    async def _ensure_playwright(self) -> Any:
        if self._pw_instance is None:
            pw = _import_playwright()
            self._pw_instance = await pw.async_playwright().start()
        return self._pw_instance

    async def get_or_create(
        self,
        conversation_id: str,
        *,
        headless: bool | None = None,
    ) -> BrowserSession:
        async with self._lock:
            session = self._sessions.get(conversation_id)
            if session is not None:
                session.last_used = time.time()
                return session

            pw = await self._ensure_playwright()
            use_headless = settings.browser_headless if headless is None else headless
            browser = await pw.chromium.launch(headless=use_headless)
            context = await browser.new_context(
                viewport={
                    "width": settings.browser_viewport_width,
                    "height": settings.browser_viewport_height,
                }
            )
            page = await context.new_page()
            session = BrowserSession(
                conversation_id=conversation_id,
                playwright=pw,
                browser=browser,
                context=context,
                page=page,
                headless=use_headless,
            )
            self._sessions[conversation_id] = session
            logger.info("Browser session created for %s", conversation_id)
            return session

    async def close(self, conversation_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(conversation_id, None)
        if not session:
            return False
        try:
            await session.context.close()
            await session.browser.close()
        except Exception as e:
            logger.warning("Error closing browser for %s: %s", conversation_id, e)
        return True

    async def close_all(self) -> int:
        ids = list(self._sessions.keys())
        count = 0
        for cid in ids:
            if await self.close(cid):
                count += 1
        if self._pw_instance is not None:
            try:
                await self._pw_instance.stop()
            except Exception:
                pass
            self._pw_instance = None
        return count


def get_browser_session_manager() -> BrowserSessionManager:
    global _manager
    if _manager is None:
        _manager = BrowserSessionManager()
    return _manager