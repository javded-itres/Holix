"""Fixtures for live LLM scenarios."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

from tests.live_llm.harness import LiveHarness
from tests.live_llm.provider import (
    live_llm_forced_off,
    live_llm_forced_on,
    probe_provider,
    resolve_live_provider,
)


def pytest_collection_modifyitems(config, items):
    """Always tag live_llm path as live_llm + llm (excluded from default CI)."""
    for item in items:
        if "live_llm/" in item.nodeid or "live_llm\\" in item.nodeid:
            if not item.get_closest_marker("live_llm"):
                item.add_marker(pytest.mark.live_llm)
            if not item.get_closest_marker("llm"):
                item.add_marker(pytest.mark.llm)


@pytest.fixture(scope="session")
def live_provider():
    if live_llm_forced_off():
        pytest.skip("HOLIX_LIVE_LLM is off")

    provider = resolve_live_provider()
    if provider is None:
        pytest.skip(
            "No live LLM config. Set HOLIX_LIVE_MODEL + HOLIX_LIVE_BASE_URL "
            "(and HOLIX_LIVE_API_KEY if needed), or configure holix settings, "
            "then run: ./scripts/test_live_llm.sh"
        )
    return provider


@pytest_asyncio.fixture(scope="session")
async def live_provider_ready(live_provider):
    err = await probe_provider(live_provider, timeout_s=120.0)
    if err:
        if live_llm_forced_on():
            pytest.fail(f"Live LLM forced on but probe failed: {err}")
        pytest.skip(f"Live LLM probe failed ({live_provider.source}): {err}")
    return live_provider


@pytest_asyncio.fixture
async def live_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_provider_ready):
    """Isolated live agent; deletes temp root after the test."""
    root = tmp_path / "live_run"
    root.mkdir(parents=True, exist_ok=True)
    # Prefer not to leak developer extensions / home state
    monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")

    h = LiveHarness(root, live_provider_ready, monkeypatch)
    await h.setup()
    try:
        yield h
    finally:
        # Keep artifacts only if requested for debugging
        keep = (os.environ.get("HOLIX_LIVE_KEEP_ARTIFACTS") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if keep:
            h.snapshot_artifacts("final")
            # close agent but do not wipe root
            if h.agent is not None:
                try:
                    await h.agent.close()
                except Exception:
                    pass
                h.agent = None
        else:
            await h.close()


@pytest_asyncio.fixture
async def live_harness_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_provider_ready
):
    """Live harness with medium auto-allow + scripted ALLOW_ONCE on confirmations."""
    from core.security.confirmation import ConfirmationChoice

    root = tmp_path / "live_confirm"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")
    h = LiveHarness(
        root,
        live_provider_ready,
        monkeypatch,
        auto_allow_threshold="medium",
        confirm_choice=ConfirmationChoice.ALLOW_ONCE,
        max_steps=12,
    )
    await h.setup()
    try:
        yield h
    finally:
        await h.close()


@pytest_asyncio.fixture
async def live_harness_deny(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_provider_ready):
    from core.security.confirmation import ConfirmationChoice

    root = tmp_path / "live_deny"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")
    h = LiveHarness(
        root,
        live_provider_ready,
        monkeypatch,
        auto_allow_threshold="medium",
        confirm_choice=ConfirmationChoice.DENY,
        max_steps=12,
    )
    await h.setup()
    try:
        yield h
    finally:
        await h.close()


@pytest_asyncio.fixture
async def live_harness_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, live_provider_ready
):
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed (uv sync --extra browser)")

    # Ensure chromium binary exists for this environment
    try:
        import subprocess
        import sys

        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False,
            capture_output=True,
            timeout=300,
        )
    except Exception:
        pass

    root = tmp_path / "live_browser"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")
    h = LiveHarness(
        root,
        live_provider_ready,
        monkeypatch,
        enable_browser=True,
        max_steps=16,
        browser_allowed_hosts="example.com",
    )
    await h.setup()
    try:
        yield h
    finally:
        await h.close()
