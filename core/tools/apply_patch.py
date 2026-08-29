"""Codex-style multi-file apply_patch tool (no shell-out to an apply_patch binary)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.tools.file_diff import unified_diff_text
from core.tools.result import tool_err, tool_ok
from core.workspace import WorkspaceJailError, resolve_tool_path
from core.workspace.quota import WorkspaceQuotaExceeded
from core.workspace.storage import (
    format_quota_error,
    read_profile_file_text,
    write_profile_file_text,
)

BEGIN_MARK = "*** Begin Patch"
END_MARK = "*** End Patch"
ADD_PREFIX = "*** Add File:"
UPDATE_PREFIX = "*** Update File:"
DELETE_PREFIX = "*** Delete File:"
END_FILE_PREFIX = "*** End of File"

_HEREDOC_RE = re.compile(
    r"""^\s*(?:[A-Za-z_][\w]*=[^\s]*\s+)*"""
    r"""(?:python(?:3)?\s+-m\s+)?apply[_-]?patch\b"""
    r"""[^<\n]*<<\s*['\"]?(\w+)['\"]?\s*\n"""
    r"""(.*)\n\1\s*$""",
    re.DOTALL | re.IGNORECASE,
)


class HunkMismatch(Exception):
    def __init__(self, path: str, hunk_index: int, preview: str) -> None:
        self.path = path
        self.hunk_index = hunk_index
        self.preview = preview
        super().__init__(f"hunk {hunk_index} did not unique-match in {path}")


@dataclass
class FileOp:
    action: str  # add | update | delete
    path: str
    hunks: list[list[str]] = field(default_factory=list)
    add_body: str = ""


def extract_apply_patch_document(command: str) -> str | None:
    """If a shell command is ``apply_patch <<EOF … EOF``, return the patch body."""
    raw = str(command or "").replace("\r\n", "\n").strip()
    if not raw:
        return None
    match = _HEREDOC_RE.match(raw)
    if match is None:
        return None
    body = match.group(2).strip("\n")
    if BEGIN_MARK not in body:
        return None
    return body


def parse_apply_patch(document: str) -> list[FileOp]:
    text = str(document or "").replace("\r\n", "\n")
    if BEGIN_MARK not in text or END_MARK not in text:
        raise ValueError("patch must start with '*** Begin Patch' and end with '*** End Patch'")
    start = text.find(BEGIN_MARK)
    end = text.rfind(END_MARK)
    if end <= start:
        raise ValueError("invalid Begin/End Patch markers")
    body = text[start + len(BEGIN_MARK) : end]
    lines = body.split("\n")
    ops: list[FileOp] = []
    current: FileOp | None = None
    hunk: list[str] | None = None

    def flush_hunk() -> None:
        nonlocal hunk
        if current is not None and hunk is not None:
            current.hunks.append(hunk)
        hunk = None

    def flush_op() -> None:
        nonlocal current
        flush_hunk()
        if current is not None:
            ops.append(current)
        current = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.startswith(ADD_PREFIX):
            flush_op()
            current = FileOp(action="add", path=line[len(ADD_PREFIX) :].strip())
            continue
        if line.startswith(UPDATE_PREFIX):
            flush_op()
            current = FileOp(action="update", path=line[len(UPDATE_PREFIX) :].strip())
            continue
        if line.startswith(DELETE_PREFIX):
            flush_op()
            current = FileOp(action="delete", path=line[len(DELETE_PREFIX) :].strip())
            continue
        if line.startswith(END_FILE_PREFIX) or line.strip() in {BEGIN_MARK, END_MARK}:
            flush_hunk()
            continue
        if current is None:
            if not line.strip():
                continue
            raise ValueError(f"patch content before a file op: {line[:80]!r}")
        if current.action == "add":
            if line.startswith("+"):
                current.add_body += line[1:] + "\n"
            elif not line.strip() or line.startswith("***"):
                continue
            else:
                current.add_body += line + "\n"
            continue
        if current.action == "delete":
            continue
        if line.startswith("@@"):
            flush_hunk()
            hunk = []
            continue
        if hunk is None:
            hunk = []
        hunk.append(line)

    flush_op()
    if not ops:
        raise ValueError("patch contains no file operations")
    for op in ops:
        if not op.path:
            raise ValueError(f"{op.action} file op is missing a path")
    return ops


def _hunk_old_new(hunk_lines: list[str]) -> tuple[str, str]:
    old_parts: list[str] = []
    new_parts: list[str] = []
    for line in hunk_lines:
        if not line:
            old_parts.append("")
            new_parts.append("")
            continue
        prefix, rest = line[0], line[1:]
        if prefix == " ":
            old_parts.append(rest)
            new_parts.append(rest)
        elif prefix == "-":
            old_parts.append(rest)
        elif prefix == "+":
            new_parts.append(rest)
        elif prefix == "\\":
            continue
        else:
            old_parts.append(line)
            new_parts.append(line)
    old = "\n".join(old_parts)
    new = "\n".join(new_parts)
    return old, new


def apply_hunk(content: str, hunk_lines: list[str], *, path: str, hunk_index: int) -> str:
    old, new = _hunk_old_new(hunk_lines)
    if old == "":
        raise HunkMismatch(path, hunk_index, preview="(empty old side)")
    matches: list[int] = []
    start = 0
    while True:
        found = content.find(old, start)
        if found < 0:
            break
        matches.append(found)
        start = found + 1
        if len(matches) > 2:
            break
    if len(matches) != 1:
        preview = old[:240].replace("\n", "\\n")
        raise HunkMismatch(path, hunk_index, preview=preview)
    i = matches[0]
    return content[:i] + new + content[i + len(old) :]


def _normalize_nl(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


class ApplyPatchTool(BaseTool):
    """Apply a Codex-style multi-file patch atomically."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "apply_patch"
        self.description = (
            "Apply a Codex-style multi-file patch. Prefer this over write_file for "
            "existing files when the model family is GPT/Codex. For Claude/Qwen "
            "prefer patch_file (old_string/new_string). Fail the entire call if any "
            "hunk does not match exactly. Never wrap the patch document in JSON."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["patch"],
            "properties": {
                "patch": {
                    "type": "string",
                    "description": (
                        "Full patch. Starts with '*** Begin Patch', ends with "
                        "'*** End Patch'. File ops: '*** Add File: path', "
                        "'*** Update File: path', '*** Delete File: path'. "
                        "Update hunks use @@ and lines prefixed with space "
                        "(context), '-' (remove), '+' (add)."
                    ),
                },
                "dry_run": {"type": "boolean"},
            },
        }

    async def execute(self, patch: str, dry_run: bool = False, **_: Any) -> str:
        try:
            ops = parse_apply_patch(patch)
        except ValueError as exc:
            return tool_err("invalid_patch", str(exc))

        profile = get_profile_name()
        planned: list[dict[str, Any]] = []
        diffs: list[str] = []

        try:
            for op in ops:
                file_path = resolve_tool_path(op.path)
                display = op.path.replace("\\", "/")
                if op.action == "add":
                    if file_path.exists():
                        return tool_err(
                            "exists",
                            f"Add File: '{display}' already exists",
                            path=display,
                        )
                    new_text = op.add_body
                    planned.append(
                        {
                            "path": display,
                            "abs": file_path,
                            "action": "add",
                            "hunks": 0,
                            "old": None,
                            "new": new_text,
                        }
                    )
                    diffs.append(unified_diff_text(display, "", new_text))
                elif op.action == "delete":
                    if not file_path.exists() or not file_path.is_file():
                        return tool_err(
                            "not_found",
                            f"Delete File: '{display}' is missing",
                            path=display,
                        )
                    old_text = _normalize_nl(read_profile_file_text(file_path, profile=profile))
                    planned.append(
                        {
                            "path": display,
                            "abs": file_path,
                            "action": "delete",
                            "hunks": 0,
                            "old": old_text,
                            "new": None,
                        }
                    )
                    diffs.append(unified_diff_text(display, old_text, ""))
                else:
                    if not file_path.exists() or not file_path.is_file():
                        return tool_err(
                            "not_found",
                            f"Update File: '{display}' is missing",
                            path=display,
                        )
                    content = _normalize_nl(read_profile_file_text(file_path, profile=profile))
                    hunks = op.hunks or []
                    if not hunks:
                        return tool_err(
                            "invalid_patch",
                            f"Update File '{display}' has no hunks",
                            path=display,
                        )
                    updated = content
                    for index, hunk in enumerate(hunks):
                        try:
                            updated = apply_hunk(updated, hunk, path=display, hunk_index=index)
                        except HunkMismatch as exc:
                            return tool_err(
                                "hunk_mismatch",
                                str(exc),
                                path=exc.path,
                                hunk_index=exc.hunk_index,
                                preview=exc.preview,
                            )
                    planned.append(
                        {
                            "path": display,
                            "abs": file_path,
                            "action": "update",
                            "hunks": len(hunks),
                            "old": content,
                            "new": updated,
                        }
                    )
                    diffs.append(unified_diff_text(display, content, updated))
        except WorkspaceJailError as exc:
            return tool_err("jail", str(exc))
        except ProfileCryptoLockedError as exc:
            return tool_err("crypto_locked", str(exc))
        except Exception as exc:
            return tool_err("error", f"apply_patch failed: {exc}")

        files_out = [
            {"path": item["path"], "action": item["action"], "hunks": item["hunks"]}
            for item in planned
        ]
        diff_text = "\n".join(part for part in diffs if part)

        if dry_run:
            return tool_ok(files=files_out, diff=diff_text, dry_run=True)

        snapshots: list[tuple[Path, str | None, bool]] = []
        try:
            for item in planned:
                path: Path = item["abs"]
                action = item["action"]
                if action == "delete":
                    snapshots.append((path, item["old"], True))
                    path.unlink()
                elif action == "add":
                    snapshots.append((path, None, False))
                    write_profile_file_text(path, item["new"] or "", profile=profile)
                else:
                    snapshots.append((path, item["old"], True))
                    write_profile_file_text(path, item["new"] or "", profile=profile)
        except WorkspaceQuotaExceeded as exc:
            _rollback(snapshots, profile)
            return format_quota_error(exc)
        except WorkspaceJailError as exc:
            _rollback(snapshots, profile)
            return tool_err("jail", str(exc))
        except Exception as exc:
            _rollback(snapshots, profile)
            return tool_err("error", f"apply_patch write failed: {exc}")

        return tool_ok(files=files_out, diff=diff_text)


def _rollback(snapshots: list[tuple[Path, str | None, bool]], profile: str) -> None:
    for path, old, existed in reversed(snapshots):
        try:
            if old is None:
                if path.exists() and path.is_file():
                    path.unlink()
            elif existed:
                write_profile_file_text(path, old, profile=profile)
        except Exception:
            continue
