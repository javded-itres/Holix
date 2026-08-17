"""Detect passing automated tests so we don't treat re-runs as progress."""

from __future__ import annotations

import json
import re
from typing import Any

_TEST_CMD_RE = re.compile(
    r"\b("
    r"pytest|py\.test|python\d*\s+-m\s+pytest|unittest|"
    r"npm\s+test|npx\s+vitest|vitest|"
    r"cargo\s+test|go\s+test|"
    r"dotnet\s+test"
    r")\b",
    re.I,
)
_PASSED_RE = re.compile(r"(\d+)\s+passed\b", re.I)
_FAILED_RE = re.compile(r"([1-9]\d*)\s+failed\b", re.I)
_ERROR_RE = re.compile(r"([1-9]\d*)\s+error", re.I)


def extract_command(details: Any) -> str:
    text = str(details or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("command"):
                return str(obj.get("command") or "")
        except Exception:
            pass
    return text


def is_test_command(command: str) -> bool:
    return bool(_TEST_CMD_RE.search(command or ""))


def is_green_test_output(text: str) -> bool:
    blob = str(text or "")
    low = blob.lower()
    if "timed out" in low or "timeout" in low and "passed" not in low:
        return False
    if _FAILED_RE.search(blob) or _ERROR_RE.search(blob):
        return False
    if "traceback" in low and "passed" not in low:
        return False
    hit = _PASSED_RE.search(blob)
    if hit:
        return int(hit.group(1)) > 0
    if "ran " in low and re.search(r"\bok\b", low) and "fail" not in low:
        return True
    return False


def is_green_test_trace(trace: dict[str, Any]) -> bool:
    name = str(trace.get("name") or "").lower()
    args = extract_command(trace.get("arguments") or "")
    result = str(trace.get("result") or "")
    if name not in {"terminal", "run_terminal_command"}:
        return False
    if not is_test_command(args):
        return False
    return is_green_test_output(result)


def green_test_passes(traces: list[dict[str, Any]]) -> int:
    return sum(1 for t in traces if is_green_test_trace(t))


def tests_already_green_loop(traces: list[dict[str, Any]]) -> bool:
    """True when the agent re-runs or re-lists tests after they already passed."""
    greens = green_test_passes(traces)
    if greens >= 2:
        return True
    if greens < 1:
        return False
    last = traces[-1] if traces else {}
    name = str(last.get("name") or "").lower()
    args = extract_command(last.get("arguments") or last.get("details") or "")
    if name in {"grep", "glob"} and re.search(r"\btest", args, re.I):
        return True
    if name in {"terminal", "run_terminal_command"} and is_test_command(args):
        return greens >= 1 and is_green_test_output(str(last.get("result") or ""))
    return False
