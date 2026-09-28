"""web_researcher must stop on ordinary search failures, not treat them as progress."""

from __future__ import annotations

from core.runtime.step_budget import _looks_like_progress
from core.subagents.registry import PREDEFINED_SUBAGENTS


def test_web_researcher_prompt_stops_on_standard_errors() -> None:
    prompt = PREDEFINED_SUBAGENTS["web_researcher"].system_prompt.lower()
    for needle in (
        "stop on standard errors",
        "http 403",
        "no results found",
        "do not search again",
        "not a source",
    ):
        assert needle in prompt


def test_search_failure_is_not_step_progress() -> None:
    assert not _looks_like_progress(
        "No results found for: Claude updates (duckduckgo: DuckDuckGo HTTP 403)"
    )
    assert not _looks_like_progress("web_fetch failed: HTTP 429 rate limit")
    assert _looks_like_progress(
        "Found the release notes at https://example.com/claude with three new API features."
    )
