"""Resolve cwd and log directory for background project processes."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_background_process_root(working_directory: str = "") -> Path:
    """Pick the directory where a background dev server should run.

    Priority:
    1. Explicit ``working_directory`` from the tool call
    2. Workspace jail root (when jail is enabled)
    3. Profile workspace root from tool execution context
    4. Process current working directory
    """
    if working_directory and str(working_directory).strip():
        return Path(working_directory).expanduser().resolve()

    from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled
    from core.workspace import get_effective_workspace_root

    jail_root = get_effective_workspace_root()
    if jail_root is not None:
        return jail_root

    raw = get_workspace_root()
    if raw and str(raw).strip():
        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    if is_workspace_jail_enabled():
        raise ValueError(
            "Workspace jail is enabled but no workspace root is configured. "
            "Set workspace_root on the profile or pass working_directory."
        )

    return Path.cwd().resolve()


def background_log_dir(project_root: Path) -> Path:
    return project_root / ".holix" / "process-logs"


def build_background_spawn_env(project_root: Path) -> dict[str, str]:
    """Environment for detached dev servers: unbuffered logs + project venv on PATH."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    venv_bin = project_root / ".venv" / "bin"
    if venv_bin.is_dir():
        prefix = str(venv_bin)
        path = env.get("PATH", "")
        if prefix not in path.split(os.pathsep):
            env["PATH"] = f"{prefix}{os.pathsep}{path}" if path else prefix

    pythonpath = env.get("PYTHONPATH", "")
    root = str(project_root)
    if root not in [p for p in pythonpath.split(os.pathsep) if p]:
        env["PYTHONPATH"] = f"{root}{os.pathsep}{pythonpath}" if pythonpath else root

    return env


def resolve_argv_executable(argv: list[str], project_root: Path) -> list[str]:
    """Prefer project ``.venv/bin/<name>`` when the command uses a bare tool name."""
    if not argv:
        return argv
    venv_bin = project_root / ".venv" / "bin"
    if not venv_bin.is_dir():
        return argv

    first = argv[0]
    name = Path(first).name
    if first != name and not first.startswith(".venv/"):
        return argv

    candidate = venv_bin / name
    if candidate.is_file():
        return [str(candidate), *argv[1:]]
    return argv


_SHELL_OPERATORS = ("&&", "||", "|", ";", "\n")
_SHELL_PREFIXES = ("source ", "export ", ". ")


def command_needs_shell(command: str) -> bool:
    """True when the command relies on shell builtins or compound syntax."""
    text = (command or "").strip()
    if not text:
        return False
    if any(op in text for op in _SHELL_OPERATORS):
        return True
    return any(text.startswith(prefix) for prefix in _SHELL_PREFIXES)