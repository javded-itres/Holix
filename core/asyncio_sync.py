"""Run async coroutines from synchronous call sites (CLI, sync approval flows)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any


def run_coroutine_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Execute *coro* and return its result.

    Works from plain sync code (``asyncio.run``) and from inside an already
    running event loop (bot handlers, gateway routes) by delegating to a thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()