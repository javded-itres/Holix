"""Detect terminal loops that only introspect libraries instead of writing code.

``inspect.getsource(DadataClient.suggest)`` then ``.geolocate`` then ``.close``
are not identical signatures, so the generic tool-loop detector misses them.
The agent can burn a full step budget without ever calling write_file.
"""

from __future__ import annotations

import re
from typing import Any

from core.runtime.test_run_signals import extract_command

_INTROSPECT_RE = re.compile(
    r"inspect\.(?:getsource|getmembers|signature|getfile|getsourcelines|"
    r"getmro|getmodule)\b"
    r"|import\s+inspect\b"
    r"|\bdis\.dis\b"
    r"|__code__"
    # Not ``__name__``: ``type(exc).__name__`` is normal error handling.
    r"|__(?:doc|annotations|defaults|kwdefaults|qualname|module|"
    r"dict|mro|globals|func__)__"
    r"|python\d*\s+-c\b[^;\n]*\b(?:dir|vars|help|getattr|hasattr)\s*\(",
    re.I,
)

_TERMINAL = frozenset({"terminal", "run_terminal_command", "code_executor", "execute_python"})
_WRITE = frozenset({"write_file", "patch_file", "apply_patch", "delete_file"})

INTROSPECT_REFUSAL = (
    "Error: Library introspection is blocked "
    "(inspect.getsource, dir(), __code__, __doc__). "
    "That is not implementation and will not be executed.\n"
    "Do not probe installed packages with python -c. "
    "Next tool must persist code: **write_file** or **patch_file** "
    "(or apply_patch). Then run tests."
)

INTROSPECT_WRITE_NUDGE = (
    "[Action honesty — introspection] python -c / inspect.getsource was blocked. "
    "Do NOT repeat library probes and do NOT echo that error as the final answer. "
    "Call write_file or patch_file now with the implementation, then pytest. "
    "A one-line python -c that only prints a value (no inspect/dir/__code__) is fine."
)

_REFUSAL_MARK = "library introspection is blocked"


def is_introspect_command(command: str) -> bool:
    return bool(_INTROSPECT_RE.search(command or ""))


def is_introspect_code(code: str) -> bool:
    """Same gate for execute_python / code_executor snippets."""
    text = code or ""
    if _INTROSPECT_RE.search(text):
        return True
    return bool(re.search(r"\b(?:import|from)\s+inspect\b", text))


def is_introspect_refusal(text: str | None) -> bool:
    return _REFUSAL_MARK in str(text or "").strip().lower()


def is_introspect_trace(trace: dict[str, Any]) -> bool:
    name = str(trace.get("name") or "").strip().lower()
    if name not in _TERMINAL:
        return False
    blob = trace.get("arguments") or trace.get("details") or ""
    if name in {"code_executor", "execute_python"}:
        text = str(blob)
        if text.startswith("{") or text.startswith("["):
            try:
                import json

                obj = json.loads(text)
                if isinstance(obj, dict):
                    text = str(obj.get("code") or obj.get("expression") or text)
            except Exception:
                pass
        return is_introspect_code(text)
    return is_introspect_command(extract_command(blob))


def introspect_loop(
    traces: list[dict[str, Any]] | None,
    *,
    min_hits: int = 3,
    lookback: int = 8,
) -> bool:
    """True when the last terminal calls are all library introspection."""
    recent = list(traces or [])[-lookback:]
    if any(str(t.get("name") or "").strip().lower() in _WRITE for t in recent):
        return False
    terms = [t for t in recent if str(t.get("name") or "").strip().lower() in _TERMINAL]
    if len(terms) < min_hits:
        return False
    last = terms[-min_hits:]
    return all(is_introspect_trace(t) for t in last)
