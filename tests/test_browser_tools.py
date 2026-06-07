"""Browser tools and URL policy tests (mocked Playwright, no real browser)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.browser.policy import parse_allowed_hosts_csv, validate_browser_url
from core.tools.browser.tools import (
    BrowserClickTool,
    BrowserCloseTool,
    BrowserFillTool,
    BrowserOpenTool,
    BrowserSnapshotTool,
    register_browser_tools,
)
from core.tools.execution_context import conversation_scope, reset_conversation_scope
from core.tools.registry import ToolRegistry


class TestBrowserUrlPolicy:
    def test_normalizes_bare_host(self):
        assert validate_browser_url("example.com") == "https://example.com"

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="localhost"):
            validate_browser_url("http://localhost:8080")

    def test_rejects_private_ip(self):
        with pytest.raises(ValueError, match="Private"):
            validate_browser_url("http://192.168.1.1")

    def test_rejects_blocked_scheme(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_browser_url("javascript:alert(1)")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_browser_url("file:///etc/passwd")

    def test_allowlist_enforced(self):
        allowed = parse_allowed_hosts_csv("example.com, .trusted.org")
        assert validate_browser_url("https://api.example.com", allowed) == "https://api.example.com"
        with pytest.raises(ValueError, match="browser_allowed_hosts"):
            validate_browser_url("https://evil.com", allowed)

    def test_empty_allowlist_allows_public_host(self):
        assert validate_browser_url("https://example.com", frozenset()) == "https://example.com"


def _mock_session(*, url: str = "https://example.com/", refs: dict | None = None):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.screenshot = AsyncMock()
    page.title = AsyncMock(return_value="Test")
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.first.fill = AsyncMock()

    session = SimpleNamespace(page=page, refs=refs or {})
    return session


@pytest.mark.asyncio
async def test_browser_open_validates_and_navigates():
    tool = BrowserOpenTool()
    session = _mock_session()

    token = conversation_scope("conv-1")
    try:
        with (
            patch(
                "core.tools.browser.tools.validate_browser_url",
                return_value="https://example.com",
            ),
            patch("core.tools.browser.tools.get_browser_session_manager") as mgr,
        ):
            mgr.return_value.get_or_create = AsyncMock(return_value=session)
            result = await tool.execute(url="example.com")
    finally:
        reset_conversation_scope(token)

    assert "Opened" in result
    session.page.goto.assert_awaited_once_with(
        "https://example.com", wait_until="domcontentloaded", timeout=60_000
    )
    assert session.refs == {}


@pytest.mark.asyncio
async def test_browser_snapshot_builds_refs():
    tool = BrowserSnapshotTool()
    session = _mock_session()
    snapshot_text = "URL: https://example.com\nTitle: T\n[e1] button \"OK\""
    refs = {"e1": '[data-helix-ref="e1"]'}

    token = conversation_scope("c1")
    try:
        with (
            patch(
                "core.tools.browser.tools.build_page_snapshot",
                new_callable=AsyncMock,
                return_value=(snapshot_text, refs),
            ),
            patch("core.tools.browser.tools.get_browser_session_manager") as mgr,
        ):
            mgr.return_value.get_or_create = AsyncMock(return_value=session)
            result = await tool.execute()
    finally:
        reset_conversation_scope(token)

    assert snapshot_text in result
    assert session.refs == refs


@pytest.mark.asyncio
async def test_browser_click_by_ref():
    tool = BrowserClickTool()
    session = _mock_session(refs={"e2": '[data-helix-ref="e2"]'})

    token = conversation_scope("c1")
    try:
        with patch("core.tools.browser.tools.get_browser_session_manager") as mgr:
            mgr.return_value.get_or_create = AsyncMock(return_value=session)
            result = await tool.execute(ref="e2")
    finally:
        reset_conversation_scope(token)

    assert "Clicked e2" in result
    session.page.locator.assert_called_with('[data-helix-ref="e2"]')


@pytest.mark.asyncio
async def test_browser_click_unknown_ref():
    tool = BrowserClickTool()
    session = _mock_session(refs={})

    token = conversation_scope("c1")
    try:
        with patch("core.tools.browser.tools.get_browser_session_manager") as mgr:
            mgr.return_value.get_or_create = AsyncMock(return_value=session)
            result = await tool.execute(ref="e99")
    finally:
        reset_conversation_scope(token)

    assert "browser_click error" in result
    assert "Unknown ref" in result


@pytest.mark.asyncio
async def test_browser_fill():
    tool = BrowserFillTool()
    session = _mock_session(refs={"e1": '[data-helix-ref="e1"]'})

    token = conversation_scope("c1")
    try:
        with patch("core.tools.browser.tools.get_browser_session_manager") as mgr:
            mgr.return_value.get_or_create = AsyncMock(return_value=session)
            result = await tool.execute(text="hello", ref="e1")
    finally:
        reset_conversation_scope(token)

    assert "Filled e1" in result


@pytest.mark.asyncio
async def test_browser_close():
    tool = BrowserCloseTool()

    token = conversation_scope("c1")
    try:
        with patch("core.tools.browser.tools.get_browser_session_manager") as mgr:
            mgr.return_value.close = AsyncMock(return_value=True)
            result = await tool.execute()
    finally:
        reset_conversation_scope(token)

    assert result == "Browser closed."
    mgr.return_value.close.assert_awaited_once_with("c1")


def test_register_browser_tools_adds_seven_tools():
    registry = ToolRegistry()
    register_browser_tools(registry)
    names = set(registry.get_tool_names())
    assert names == {
        "browser_open",
        "browser_snapshot",
        "browser_click",
        "browser_fill",
        "browser_press",
        "browser_wait",
        "browser_close",
    }


def test_registry_skips_browser_when_disabled(monkeypatch):
    monkeypatch.setattr("config.settings.enable_browser_tools", False)
    registry = ToolRegistry()
    registry.register_all()
    assert not any(n.startswith("browser_") for n in registry.get_tool_names())


def test_registry_includes_browser_when_enabled(monkeypatch):
    monkeypatch.setattr("config.settings.enable_browser_tools", True)
    registry = ToolRegistry()
    registry.register_all()
    assert "browser_open" in registry.get_tool_names()


def test_browser_mutating_tools_are_high_risk():
    assert BrowserOpenTool().risk_level == "high"
    assert BrowserClickTool().risk_level == "high"
    assert BrowserFillTool().risk_level == "high"
    assert BrowserSnapshotTool().risk_level == "low"