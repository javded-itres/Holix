"""Playwright browser sessions keyed by conversation_id."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import settings
from core.paths import resolve_profile_data_dir

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


def _safe_conversation_id(conversation_id: str) -> str:
    return conversation_id.replace("/", "_").replace("\\", "_") or "default"


def browser_videos_dir() -> Path:
    path = resolve_profile_data_dir() / "browser_videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _staging_dir(conversation_id: str) -> Path:
    path = browser_videos_dir() / "staging" / _safe_conversation_id(conversation_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    recording: bool = False
    video_staging_dir: str | None = None


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

    def _viewport(self) -> dict[str, int]:
        return {
            "width": settings.browser_viewport_width,
            "height": settings.browser_viewport_height,
        }

    def _context_kwargs(self, *, record_dir: Path | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"viewport": self._viewport()}
        if record_dir is not None:
            record_dir.mkdir(parents=True, exist_ok=True)
            # Clear prior staging artifacts so Playwright writes a single fresh file.
            for old in record_dir.glob("*"):
                try:
                    if old.is_file():
                        old.unlink()
                except OSError:
                    pass
            kwargs["record_video_dir"] = str(record_dir)
            kwargs["record_video_size"] = self._viewport()
        return kwargs

    async def _new_session(
        self,
        conversation_id: str,
        *,
        headless: bool,
        record: bool,
    ) -> BrowserSession:
        pw = await self._ensure_playwright()
        browser = await pw.chromium.launch(headless=headless)
        staging = _staging_dir(conversation_id) if record else None
        context = await browser.new_context(**self._context_kwargs(record_dir=staging))
        page = await context.new_page()
        session = BrowserSession(
            conversation_id=conversation_id,
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
            headless=headless,
            recording=record,
            video_staging_dir=str(staging) if staging else None,
        )
        self._sessions[conversation_id] = session
        logger.info(
            "Browser session created for %s (recording=%s)",
            conversation_id,
            record,
        )
        return session

    async def _recreate_context(
        self,
        session: BrowserSession,
        *,
        record: bool,
        restore_url: str | None,
    ) -> BrowserSession:
        """Close current context and open a new one on the same browser."""
        try:
            await session.context.close()
        except Exception as e:
            logger.warning("Error closing browser context for %s: %s", session.conversation_id, e)

        staging = _staging_dir(session.conversation_id) if record else None
        context = await session.browser.new_context(**self._context_kwargs(record_dir=staging))
        page = await context.new_page()
        session.context = context
        session.page = page
        session.refs.clear()
        session.recording = record
        session.video_staging_dir = str(staging) if staging else None
        session.last_used = time.time()

        if restore_url and restore_url not in ("about:blank", "chrome://newtab/"):
            try:
                await page.goto(restore_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                logger.warning(
                    "Could not restore URL %s after context recreate: %s",
                    restore_url,
                    e,
                )
        return session

    async def _finalize_video(self, session: BrowserSession) -> Path | None:
        """Close context to flush Playwright video and move it to browser_videos/."""
        if not session.recording:
            return None

        video = getattr(session.page, "video", None)
        try:
            await session.context.close()
        except Exception as e:
            logger.warning(
                "Error closing context while finalizing video for %s: %s",
                session.conversation_id,
                e,
            )
            return None

        session.recording = False
        staging = session.video_staging_dir
        session.video_staging_dir = None

        raw_path: Path | None = None
        if video is not None:
            try:
                path_str = await video.path()
                if path_str:
                    raw_path = Path(path_str)
            except Exception as e:
                logger.warning("Could not resolve video path for %s: %s", session.conversation_id, e)

        if raw_path is None or not raw_path.is_file():
            # Fallback: pick newest file in staging
            if staging:
                candidates = sorted(
                    Path(staging).glob("*.webm"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                raw_path = candidates[0] if candidates else None

        if raw_path is None or not raw_path.is_file():
            return None

        safe = _safe_conversation_id(session.conversation_id)
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = browser_videos_dir() / f"{safe}_{ts}.webm"
        try:
            shutil.move(str(raw_path), str(dest))
        except OSError:
            shutil.copy2(str(raw_path), str(dest))
            try:
                raw_path.unlink()
            except OSError:
                pass
        return dest

    async def get_or_create(
        self,
        conversation_id: str,
        *,
        headless: bool | None = None,
        record: bool = False,
    ) -> BrowserSession:
        async with self._lock:
            session = self._sessions.get(conversation_id)
            if session is not None:
                session.last_used = time.time()
                if record and not session.recording:
                    url = getattr(session.page, "url", None)
                    return await self._recreate_context(session, record=True, restore_url=url)
                return session

            use_headless = settings.browser_headless if headless is None else headless
            return await self._new_session(
                conversation_id, headless=use_headless, record=record
            )

    async def start_recording(self, conversation_id: str) -> tuple[BrowserSession, bool]:
        """
        Start video recording for the conversation session.

        Returns (session, already_recording).
        """
        async with self._lock:
            session = self._sessions.get(conversation_id)
            if session is not None and session.recording:
                session.last_used = time.time()
                return session, True

            if session is None:
                use_headless = settings.browser_headless
                session = await self._new_session(
                    conversation_id, headless=use_headless, record=True
                )
                return session, False

            url = getattr(session.page, "url", None)
            session = await self._recreate_context(session, record=True, restore_url=url)
            return session, False

    async def stop_recording(
        self,
        conversation_id: str,
        *,
        keep_session: bool = True,
    ) -> Path | None:
        """
        Stop recording and return the saved WebM path (or None).

        When keep_session is True, opens a fresh non-recording context on the same browser
        and restores the last URL when possible.
        """
        async with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                return None
            if not session.recording:
                return None

            url = getattr(session.page, "url", None)
            video_path = await self._finalize_video(session)

            if keep_session:
                context = await session.browser.new_context(**self._context_kwargs(record_dir=None))
                page = await context.new_page()
                session.context = context
                session.page = page
                session.refs.clear()
                session.last_used = time.time()
                if url and url not in ("about:blank", "chrome://newtab/"):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    except Exception as e:
                        logger.warning("Could not restore URL after stop_recording: %s", e)
            else:
                try:
                    await session.browser.close()
                except Exception as e:
                    logger.warning("Error closing browser after stop_recording: %s", e)
                self._sessions.pop(conversation_id, None)

            return video_path

    async def close(self, conversation_id: str) -> tuple[bool, Path | None]:
        """Close session. Returns (was_open, saved_video_path_if_any)."""
        async with self._lock:
            session = self._sessions.pop(conversation_id, None)
        if not session:
            return False, None

        video_path: Path | None = None
        try:
            if session.recording:
                video_path = await self._finalize_video(session)
            else:
                await session.context.close()
        except Exception as e:
            logger.warning("Error closing browser context for %s: %s", conversation_id, e)
        try:
            await session.browser.close()
        except Exception as e:
            logger.warning("Error closing browser for %s: %s", conversation_id, e)
        return True, video_path

    async def close_all(self) -> int:
        ids = list(self._sessions.keys())
        count = 0
        for cid in ids:
            closed, _ = await self.close(cid)
            if closed:
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
