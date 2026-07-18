"""Detect installed external CLI binaries on PATH / known paths."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from core.external_cli.registry import ExternalCliSpec, list_cli_specs


def install_path_dirs() -> str:
    """PATH-like string including known install locations for external CLIs."""
    home = Path.home()
    dirs: list[str] = []
    for spec in list_cli_specs():
        for raw in spec.binary_paths:
            parent = str(Path(raw).expanduser().parent)
            if parent not in dirs:
                dirs.append(parent)
    for sub in (".local/bin", ".opencode/bin", ".grok/bin"):
        candidate = str(home / sub)
        if candidate not in dirs:
            dirs.append(candidate)
    current = os.environ.get("PATH", "")
    return os.pathsep.join([*dirs, current]) if dirs else current


def binary_installed(spec: ExternalCliSpec) -> str | None:
    """Return absolute path of the first matching binary, or None."""
    search_path = install_path_dirs()
    for name in spec.binary_names:
        path = shutil.which(name, path=search_path)
        if path:
            return path
    for raw in spec.binary_paths:
        candidate = Path(raw).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
