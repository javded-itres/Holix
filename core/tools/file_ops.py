import mimetypes
from pathlib import Path

from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.project.holix_md import HOLIX_MD_FILENAME, HOLIX_MD_LEGACY_FILENAME
from core.tools.file_diff import format_write_file_result, read_file_text

_HOLIX_MD_MAX_WRITE_CHARS = 6000
_PATCH_MAX_REPLACEMENTS = 12
_PATCH_MAX_NEW_CHARS = 2000
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path
from core.workspace.quota import WorkspaceQuotaExceeded
from core.workspace.storage import (
    format_quota_error,
    read_profile_file_text,
    write_profile_file_text,
)

_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}
)


def _is_binary_image_path(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return True
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("image/"))


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
            "Prefer this over write_file for large docs like HOLIX.md."
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

            content = read_profile_file_text(file_path, profile=profile)
            applied = 0
            for index, item in enumerate(replacements, start=1):
                old_string = item.get("old_string", "")
                new_string = item.get("new_string", "")
                if not old_string:
                    return f"Error: replacement {index}: old_string is required"
                if len(new_string) > _PATCH_MAX_NEW_CHARS:
                    return (
                        f"Error: replacement {index}: new_string too long "
                        f"(max {_PATCH_MAX_NEW_CHARS} chars) — patch one section at a time"
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
            return f"Patched {display_path}: {applied} replacement(s) applied."
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