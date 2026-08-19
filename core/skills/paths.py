"""Confine skill filesystem operations to a trusted root."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_under(root: Path | str, path: Path | str) -> Path:
    """Return the real path if it stays inside *root*; otherwise raise."""
    base = os.path.realpath(os.path.expanduser(str(root)))
    resolved = os.path.realpath(os.path.expanduser(str(path)))
    if resolved != base and not resolved.startswith(base + os.sep):
        raise ValueError(f"path escapes {base}: {path}")
    return Path(resolved)


def join_under(root: Path | str, *parts: str) -> Path:
    base = Path(os.path.expanduser(str(root)))
    return resolve_under(base, base.joinpath(*parts))


def resolve_under_any(path: Path | str, roots: list[Path | str]) -> Path:
    last_error: ValueError | None = None
    for root in roots:
        try:
            return resolve_under(root, path)
        except ValueError as exc:
            last_error = exc
    raise last_error or ValueError(f"path escapes skill roots: {path}")
