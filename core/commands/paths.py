"""Resolve project- and user-level custom command directories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_utils import get_local_holix_dir
from core.platform_compat import resolve_holix_home
from core.project.workspace_root import resolve_project_root

COMMANDS_DIRNAME = "commands"


def user_commands_dir() -> Path:
    """``$HOLIX_HOME/commands`` (typically ``~/.holix/commands``)."""
    return resolve_holix_home() / COMMANDS_DIRNAME


def project_commands_dir(
    *, cwd: str | Path | None = None, agent: Any = None, host: Any = None
) -> Path:
    """``<workspace>/.holix/commands`` (legacy ``.helix/commands``)."""
    root = resolve_project_root(cwd=cwd, agent=agent, host=host)
    return get_local_holix_dir(root) / COMMANDS_DIRNAME


def command_name_from_rel(rel: str) -> str | None:
    """Map ``test/unit.md`` → ``test:unit``. Returns None if the name is invalid."""
    raw = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not raw.lower().endswith(".md"):
        return None
    stem = raw[: -len(".md")]
    parts = [p for p in stem.split("/") if p]
    if not parts or any(p.startswith(".") or p.startswith("_") for p in parts):
        return None
    if any(p.lower() == "readme" for p in parts):
        return None
    name = ":".join(p.lower() for p in parts)
    if not all(ch.isalnum() or ch in "-_:" for ch in name):
        return None
    if name.startswith(":") or name.endswith(":") or "::" in name:
        return None
    return name
