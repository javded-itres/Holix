import mimetypes
from pathlib import Path

from core.crypto.profile_crypto import ProfileCryptoLockedError
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

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"})


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

            write_profile_file_text(file_path, content, profile=profile)

            display_path = display_path_for_user(file_path, input_path=path)
            return format_write_file_result(display_path, old_text, content)

        except WorkspaceQuotaExceeded as e:
            return format_quota_error(e)
        except WorkspaceJailError as e:
            return f"Error: {e}"
        except ProfileCryptoLockedError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


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