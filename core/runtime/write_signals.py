"""Detect write_file loops that do not change disk bytes."""

from __future__ import annotations

import re
from typing import Any

_WRITE_TOOLS = frozenset({"write_file", "patch_file", "apply_patch", "notebook_edit"})
_IMPL_TASK = re.compile(
    r"(?is)\b("
    r"implement|fix|create|write|add|patch|build|"
    r"исправ|сделай|создай|напиш|почин|добав|реализуй"
    r")\b"
)


def no_write_implementation_loop(
    traces: list[dict[str, Any]] | None,
    task: str = "",
    *,
    lookback: int = 8,
    min_calls: int = 6,
) -> bool:
    """True when an implement/fix task only reads/tests and never writes."""
    recent = list(traces or [])[-max(lookback, min_calls) :]
    if len(recent) < min_calls:
        return False
    names = [str(t.get("name") or "").strip().lower() for t in recent]
    if any(n in _WRITE_TOOLS for n in names):
        return False
    from core.runtime.test_run_signals import is_red_test_trace

    failed_tests = any(is_red_test_trace(t) for t in recent)
    impl = bool(_IMPL_TASK.search(task or ""))
    if not failed_tests and not impl:
        return False
    return True


NOOP_WRITE_MARK = "no content changes"

NOOP_WRITE_STOP = (
    "STOP: The file on disk is already exactly this text. "
    "Do NOT call write_file on it again. "
    "If the project files exist, run pytest once (if you have not) "
    "or give the final answer with NO tool calls so the Studio process "
    "can continue. Rewriting the same bytes is not progress."
)


def is_noop_write_result(text: str) -> bool:
    return NOOP_WRITE_MARK in str(text or "").lower()


def is_noop_write_trace(trace: dict[str, Any]) -> bool:
    name = str(trace.get("name") or "").strip().lower()
    if name not in _WRITE_TOOLS:
        return False
    return is_noop_write_result(str(trace.get("result") or ""))


def noop_write_loop(
    traces: list[dict[str, Any]] | None,
    *,
    min_hits: int = 3,
    lookback: int = 8,
) -> bool:
    """True when recent writes only restated files that already matched disk."""
    recent = list(traces or [])[-lookback:]
    writes = [t for t in recent if str(t.get("name") or "").strip().lower() in _WRITE_TOOLS]
    if len(writes) < min_hits:
        return False
    last = writes[-min_hits:]
    return all(is_noop_write_trace(t) for t in last)


def noop_write_count(traces: list[dict[str, Any]] | None) -> int:
    return sum(1 for t in (traces or []) if is_noop_write_trace(t))
