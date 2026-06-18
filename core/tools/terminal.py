import asyncio
import shlex

from config import settings
from core.platform_compat import IS_WINDOWS, subprocess_shell_kwargs
from core.security.safety import command_whitelist
from core.security.workspace_command_guard import (
    references_holix_profiles,
    validate_workspace_command,
)
from core.tools.base import BaseTool
from core.workspace import sanitize_paths_in_text


def _blocked_sensitive_path_access(command: str, *, jail_enabled: bool) -> tuple[bool, str]:
    """Block shell commands that reach Holix profile secrets or runtime caches."""
    _ = jail_enabled  # workspace jail uses validate_workspace_command; secrets always blocked
    normalized = command.replace("\\", "/").lower()
    if references_holix_profiles(command):
        return True, "Access to Holix profile directories and secrets is not allowed."
    if (
        ".holix/memory-cache" in normalized
        or "/memory-cache/" in normalized
        or ".runtime-cache" in normalized
        or "/.runtime-cache/" in normalized
    ):
        return True, "Direct access to decrypted memory cache is not allowed."
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

        try:
            from core.tools.execution_context import is_workspace_jail_enabled
            from core.workspace import get_effective_workspace_root

            jail = is_workspace_jail_enabled()
            root = get_effective_workspace_root()

            blocked, reason = _blocked_sensitive_path_access(command, jail_enabled=jail)
            if blocked:
                return f"Error: Command blocked. {reason}"

            allowed, jail_reason = validate_workspace_command(
                command,
                str(root) if root is not None else None,
                jail_enabled=jail,
            )
            if not allowed:
                return f"Error: Command blocked. {jail_reason}"

            if jail and root is None:
                return "Error: Workspace jail is enabled but no workspace root is configured."

            cwd: str | None = str(root) if root is not None else None

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
