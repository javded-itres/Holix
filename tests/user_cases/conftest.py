"""Fixtures for user-case journeys."""

from __future__ import annotations

import pytest

from tests.user_cases.harness import UserCaseHarness


@pytest.fixture
async def harness(temp_dir, monkeypatch: pytest.MonkeyPatch):
    """Isolated UserCaseHarness with real tools and scripted LLM."""
    h = UserCaseHarness(temp_dir, monkeypatch)
    await h.setup()
    try:
        yield h
    finally:
        await h.close()
