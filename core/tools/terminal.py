import asyncio

from config import settings
from core.platform_compat import subprocess_shell_kwargs
from core.security.safety import command_whitelist
from core.tools.base import BaseTool


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
            return "Error: Terminal tool is disabled (HELIX_ENABLE_TERMINAL_TOOL=false)"

        if settings.terminal_command_whitelist:
            command_whitelist.apply_extra(settings.terminal_whitelist_extra)
            allowed, reason = command_whitelist.is_command_allowed(command)
            if not allowed:
                return f"Error: Command blocked by safety policy. {reason}"

        try:
            from core.workspace import get_effective_workspace_root

            cwd: str | None = None
            root = get_effective_workspace_root()
            if root is not None:
                cwd = str(root)

            process = await asyncio.create_subprocess_shell(
                command,
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

                if process.returncode == 0:
                    return f"Success (exit code 0):\n{output}" if output else "Success (no output)"
                else:
                    return f"Error (exit code {process.returncode}):\nSTDOUT:\n{output}\nSTDERR:\n{error}"

            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {timeout} seconds"

        except Exception as e:
            return f"Error executing command: {str(e)}"
