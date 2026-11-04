"""Inject the nearest nested AGENTS.md when a file is read.

The workspace-root instruction file stays in the system prompt. A file under
a subdirectory picks up that directory's ``AGENTS.md`` (or ``CLAUDE.md`` /
``rules.md``) once per conversation.
"""

from __future__ import annotations

from pathlib import Path

from core.project.instruction_files import INSTRUCTION_FILE_NAMES, load_instruction_file

_SEEN: dict[str, set[str]] = {}
_MAX_CHARS = 1500


def nearest_nested_instruction(file_path: Path, workspace: Path) -> Path | None:
    """Closest instruction file strictly below *workspace*."""
    try:
        current = file_path.resolve()
        root = workspace.resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent
    while current != root:
        if root not in current.parents and current != root:
            return None
        for name in INSTRUCTION_FILE_NAMES:
            candidate = current / name
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def note_for_read(
    file_path: Path,
    workspace: Path | None,
    *,
    conversation_id: str = "default",
) -> str:
    if workspace is None:
        return ""
    hit = nearest_nested_instruction(file_path, workspace)
    if hit is None:
        return ""
    key = f"{conversation_id}:{hit}"
    seen = _SEEN.setdefault(conversation_id, set())
    if key in seen:
        return ""
    body = load_instruction_file(hit, max_chars=_MAX_CHARS)
    if not body:
        return ""
    seen.add(key)
    try:
        rel = str(hit.resolve().relative_to(workspace.resolve())).replace("\\", "/")
    except ValueError:
        rel = hit.name
    return f"\n\n---\nDirectory instructions `{rel}`:\n{body}"


def reset_seen(conversation_id: str | None = None) -> None:
    if conversation_id is None:
        _SEEN.clear()
    else:
        _SEEN.pop(conversation_id, None)
