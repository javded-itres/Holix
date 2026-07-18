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


def _looks_like_holix_profile_path(path: Path) -> bool:
    """True when a resolved path sits under a Holix/Helix profile tree."""
    norm = str(path).replace("\\", "/").lower()
    if "/.holix/" in norm or "/.helix/" in norm:
        return True
    # HOLIX_HOME/profiles/<name>/... (workspace lives here too)
    return bool(re.search(r"/profiles/[a-z0-9][a-z0-9_.-]{0,63}(?:/|$)", norm))


def references_holix_profiles(
    command: str,
    *,
    allow_under: Path | str | None = None,
) -> bool:
    """True if the command reaches Holix profile dirs outside ``allow_under``.

    Absolute paths under the profile workspace (e.g.
    ``/var/lib/holix/profiles/<name>/workspace/...``) are allowed when
    ``allow_under`` is that workspace root. Secrets and other profiles stay blocked.
    """
    text = _normalize(command)
    # Unexpanded env / home markers — cannot prove they stay inside the workspace.
    if _SENSITIVE_HOME_RE.search(text):
        return True

    has_marker = (
        _HOLIX_PROFILE_RE.search(text) is not None
        or ".holix/profiles" in text.lower()
        or ".helix/profiles" in text.lower()
    )
    if not has_marker:
        return False

    if allow_under is None:
        return True

    root = Path(allow_under).expanduser().resolve()
    holix_paths: list[Path] = []
    for token in _path_tokens(text):
        resolved = _resolve_path_token(token, workspace_root=root, cwd=root)
        if resolved is None:
            continue
        if _looks_like_holix_profile_path(resolved):
            holix_paths.append(resolved)

    if holix_paths:
        return any(not _is_relative_to(path, root) for path in holix_paths)

    # Marker present but no resolvable path tokens — fail closed.
    return True


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
        start = match.start()
        if start > 0 and text[start - 1] not in {" ", "\t", "\"", "'", ">", "|", ";", "&", "(", "\n"}:
            continue
        tokens.append(match.group(0))
    return tokens


def command_escapes_workspace(
    command: str,
    workspace_root: Path | str | None,
    *,
    jail_enabled: bool = True,
) -> tuple[bool, str]:
    """Return (blocked, reason) when a command targets paths outside the workspace."""
    if not jail_enabled:
        return False, ""

    text = (command or "").strip()
    if not text:
        return True, "Empty command."

    if _PARENT_TRAVERSAL_RE.search(_normalize(text)):
        return True, "Parent directory traversal (..) is not allowed."

    if workspace_root is None:
        if references_holix_profiles(text):
            return True, "Access to Holix profile directories and secrets is not allowed."
        if _PATHISH_FLAGS.search(text) or _ABSOLUTE_PATH_RE.search(text):
            return True, "Absolute paths are not allowed without a workspace jail."
        return False, ""

    root = Path(workspace_root).expanduser().resolve()
    cwd = root

    # Block profile secrets / other profiles; allow absolute paths under this workspace
    # even when they contain ``.../profiles/<name>/...``.
    if references_holix_profiles(text, allow_under=root):
        return True, "Access to Holix profile directories and secrets is not allowed."

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


def validate_workspace_command(
    command: str,
    workspace_root: Path | str | None,
    *,
    jail_enabled: bool = True,
) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    blocked, reason = command_escapes_workspace(
        command,
        workspace_root,
        jail_enabled=jail_enabled,
    )
    if blocked:
        return False, reason
    return True, ""