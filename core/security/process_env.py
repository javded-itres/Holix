"""Environment passed to processes the agent starts.

The gateway process keeps its own keys. A shell, Python worker, or other
child must not receive them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

_SECRET_NAME_MARKERS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PEPPER",
    "CREDENTIAL",
)


def agent_process_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy ``base`` (or the process env) without secret-named variables."""
    source = os.environ if base is None else base
    cleaned: dict[str, str] = {}
    for name, value in source.items():
        upper = name.upper()
        if any(marker in upper for marker in _SECRET_NAME_MARKERS):
            continue
        cleaned[name] = value
    return cleaned
