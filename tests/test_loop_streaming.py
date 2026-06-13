"""Tests for streaming error sanitization."""

import json

import pytest

from config import settings


@pytest.mark.asyncio
async def test_streaming_hides_exception_details_by_default(monkeypatch):
    from core.loop_streaming import StreamingAgentLoop

    monkeypatch.setattr(settings, "log_debug_enabled", False)

    class BrokenAgent:
        client = None
        model = "test"

    loop = StreamingAgentLoop(BrokenAgent())

    async def broken_run(*_args, **_kwargs):
        raise RuntimeError("secret traceback path")
        yield  # pragma: no cover

    monkeypatch.setattr("core.loop_streaming.run_holix", broken_run)

    chunks = [chunk async for chunk in loop.run_conversation_stream("hi")]
    assert len(chunks) == 1
    payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert payload["type"] == "error"
    assert payload["message"] == "Internal server error"
    assert "secret" not in payload["message"]


@pytest.mark.asyncio
async def test_streaming_shows_exception_details_in_debug(monkeypatch):
    from core.loop_streaming import StreamingAgentLoop

    monkeypatch.setattr(settings, "log_debug_enabled", True)

    class BrokenAgent:
        client = None
        model = "test"

    loop = StreamingAgentLoop(BrokenAgent())

    async def broken_run(*_args, **_kwargs):
        raise RuntimeError("debug-visible error")
        yield  # pragma: no cover

    monkeypatch.setattr("core.loop_streaming.run_holix", broken_run)

    chunks = [chunk async for chunk in loop.run_conversation_stream("hi")]
    payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert payload["message"] == "debug-visible error"