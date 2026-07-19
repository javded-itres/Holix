"""LLM stream iteration must not raise athrow RuntimeError on timeout/cancel."""

from __future__ import annotations

import asyncio

import pytest
from core.graph.nodes.react_node import _iter_stream_chunks


class _SlowStream:
    """Async iterator that hangs on __anext__ (like a stuck HTTP stream)."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(60)
        return {"choices": [{"delta": {}}]}

    async def aclose(self) -> None:
        return


@pytest.mark.asyncio
async def test_iter_stream_chunks_timeout_does_not_raise_athrow_error() -> None:
    stream = _SlowStream()
    with pytest.raises(TimeoutError):
        async for _ in _iter_stream_chunks(stream, timeout_s=0.05):
            pass


@pytest.mark.asyncio
async def test_iter_stream_chunks_cancel_closes_cleanly() -> None:
    class _EndlessStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(0)
            return {"choices": [{"delta": {"content": "x"}}]}

        async def aclose(self) -> None:
            return

    async def _consume() -> None:
        async for _ in _iter_stream_chunks(_EndlessStream(), timeout_s=5.0):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _consume()