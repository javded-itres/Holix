"""Workspace jail helpers for profile-scoped filesystem isolation."""

from __future__ import annotations

import dataclasses
import json
import re
from contextlib import contextmanager
from pathlib import Path

_ABSOLUTE_PATH_RE = re.compile(
    r"(?:~(?:/[\w.\-]+)+)"
    r"|(?:/(?:[\w.\-]+)(?:/[\w.\-]+)*)"
    r"|(?:[A-Za-z]:[/\\](?:[\w.\-]+)(?:[/\\][\w.\-]+)*)"
)
_PATH_ARG_KEYS = frozenset(
    {"path", "paths", "db_path", "file_path", "directory", "dir", "cwd", "repo_path"}
)
_RESTRICTED_LABEL = "[restricted]"


class WorkspaceJailError(PermissionError):
    """Raised when a tool path escapes the configured workspace root."""


def get_effective_workspace_root() -> Path | None:
    from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled

    if not is_workspace_jail_enabled():
        return None
    raw = get_workspace_root()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def resolve_full_paths_visible(*, is_admin: bool, workspace_jail_enabled: bool) -> bool:
    """Admins see absolute paths; jailed non-admins see workspace-relative paths only."""
    if is_admin:
        return True
    return not workspace_jail_enabled


def should_redact_paths() -> bool:
    from core.tools.execution_context import is_full_paths_visible, is_workspace_jail_enabled

    return is_workspace_jail_enabled() and not is_full_paths_visible()


def _resolve_path_value(path: Path | str) -> Path | None:
    raw = Path(path).expanduser()
    try:
        return raw.resolve() if raw.is_absolute() else None
    except OSError:
        return None


def display_path_for_user(path: Path | str, *, input_path: str | None = None) -> str:
    """Return a path string safe to show the current user."""
    label = input_path if input_path is not None else str(path)
    if not should_redact_paths():
        resolved = _resolve_path_value(path)
        return str(resolved) if resolved is not None else label

    root = get_effective_workspace_root()
    if root is None:
        return label

    resolved = _resolve_path_value(path)
    if resolved is None:
        raw = Path(label)
        if not raw.is_absolute():
            return label.replace("\\", "/")
        resolved = raw

    try:
        rel = resolved.relative_to(root)
        if rel == Path("."):
            return "."
        return str(rel).replace("\\", "/")
    except ValueError:
        if input_path and not Path(input_path).is_absolute():
            return input_path.replace("\\", "/")
        name = Path(label).name
        return name or _RESTRICTED_LABEL


def _workspace_ancestor_strings(root: Path) -> list[str]:
    parts: list[str] = []
    current = root
    while True:
        parts.append(str(current).replace("\\", "/"))
        if current.parent == current:
            break
        current = current.parent
    return sorted(parts, key=len, reverse=True)


def sanitize_paths_in_text(text: str) -> str:
    """Replace absolute paths in free-form text with workspace-relative paths."""
    if not text or not should_redact_paths():
        return text

    root = get_effective_workspace_root()
    if root is None:
        return text

    ancestors = set(_workspace_ancestor_strings(root)[1:])

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        resolved = _resolve_path_value(token)
        if resolved is not None:
            try:
                resolved.relative_to(root)
                return display_path_for_user(token, input_path=token)
            except ValueError:
                pass
        normalized = token.replace("\\", "/")
        if normalized in ancestors:
            return _RESTRICTED_LABEL
        return display_path_for_user(token, input_path=token)

    return _ABSOLUTE_PATH_RE.sub(_replace, text)


def sanitize_mapping_paths(value: object) -> object:
    """Recursively sanitize path-like fields in structured tool arguments."""
    if not should_redact_paths():
        return value
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            if key in _PATH_ARG_KEYS:
                if isinstance(item, list):
                    out[key] = [
                        display_path_for_user(str(entry), input_path=str(entry))
                        if str(entry).strip()
                        else entry
                        for entry in item
                    ]
                elif isinstance(item, str):
                    out[key] = display_path_for_user(item, input_path=item)
                else:
                    out[key] = sanitize_mapping_paths(item)
            else:
                out[key] = sanitize_mapping_paths(item)
        return out
    if isinstance(value, list):
        return [sanitize_mapping_paths(item) for item in value]
    if isinstance(value, str):
        return sanitize_paths_in_text(value)
    return value


def sanitize_agent_event(event: object) -> object:
    """Sanitize user-visible path fields on agent events."""
    if not should_redact_paths():
        return event

    from core.agent_events import (
        AssistantDeltaEvent,
        ErrorEvent,
        FinalResponseEvent,
        ToolCallErrorEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    if isinstance(event, FinalResponseEvent):
        return dataclasses.replace(event, content=sanitize_paths_in_text(event.content))
    if isinstance(event, AssistantDeltaEvent):
        return dataclasses.replace(
            event,
            content=sanitize_paths_in_text(event.content),
            accumulated=sanitize_paths_in_text(event.accumulated),
        )
    if isinstance(event, ToolCallResultEvent):
        return dataclasses.replace(event, result=sanitize_paths_in_text(event.result))
    if isinstance(event, ToolCallErrorEvent):
        return dataclasses.replace(event, error=sanitize_paths_in_text(event.error))
    if isinstance(event, ErrorEvent):
        return dataclasses.replace(event, error=sanitize_paths_in_text(event.error))
    if isinstance(event, ToolCallStartEvent):
        args = sanitize_mapping_paths(event.arguments)
        raw = event.arguments_raw
        if raw:
            try:
                parsed = json.loads(raw)
                raw = json.dumps(sanitize_mapping_paths(parsed), ensure_ascii=False)
            except json.JSONDecodeError:
                raw = sanitize_paths_in_text(raw)
        return dataclasses.replace(event, arguments=args if isinstance(args, dict) else event.arguments, arguments_raw=raw)
    return event


@contextmanager
def agent_path_visibility_context(*, is_admin: bool, workspace_jail_enabled: bool):
    """Set per-run path visibility for agent/tool output."""
    from core.tools.execution_context import paths_visibility_scope, reset_paths_visibility_scope

    token = paths_visibility_scope(
        full_paths_visible=resolve_full_paths_visible(
            is_admin=is_admin,
            workspace_jail_enabled=workspace_jail_enabled,
        )
    )
    try:
        yield
    finally:
        reset_paths_visibility_scope(token)


def resolve_tool_path(raw: str, *, default_relative_to: Path | None = None) -> Path:
    """Resolve a tool file path, enforcing workspace jail when enabled."""
    root = get_effective_workspace_root()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        base = default_relative_to or root or Path.cwd()
        p = (base / p).resolve()
    else:
        p = p.resolve()

    if root is not None and not p.is_relative_to(root):
        workspace_label = display_path_for_user(root)
        path_label = display_path_for_user(p, input_path=raw)
        raise WorkspaceJailError(
            f"Path '{path_label}' is outside the allowed workspace '{workspace_label}'. "
            "Workspace jail is enabled for this profile."
        )
    return p