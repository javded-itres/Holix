"""Playwright browser tools for Helix agent."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from config import settings
from core.paths import resolve_profile_data_dir
from core.tools.base import BaseTool
from core.tools.browser.policy import parse_allowed_hosts_csv, validate_browser_url
from core.tools.browser.session import get_browser_session_manager
from core.tools.browser.snapshot import build_page_snapshot
from core.tools.execution_context import get_conversation_id

if TYPE_CHECKING:
    from core.tools.registry import ToolRegistry


def _allowed_hosts() -> frozenset[str]:
    return parse_allowed_hosts_csv(settings.browser_allowed_hosts)


def _resolve_locator(session, *, ref: str = "", selector: str = ""):
    page = session.page
    if ref:
        sel = session.refs.get(ref)
        if not sel:
            raise ValueError(
                f"Unknown ref '{ref}'. Run browser_snapshot first to refresh refs."
            )
        return page.locator(sel)
    if selector:
        return page.locator(selector)
    raise ValueError("Provide ref (from snapshot) or selector")


class BrowserOpenTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_open"
        self.description = (
            "Open a URL in the browser for this conversation (creates or reuses a session). "
            "Use browser_snapshot next to see interactive elements."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "http(s) URL to open"},
                "wait_until": {
                    "type": "string",
                    "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                    "default": "domcontentloaded",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, wait_until: str = "domcontentloaded") -> str:
        try:
            normalized = validate_browser_url(url, _allowed_hosts())
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            await session.page.goto(normalized, wait_until=wait_until, timeout=60_000)
            session.refs.clear()
            return f"Opened {session.page.url} (conversation={cid})"
        except Exception as e:
            return f"browser_open error: {e}"


class BrowserSnapshotTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_snapshot"
        self.description = (
            "Capture page state: URL, title, and interactive elements with refs (e1, e2, ...). "
            "Use refs with browser_click and browser_fill."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "screenshot": {
                    "type": "boolean",
                    "description": "Save PNG screenshot under data/browser_screenshots/",
                    "default": False,
                },
            },
        }

    async def execute(self, screenshot: bool = False) -> str:
        try:
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            text, refs = await build_page_snapshot(session.page)
            session.refs = refs

            extra = ""
            if screenshot:
                out_dir = resolve_profile_data_dir() / "browser_screenshots"
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{cid.replace('/', '_')}.png"
                await session.page.screenshot(path=str(path), full_page=False)
                extra = f"\nScreenshot: {path}"

            return text + extra
        except Exception as e:
            return f"browser_snapshot error: {e}"


class BrowserClickTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_click"
        self.description = "Click an element by ref from browser_snapshot or by CSS selector."
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref e.g. e3"},
                "selector": {"type": "string", "description": "CSS selector (if ref omitted)"},
            },
        }

    async def execute(self, ref: str = "", selector: str = "") -> str:
        try:
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            loc = _resolve_locator(session, ref=ref, selector=selector)
            await loc.first.click(timeout=30_000)
            return f"Clicked {ref or selector} on {session.page.url}"
        except Exception as e:
            return f"browser_click error: {e}"


class BrowserFillTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_fill"
        self.description = "Fill an input/textarea by ref or selector."
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "selector": {"type": "string"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["text"],
        }

    async def execute(self, text: str, ref: str = "", selector: str = "") -> str:
        try:
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            loc = _resolve_locator(session, ref=ref, selector=selector)
            await loc.first.fill(text, timeout=30_000)
            return f"Filled {ref or selector}"
        except Exception as e:
            return f"browser_fill error: {e}"


class BrowserPressTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_press"
        self.description = "Press a keyboard key (Enter, Tab, Escape, etc.)."
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name, e.g. Enter"},
            },
            "required": ["key"],
        }

    async def execute(self, key: str) -> str:
        try:
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            await session.page.keyboard.press(key)
            return f"Pressed {key}"
        except Exception as e:
            return f"browser_press error: {e}"


class BrowserWaitTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_wait"
        self.description = "Wait for selector, timeout (ms), or network idle."
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "timeout_ms": {"type": "integer", "default": 5000},
                "network_idle": {"type": "boolean", "default": False},
            },
        }

    async def execute(
        self,
        selector: str = "",
        timeout_ms: int = 5000,
        network_idle: bool = False,
    ) -> str:
        try:
            cid = get_conversation_id()
            session = await get_browser_session_manager().get_or_create(cid)
            if network_idle:
                await session.page.wait_for_load_state("networkidle", timeout=timeout_ms)
            elif selector:
                await session.page.wait_for_selector(selector, timeout=timeout_ms)
            else:
                await session.page.wait_for_timeout(timeout_ms)
            return f"Wait complete ({session.page.url})"
        except Exception as e:
            return f"browser_wait error: {e}"


class BrowserCloseTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "browser_close"
        self.description = "Close the browser session for this conversation."
        self.risk_level = "low"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self) -> str:
        try:
            cid = get_conversation_id()
            closed = await get_browser_session_manager().close(cid)
            return "Browser closed." if closed else "No browser session was open."
        except Exception as e:
            return f"browser_close error: {e}"


def register_browser_tools(registry: ToolRegistry) -> None:
    """Register browser tools when enable_browser_tools is True."""
    registry.register(BrowserOpenTool())
    registry.register(BrowserSnapshotTool())
    registry.register(BrowserClickTool())
    registry.register(BrowserFillTool())
    registry.register(BrowserPressTool())
    registry.register(BrowserWaitTool())
    registry.register(BrowserCloseTool())