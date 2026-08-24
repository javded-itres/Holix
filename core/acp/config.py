"""Resolve ACP child command and permission policy."""

from __future__ import annotations

import os
import shlex


def acp_argv(*, command: str | None = None) -> list[str] | None:
    raw = (command or os.environ.get("HOLIX_ACP_COMMAND") or "").strip()
    if not raw:
        return None
    argv = shlex.split(raw)
    extra = (os.environ.get("HOLIX_ACP_ARGS") or "").strip()
    if extra:
        argv.extend(shlex.split(extra))
    return argv or None


def acp_permission_policy() -> str:
    raw = (os.environ.get("HOLIX_ACP_PERMISSION") or "reject").strip().lower()
    if raw in {"allow", "allow_once", "allow-always", "allow_always"}:
        return "allow"
    return "reject"
