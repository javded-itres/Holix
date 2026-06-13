import asyncio
import re
import shlex

from config import settings
from core.platform_compat import IS_WINDOWS, subprocess_shell_kwargs
from core.security.safety import command_whitelist
from core.tools.base import BaseTool
from core.workspace import sanitize_paths_in_text

_PROFILE_PATH_RE = re.compile(
    r"(?:~/?\.holix/profiles/|\.holix/profiles/|/profiles/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}/)"
)


def _blocked_profile_path_access(command: str) -> tuple[bool, str]:
    """Block shell commands that read Holix profile secrets outside workspace jail."""
    from core.crypto.profile_crypto import is_profile_encryption_enabled
    from core.tools.execution_context import get_profile_name

    profile = get_profile_name()
    if not is_profile_encryption_enabled(profile):
        return False, ""

    normalized = command.replace("\\", "/")
    if _PROFILE_PATH_RE.search(normalized):
        return True, "Direct access to Holix profile directories is disabled for encrypted profiles."
    if ".holix/memory-cache" in normalized or "/memory-cache/" in normalized:
        return True, "Direct access to decrypted memory cache is disabled for encrypted profiles."
    if ".holix/profiles" in normalized or "/profiles/" in normalized and ".env" in normalized:
        return True, "Direct access to profile secrets is disabled for encrypted profiles."
    return False, ""


class TerminalTool(BaseTool):
    """Tool for executing terminal commands safely."""

    def __init__(self):
        super().__init__()
        self.name = "run_terminal_command"
        self.description = "Execute a terminal command and return its output. Use for system operations, package installation, git commands, etc."
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The terminal command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30
                }
            },
            "required": ["command"]
        }

    async def execute(self, command: str, timeout: int = 30) -> str:
        """Execute a terminal command with timeout.

        Args:
            command: Command to execute
            timeout: Maximum execution time in seconds

        Returns:
            Command output or error message
        """
        if not settings.enable_terminal_tool:
            return "Error: Terminal tool is disabled (HOLIX_ENABLE_TERMINAL_TOOL=false)"

        if settings.terminal_command_whitelist:
            command_whitelist.apply_extra(settings.terminal_whitelist_extra)
            allowed, reason = command_whitelist.is_command_allowed(command)
            if not allowed:
                return f"Error: Command blocked by safety policy. {reason}"

        blocked, reason = _blocked_profile_path_access(command)
        if blocked:
            return f"Error: Command blocked. {reason}"

        try:
            from core.workspace import get_effective_workspace_root

            cwd: str | None = None
            root = get_effective_workspace_root()
            if root is not None:
                cwd = str(root)

            try:
                argv = shlex.split(command, posix=not IS_WINDOWS)
            except ValueError as exc:
                return f"Error: Invalid command syntax: {exc}"

            if not argv:
                return "Error: Empty command"

            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                **subprocess_shell_kwargs(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                output = stdout.decode('utf-8', errors='replace')
                error = stderr.decode('utf-8', errors='replace')

                output = sanitize_paths_in_text(output)
                error = sanitize_paths_in_text(error)
                if process.returncode == 0:
                    return f"Success (exit code 0):\n{output}" if output else "Success (no output)"
                else:
                    return f"Error (exit code {process.returncode}):\nSTDOUT:\n{output}\nSTDERR:\n{error}"

            except TimeoutError:
                process.kill()
                return f"Error: Command timed out after {timeout} seconds"

        except Exception as e:
            return f"Error executing command: {str(e)}"
