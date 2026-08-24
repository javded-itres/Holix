"""Refuse to walk $HOME / OS roots; skip macOS poison directories.

Telegram LaunchAgents often have process CWD ``$HOME``. A recursive
``Path.rglob`` / ``os.scandir`` of the home directory (especially
``~/Library`` and iCloud) blocks the event loop and the bot looks hung.
"""

from __future__ import annotations

from pathlib import Path

SKIP_SEARCH_DIR_NAMES = frozenset(
    {
        ".git",
        ".holix",
        ".helix",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        ".turbo",
        # macOS home / volume poison — scandir here blocks the Telegram loop
        "Library",
        "Applications",
        "System",
        "Volumes",
        "Network",
        "Movies",
        "Pictures",
        "Music",
        "CloudStorage",
        "iCloud Drive",
        "Mobile Documents",
        "Google Drive",
        "Dropbox",
        "OneDrive",
        ".Trash",
        "Trash",
    }
)

_FS_ROOTS = frozenset(
    {
        "/",
        "/Users",
        "/home",
        "/private",
        "/System",
        "/Volumes",
        "/Network",
        "/Applications",
        "/opt",
        "/usr",
        "/root",
    }
)


def is_unsafe_project_scan_root(path: Path | str | None) -> bool:
    """True for ``$HOME``, ``/``, ``/Users``, and similar roots.

    Do **not** treat path *components* like ``System`` / ``Volumes`` as
    unsafe: on macOS ``/Users/...`` may resolve through
    ``/System/Volumes/Data/Users/...``.
    """
    if path is None:
        return False
    text = str(path).strip()
    if not text:
        return False
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        return True
    posix = resolved.as_posix()
    if posix in _FS_ROOTS or resolved.parent == resolved:
        return True
    try:
        home = Path.home().resolve()
    except OSError:
        return False
    return resolved == home
