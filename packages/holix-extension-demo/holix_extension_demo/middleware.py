"""Example LLM middleware — counts model requests when enabled in settings."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RequestStatsMiddleware:
    """Append one JSON line per LLM call under the profile data dir."""

    name = "demo_request_stats"

    def __init__(self, *, path: Path, enabled: bool = True) -> None:
        self._path = path
        self._enabled = enabled

    async def process(self, ctx: Any, call_next: Any) -> Any:
        if not self._enabled:
            return await call_next()

        t0 = time.perf_counter()
        error: str | None = None
        try:
            result = await call_next()
            return result
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            try:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                record = {
                    "model": getattr(ctx, "model", "") or (ctx.kwargs or {}).get("model"),
                    "stream": bool((ctx.kwargs or {}).get("stream")),
                    "duration_ms": round(duration_ms, 2),
                    "message_count": len(getattr(ctx, "messages", None) or []),
                    "error": error,
                    "profile": getattr(ctx, "profile", ""),
                }
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception:
                logger.debug("demo stats write failed", exc_info=True)
