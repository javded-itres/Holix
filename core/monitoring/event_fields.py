"""Shared correlation fields for agent event observability."""

from __future__ import annotations

from typing import Any


def correlation_fields(event: Any) -> dict[str, str]:
    """Extract conversation/run/plan IDs and event type for logs and metrics."""
    et = getattr(event, "type", None)
    event_type = et.value if hasattr(et, "value") else str(et or "")
    extra = {}
    if hasattr(event, "_extra_fields"):
        try:
            extra = event._extra_fields() or {}
        except Exception:
            pass
    if "event_type" in extra:
        event_type = str(extra["event_type"])
    return {
        "event_type": event_type,
        "conversation_id": getattr(event, "conversation_id", "") or "",
        "run_id": getattr(event, "run_id", "") or "",
        "plan_id": getattr(event, "plan_id", "") or "",
    }