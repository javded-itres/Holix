"""TUI session workspace is the directory where ``holix tui`` was launched."""

from __future__ import annotations

import os
from pathlib import Path

ENV_LAUNCH_CWD = "HOLIX_TUI_LAUNCH_CWD"


def capture_tui_launch_cwd() -> Path:
    """Remember process CWD so web TUI subprocesses keep the same root."""
    cwd = Path.cwd()
    try:
        cwd = cwd.resolve()
    except OSError:
        pass
    os.environ[ENV_LAUNCH_CWD] = str(cwd)
    return cwd


def tui_session_workspace_root() -> Path:
    """Directory tools should treat as ``.`` for this TUI session."""
    raw = (os.environ.get(ENV_LAUNCH_CWD) or "").strip()
    if raw:
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except OSError:
            pass
        if path.is_dir():
            return path
    cwd = Path.cwd()
    try:
        return cwd.resolve()
    except OSError:
        return cwd
