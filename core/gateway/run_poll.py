"""Hermes-compatible helpers for polling /v1/runs status."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from core.gateway.runs_store import RunStatus

# Hermes terminal states; "done" is accepted as a legacy alias for "completed".
TERMINAL_RUN_STATUSES = frozenset({
    RunStatus.COMPLETED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
    "done",
})


def is_terminal_run_status(status: str | RunStatus | None) -> bool:
    """Return True when a run has reached a terminal poll state."""
    if status is None:
        return False
    if isinstance(status, RunStatus):
        return status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    return status.strip().lower() in TERMINAL_RUN_STATUSES


def normalize_run_status(status: str | RunStatus | None) -> str | None:
    """Normalize legacy aliases for external Hermes clients."""
    if status is None:
        return None
    value = status.value if isinstance(status, RunStatus) else str(status).strip().lower()
    if value == "done":
        return RunStatus.COMPLETED.value
    return value


def poll_run(
    fetch: Callable[[str], dict[str, Any]],
    run_id: str,
    *,
    timeout: float = 120.0,
    interval: float = 0.1,
) -> dict[str, Any]:
    """Poll run status until terminal (completed/failed/cancelled/done)."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = fetch(run_id)
        status = normalize_run_status(last.get("status"))
        if status is not None:
            last = {**last, "status": status}
        if is_terminal_run_status(status):
            return last
        time.sleep(interval)
    last_status = last.get("status", "unknown")
    raise TimeoutError(
        f"Run {run_id} did not reach a terminal status within {timeout}s "
        f"(last status: {last_status!r})"
    )