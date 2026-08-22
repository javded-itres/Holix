"""Identity of a background process by script / npm task, not by OS pid."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from core.platform_compat import IS_WINDOWS

_SCRIPT_EXT = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".bash",
    ".rb",
    ".go",
    ".php",
}
_NPM_RUN = re.compile(
    r"\b(?:npm|pnpm|yarn|bun)(?:\.cmd)?(?:\s+run)?\s+([@\w:./-]+)",
    re.I,
)
_PY_MODULE = re.compile(
    r"\bpython(?:\d+(?:\.\d+)?)?\s+-m\s+([\w.]+)",
    re.I,
)
_ASGI = re.compile(
    r"\b(?:uvicorn|gunicorn|hypercorn|granian)\s+([\w.:]+)",
    re.I,
)
_UV_RUN = re.compile(r"\buv\s+run\s+(?:--\S+\s+)*([\w./-]+)", re.I)


def process_script_key(command: str, *, cwd: str = "") -> str:
    """Stable key so the same script replaces its pin; different scripts coexist."""
    normalized = " ".join((command or "").split())
    identity = _script_identity(normalized) or normalized.lower()
    cwd_key = ""
    raw_cwd = (cwd or "").strip()
    if raw_cwd:
        try:
            cwd_key = str(Path(raw_cwd).expanduser().resolve())
        except OSError:
            cwd_key = raw_cwd
    return f"{cwd_key}::{identity}" if cwd_key else identity


def _script_identity(command: str) -> str:
    if not command:
        return ""
    npm = _NPM_RUN.search(command)
    if npm:
        name = npm.group(1).strip().lower()
        if name not in {"run", "exec", "dlx"}:
            return f"npm:{name}"
    pym = _PY_MODULE.search(command)
    if pym:
        return f"py-m:{pym.group(1).strip().lower()}"
    asgi = _ASGI.search(command)
    if asgi:
        return f"asgi:{asgi.group(1).strip().lower()}"
    uv = _UV_RUN.search(command)
    if uv:
        token = uv.group(1).strip()
        if token:
            return Path(token).name.lower()
    try:
        argv = shlex.split(command, posix=not IS_WINDOWS)
    except ValueError:
        argv = command.split()
    for token in argv:
        if not token or token.startswith("-"):
            continue
        suffix = Path(token).suffix.lower()
        if suffix in _SCRIPT_EXT:
            return Path(token).name.lower()
    for token in argv:
        if not token or token.startswith("-"):
            continue
        name = Path(token).name.lower()
        if name in {"python", "python3", "node", "nodejs", "bash", "sh", "uv", "poetry"}:
            continue
        return name
    return command.lower()
