"""Workspace jail helpers for profile-scoped filesystem isolation."""

from __future__ import annotations

from pathlib import Path


class WorkspaceJailError(PermissionError):
    """Raised when a tool path escapes the configured workspace root."""


def get_effective_workspace_root() -> Path | None:
    from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled

    if not is_workspace_jail_enabled():
        return None
    raw = get_workspace_root()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def resolve_tool_path(raw: str, *, default_relative_to: Path | None = None) -> Path:
    """Resolve a tool file path, enforcing workspace jail when enabled."""
    root = get_effective_workspace_root()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        base = default_relative_to or root or Path.cwd()
        p = (base / p).resolve()
    else:
        p = p.resolve()

    if root is not None and not p.is_relative_to(root):
        raise WorkspaceJailError(
            f"Path '{p}' is outside the allowed workspace '{root}'. "
            "Workspace jail is enabled for this profile."
        )
    return p