import mimetypes
from pathlib import Path

from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.project.holix_md import HOLIX_MD_FILENAME, HOLIX_MD_LEGACY_FILENAME
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.tools.file_diff import format_write_file_result, read_file_text
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path
from core.workspace.quota import WorkspaceQuotaExceeded
from core.workspace.storage import (
    format_quota_error,
    read_profile_file_text,
    write_profile_file_text,
)

_HOLIX_MD_MAX_WRITE_CHARS = 6000
_PATCH_MAX_REPLACEMENTS = 12
# Handbook: keep patches tiny so the model cannot dump a full rewrite.
_PATCH_MAX_NEW_CHARS_HOLIX = 2000
# Code / specs / configs: one coherent edit (function, section) may be larger.
_PATCH_MAX_NEW_CHARS = 12000

_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}
)


def _is_binary_image_path(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return True
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("image/"))


def _find_nested_openspec_file(path: str) -> str | None:
    """If path is missing at workspace root, find it under a project subfolder."""
    norm = (path or "").replace("\\", "/").strip().lstrip("./")
    lower = norm.lower()
    # Strip accidental leading project segments later; look for openspec/... suffix
    idx = lower.find("openspec/")
    if idx < 0:
        return None
    suffix = norm[idx:]  # openspec/...
    try:
        from core.sdd.projects import discover_sdd_projects
        from core.sdd.store import workspace_from_context

        ws = workspace_from_context()
        if (ws / suffix).is_file():
            return None
        hits: list[str] = []
        for proj in discover_sdd_projects(ws):
            prel = (proj.get("path") or "").strip().strip("/")
            candidate = (ws / prel / suffix) if prel else (ws / suffix)
            if candidate.is_file():
                try:
                    hits.append(candidate.relative_to(ws).as_posix())
                except ValueError:
                    hits.append(str(candidate))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return hits[0]  # first match; status will list projects
    except Exception:
        return None
    return None


def _openspec_missing_path_hint(path: str) -> str:
    """Steer agents away from common OpenSpec path mistakes (e.g. flat specs.md)."""
    norm = (path or "").replace("\\", "/").strip().lstrip("./")
    lower = norm.lower()
    if "openspec/" not in lower:
        return ""
    nested = _find_nested_openspec_file(path)
    if nested:
        return (
            f"Found under project path: `{nested}`. "
            "Use that path for read_file, or prefer sdd_status / sdd_write_artifact "
            "with project= (sdd_list_projects). Nested SDD is not at workspace-root "
            "openspec/."
        )
    # Flat specs.md at change root never exists — deltas live under specs/<domain>/spec.md
    if "openspec/changes/" in lower:
        if lower.endswith("specs.md") and not lower.endswith("/specs/spec.md"):
            return (
                "OpenSpec has NO change-root file named specs.md. "
                "Delta specs are at openspec/changes/<id>/specs/<domain>/spec.md "
                "(or <project>/openspec/...). Call sdd_status(change_id=…, project=…) "
                "for real paths; fill with sdd_write_artifact — do not invent paths."
            )
        if lower.endswith("/spec.md") and "/specs/" not in lower:
            return (
                "Delta specs path is openspec/changes/<id>/specs/<domain>/spec.md "
                "(not …/spec.md at change root). Use sdd_status or sdd_write_artifact."
            )
        return (
            "For SDD changes prefer sdd_status / sdd_write_artifact over inventing paths. "
            "If the project is nested (e.g. user_catalog/), paths are "
            "<project>/openspec/changes/<id>/tasks.md — not openspec/... at workspace root. "
            "Layout under the change: proposal.md, design.md, tasks.md, "
            "specs/<domain>/spec.md. Create with sdd_create_change if missing."
        )
    return (
        "For SDD prefer sdd_list_projects / sdd_status / sdd_write_artifact. "
        "Layout: proposal.md, design.md, tasks.md, specs/<domain>/spec.md."
    )


class ReadFileTool(BaseTool):
    """Tool for reading file contents."""

    def __init__(self):
        super().__init__()
        self.name = "read_file"
        self.description = "Read the contents of a file from the filesystem"
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (relative or absolute)"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str) -> str:
        """Read file contents.

        Args:
            path: File path to read

        Returns:
            File contents or error message
        """
        try:
            file_path = resolve_tool_path(path)

            if not file_path.exists():
                hint = _openspec_missing_path_hint(path)
                if hint:
                    return f"Error: File '{path}' does not exist. {hint}"
                return f"Error: File '{path}' does not exist"

            if not file_path.is_file():
                return f"Error: '{path}' is not a file"

            if _is_binary_image_path(file_path):
                display_path = display_path_for_user(file_path, input_path=path)
                return (
                    f"{display_path} is a binary image file; read_file cannot decode it as text. "
                    "If the user attached this image in Telegram, use the vision description "
                    "already included in their message. Do not ask the user to re-upload the image."
                )

            profile = get_profile_name()
            content = read_profile_file_text(file_path, profile=profile)

            display_path = display_path_for_user(file_path, input_path=path)
            return f"Content of {display_path}:\n{content}"

        except WorkspaceJailError as e:
            return f"Error: {e}"
        except ProfileCryptoLockedError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """Tool for writing content to files."""

    def __init__(self):
        super().__init__()
        self.name = "write_file"
        self.description = "Write content to a file, creating it if it doesn't exist"
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str) -> str:
        """Write content to a file.

        Args:
            path: File path to write
            content: Content to write

        Returns:
            Success or error message
        """
        try:
            file_path = resolve_tool_path(path)
            profile = get_profile_name()
            old_text = read_file_text(file_path, profile=profile)

            if (
                file_path.name in (HOLIX_MD_FILENAME, HOLIX_MD_LEGACY_FILENAME)
                and len(content) > _HOLIX_MD_MAX_WRITE_CHARS
            ):
                display_path = display_path_for_user(file_path, input_path=path)
                return (
                    f"Error: {display_path} is too large for write_file "
                    f"({len(content)} chars). Use patch_file with small replacements "
                    "(one section per call, max ~40 lines in each new_string)."
                )

            write_profile_file_text(file_path, content, profile=profile)

            display_path = display_path_for_user(file_path, input_path=path)
            result = format_write_file_result(display_path, old_text, content)
            warn = _sdd_soft_gate_warning(path)
            return f"{warn}\n{result}" if warn else result

        except WorkspaceQuotaExceeded as e:
            return format_quota_error(e)
        except WorkspaceJailError as e:
            return f"Error: {e}"
        except ProfileCryptoLockedError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


def _sdd_soft_gate_warning(writing_path: str) -> str | None:
    try:
        from core.sdd.policy import soft_gate_warning
        from core.sdd.store import workspace_from_context

        return soft_gate_warning(workspace_from_context(), writing_path=writing_path)
    except Exception:
        return None


class PatchFileTool(BaseTool):
    """Apply small, targeted text replacements — safe for large handbook files."""

    def __init__(self):
        super().__init__()
        self.name = "patch_file"
        self.description = (
            "Apply one or more exact string replacements in a text file. "
            "Prefer this over write_file for large docs like HOLIX.md. "
            f"Each new_string max {_PATCH_MAX_NEW_CHARS} chars "
            f"({_PATCH_MAX_NEW_CHARS_HOLIX} for HOLIX.md) — split large edits."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to patch",
                },
                "replacements": {
                    "type": "array",
                    "description": "Ordered list of exact replacements (old_string → new_string)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {
                                "type": "string",
                                "description": "Exact text to find (must be unique in the file)",
                            },
                            "new_string": {
                                "type": "string",
                                "description": "Replacement text",
                            },
                        },
                        "required": ["old_string", "new_string"],
                    },
                    "minItems": 1,
                    "maxItems": _PATCH_MAX_REPLACEMENTS,
                },
            },
            "required": ["path", "replacements"],
        }

    async def execute(self, path: str, replacements: list[dict]) -> str:
        try:
            if not replacements:
                return "Error: replacements must be a non-empty list"
            if len(replacements) > _PATCH_MAX_REPLACEMENTS:
                return f"Error: at most {_PATCH_MAX_REPLACEMENTS} replacements per call"

            file_path = resolve_tool_path(path)
            profile = get_profile_name()
            if not file_path.exists():
                return f"Error: File '{path}' does not exist"
            if not file_path.is_file():
                return f"Error: '{path}' is not a file"

            before_text = read_profile_file_text(file_path, profile=profile)
            content = before_text
            is_holix = file_path.name in (HOLIX_MD_FILENAME, HOLIX_MD_LEGACY_FILENAME)
            max_new = _PATCH_MAX_NEW_CHARS_HOLIX if is_holix else _PATCH_MAX_NEW_CHARS
            applied = 0
            for index, item in enumerate(replacements, start=1):
                old_string = item.get("old_string", "")
                new_string = item.get("new_string", "")
                if not old_string:
                    return f"Error: replacement {index}: old_string is required"
                if len(new_string) > max_new:
                    hint = (
                        "patch one section at a time"
                        if is_holix
                        else "split into smaller replacements or use write_file for a full rewrite"
                    )
                    return (
                        f"Error: replacement {index}: new_string too long "
                        f"({len(new_string)} chars, max {max_new}) — {hint}"
                    )
                count = content.count(old_string)
                if count == 0:
                    return f"Error: replacement {index}: old_string not found in '{path}'"
                if count > 1:
                    return (
                        f"Error: replacement {index}: old_string matches {count} times — "
                        "include more surrounding context to make it unique"
                    )
                content = content.replace(old_string, new_string, 1)
                applied += 1

            write_profile_file_text(file_path, content, profile=profile)
            display_path = display_path_for_user(file_path, input_path=path)
            # Same Studio-facing format as write_file so the UI opens a diff tab.
            return format_write_file_result(display_path, before_text, content)
        except WorkspaceQuotaExceeded as e:
            return format_quota_error(e)
        except WorkspaceJailError as e:
            return f"Error: {e}"
        except ProfileCryptoLockedError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error patching file: {str(e)}"


class ListDirectoryTool(BaseTool):
    """Tool for listing directory contents."""

    def __init__(self):
        super().__init__()
        self.name = "list_directory"
        self.description = "List files and directories in a given path"
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory to list (default: current directory)",
                    "default": "."
                }
            }
        }

    async def execute(self, path: str = ".") -> str:
        """List directory contents.

        Args:
            path: Directory path to list

        Returns:
            Directory listing or error message
        """
        try:
            dir_path = resolve_tool_path(path)

            if not dir_path.exists():
                return f"Error: Directory '{path}' does not exist"

            if not dir_path.is_dir():
                return f"Error: '{path}' is not a directory"

            items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))

            display_path = display_path_for_user(dir_path, input_path=path)
            output_lines = [f"Contents of {display_path}:"]
            for item in items:
                prefix = "[DIR] " if item.is_dir() else "[FILE]"
                output_lines.append(f"{prefix} {item.name}")

            return "\n".join(output_lines)

        except WorkspaceJailError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"