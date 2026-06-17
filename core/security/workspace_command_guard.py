"""Block terminal/background commands that escape the profile workspace."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from core.platform_compat import IS_WINDOWS

_HOLIX_PROFILE_RE = re.compile(
    r"(?:~/?\.holix/profiles/|\.holix/profiles/|(?:^|[\s'\"])(?:/[\w.\-]+)*/profiles/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}/)",
    re.I,
)
_SENSITIVE_HOME_RE = re.compile(
    r"(?:~/?\.(?:holix|helix)(?:/|$)|\$HOME/\.(?:holix|helix)|\$HOLIX_HOME|\$HELIX_HOME)",
    re.I,
)
_PARENT_TRAVERSAL_RE = re.compile(r"(?:^|[\s/\\])\.\.(?:$|[\s/\\])|(?:^|[\s/\\])\.\./")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:~(?:/[\w.\-]+)+)"
    r"|(?:/(?:[\w.\-]+)(?:/[\w.\-]+)*)"
    r"|(?:[A-Za-z]:[/\\](?:[\w.\-]+)(?:[/\\][\w.\-]+)*)"
)
_PATHISH_FLAGS = re.compile(r"(?:^|[\s])(/|\.\./|~/)")
_SKIP_TOKENS = frozenset({"&&", "||", "|", ";", ">", ">>", "<", "2>", "2>>"})


def _normalize(command: str) -> str:
    return (command or "").replace("\\", "/")


def references_holix_profiles(command: str) -> bool:
    text = _normalize(command)
    if _HOLIX_PROFILE_RE.search(text):
        return True
    if _SENSITIVE_HOME_RE.search(text):
        return True
    if ".holix/profiles" in text.lower() or ".helix/profiles" in text.lower():
        return True
    return False


def _resolve_path_token(token: str, *, workspace_root: Path, cwd: Path) -> Path | None:
    raw = (token or "").strip().strip("\"'")
    if not raw or raw in _SKIP_TOKENS:
        return None
    if raw.startswith("-"):
        return None

    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        try:
            return expanded.resolve()
        except OSError:
            return None
    try:
        return (cwd / expanded).resolve()
    except OSError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_tokens(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    tokens: list[str] = []
    try:
        for part in shlex.split(text, posix=not IS_WINDOWS):
            if part not in _SKIP_TOKENS:
                tokens.append(part)
    except ValueError:
        tokens = text.split()
    for match in _ABSOLUTE_PATH_RE.finditer(text):
        tokens.append(match.group(0))
    return tokens


def command_escapes_workspace(command: str, workspace_root: Path | str | None) -> tuple[bool, str]:
    """Return (blocked, reason) when a command targets paths outside the workspace."""
    text = (command or "").strip()
    if not text:
        return True, "Empty command."

    if references_holix_profiles(text):
        return True, "Access to Holix profile directories and secrets is not allowed."

    if _PARENT_TRAVERSAL_RE.search(_normalize(text)):
        return True, "Parent directory traversal (..) is not allowed."

    if workspace_root is None:
        if _PATHISH_FLAGS.search(text) or _ABSOLUTE_PATH_RE.search(text):
            return True, "Absolute paths are not allowed without a workspace jail."
        return False, ""

    root = Path(workspace_root).expanduser().resolve()
    cwd = root

    if _normalize(text).strip() in {"/", "~", "~/.", "~"}:
        return True, "Listing the filesystem root or home directory is not allowed."

    for token in _path_tokens(text):
        resolved = _resolve_path_token(token, workspace_root=root, cwd=cwd)
        if resolved is None:
            continue
        if not _is_relative_to(resolved, root):
            label = token[:80] + ("…" if len(token) > 80 else "")
            return True, f"Path '{label}' is outside your profile workspace."

    return False, ""


def validate_workspace_command(command: str, workspace_root: Path | str | None) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    blocked, reason = command_escapes_workspace(command, workspace_root)
    if blocked:
        return False, reason
    return True, ""