"""Validate Holix profile names before filesystem use (path-injection guard)."""

from __future__ import annotations

import os
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


def _realpath_under(base: Path, *parts: str) -> Path:
    """Resolve a path and ensure it stays under *base* (CodeQL path guard)."""
    root = os.path.realpath(str(base))
    candidate = os.path.realpath(os.path.join(root, *parts))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise ProfileNameError("Path escapes allowed directory")
    return Path(candidate)


def profile_dir_for_name(profile: str | None, *, default: str = "default") -> Path:
    """Resolved ``~/.helix/profiles/<validated-name>``."""
    from core.profile_keys import profiles_root

    name = validate_profile_name(profile, default=default)
    return _realpath_under(profiles_root(), name)


def resolve_workspace_root(workspace_root: Path) -> Path:
    """Resolve a workspace directory path (rejects obvious traversal in the input)."""
    text = str(workspace_root)
    if "\0" in text:
        raise ProfileNameError("Invalid workspace path")
    normalized = text.replace("\\", "/").strip()
    if normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ProfileNameError("Invalid workspace path")
    expanded = os.path.expanduser(str(workspace_root))
    return Path(os.path.realpath(expanded))


def assert_under_profiles_root(path: Path) -> Path:
    """Ensure *path* stays inside the Holix profiles tree."""
    from core.profile_keys import profiles_root

    resolved = Path(
        os.path.realpath(os.path.expanduser(str(path))),
    )
    root = os.path.realpath(str(profiles_root()))
    if str(resolved) != root and not str(resolved).startswith(root + os.sep):
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


def ensure_profile_workspace_dir(
    profile: str,
    workspace_hint: Path | None = None,
) -> Path:
    """Validate optional workspace path and create the directory under the profile."""
    name = validate_profile_name(profile)
    base = os.path.realpath(str(profile_dir_for_name(name) / "workspace"))
    if workspace_hint is not None:
        trusted_profile_workspace(profile, resolve_workspace_root(workspace_hint))
        target = os.path.realpath(str(resolve_workspace_root(workspace_hint)))
        rel = os.path.relpath(target, base)
        if rel != "." and (rel.startswith("..") or Path(rel).parts[0] == ".."):
            raise ProfileNameError("Workspace path escapes profile workspace")
        final = os.path.realpath(os.path.join(base, rel)) if rel != "." else base
    else:
        final = base
    os.makedirs(final, mode=0o700, exist_ok=True)
    return Path(final)