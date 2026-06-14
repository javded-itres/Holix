"""Validate Holix profile names before filesystem use (path-injection guard)."""

from __future__ import annotations

import re
from pathlib import Path

PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


class ProfileNameError(ValueError):
    """Raised when a profile name or path segment is unsafe for filesystem use."""


def validate_profile_name(profile: str | None, *, default: str = "default") -> str:
    """Return a safe profile directory segment or raise ProfileNameError."""
    name = (profile or default).strip() or default
    if ".." in name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ProfileNameError(f"Invalid profile name: {profile!r}")
    if not PROFILE_NAME_RE.fullmatch(name):
        raise ProfileNameError(f"Invalid profile name: {profile!r}")
    return name


def profile_dir_for_name(profile: str | None, *, default: str = "default") -> Path:
    """Resolved ``~/.helix/profiles/<validated-name>``."""
    from core.profile_keys import profiles_root

    name = validate_profile_name(profile, default=default)
    return (profiles_root() / name).resolve()


def assert_under_profiles_root(path: Path) -> Path:
    """Ensure *path* stays inside the Holix profiles tree."""
    from core.profile_keys import profiles_root

    resolved = Path(path).expanduser().resolve()
    root = profiles_root().resolve()
    if resolved != root and root not in resolved.parents:
        raise ProfileNameError(f"Path escapes profiles root: {path}")
    return resolved


def trusted_profile_workspace(profile: str, workspace_root: Path) -> Path:
    """Ensure workspace directory belongs to the validated profile."""
    from core.profile_keys import profile_dir

    name = validate_profile_name(profile)
    root = assert_under_profiles_root(workspace_root)
    expected = (profile_dir(name) / "workspace").resolve()
    if root != expected and expected not in root.parents:
        raise ProfileNameError(
            f"Workspace path must be under profile workspace: {expected}"
        )
    return root