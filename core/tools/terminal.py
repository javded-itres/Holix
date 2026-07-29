import asyncio
import os
import shlex

from config import settings
from core.platform_compat import IS_WINDOWS, subprocess_shell_kwargs
from core.security.safety import command_needs_shell, command_whitelist
from core.security.workspace_command_guard import (
    references_holix_profiles,
    validate_workspace_command,
)
from core.tools.base import BaseTool
from core.workspace import sanitize_paths_in_text


def _env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def terminal_whitelist_enabled() -> bool:
    """Live check — profile ``.env`` is applied after the Settings singleton is built."""
    for key in ("HOLIX_TERMINAL_COMMAND_WHITELIST", "TERMINAL_COMMAND_WHITELIST"):
        if key in os.environ:
            return _env_bool(os.environ.get(key), default=True)
    return bool(settings.terminal_command_whitelist)


def terminal_whitelist_extra() -> str:
    for key in ("HOLIX_TERMINAL_WHITELIST_EXTRA", "TERMINAL_WHITELIST_EXTRA"):
        if key in os.environ and str(os.environ.get(key) or "").strip():
            return str(os.environ.get(key) or "")
    return str(settings.terminal_whitelist_extra or "")


def _blocked_sensitive_path_access(
    command: str,
    *,
    jail_enabled: bool,
    workspace_root: str | None = None,
) -> tuple[bool, str]:
    """Block shell commands that reach Holix profile secrets or runtime caches.

    When jail is on, absolute paths under the profile workspace are allowed even
    though they live under ``.../profiles/<name>/``. Paths outside the workspace
    (config, .env, other profiles) stay blocked.
    """
    normalized = command.replace("\\", "/").lower()
    allow_under = workspace_root if jail_enabled and workspace_root else None
    if references_holix_profiles(command, allow_under=allow_under):
        return True, "Access to Holix profile directories and secrets is not allowed."
    if (
        ".holix/memory-cache" in normalized
        or "/memory-cache/" in normalized
        or ".runtime-cache" in normalized
        or "/.runtime-cache/" in normalized
    ):
        return True, "Direct access to decrypted memory cache is not allowed."
    return False, ""


def _format_process_result(
    *,
    returncode: int,
    output: str,
    error: str,
) -> str:
    if returncode == 0:
        return f"Success (exit code 0):\n{output}" if output else "Success (no output)"
    return f"Error (exit code {returncode}):\nSTDOUT:\n{output}\nSTDERR:\n{error}"


def _spawn_kwargs() -> dict:
    """Kwargs so children can be killed as a process group on POSIX."""
    kwargs = dict(subprocess_shell_kwargs())
    if not IS_WINDOWS:
        # New session → killpg works for shell pipelines.
        kwargs["start_new_session"] = True
    return kwargs


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if not IS_WINDOWS and process.pid:
            try:
                os.killpg(process.pid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                process.kill()
        else:
            process.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except (TimeoutError, ProcessLookupError):
        pass


async def _communicate_with_cancel(
    process: asyncio.subprocess.Process,
    *,
    timeout: float,
) -> tuple[bytes, bytes]:
    """Wait for process output, honouring cooperative cancel and hard timeout."""
    from core.tools.execution_context import is_run_cancelled

    comm = asyncio.create_task(process.communicate())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.1, float(timeout))
    poll = 0.2

    try:
        while not comm.done():
            if is_run_cancelled():
                await _kill_process_tree(process)
                raise asyncio.CancelledError("run cancelled")

            remaining = deadline - loop.time()
            if remaining <= 0:
                await _kill_process_tree(process)
                raise TimeoutError()

            wait_s = min(poll, remaining)
            try:
                return await asyncio.wait_for(asyncio.shield(comm), timeout=wait_s)
            except TimeoutError:
                continue
        return await comm
    finally:
        if not comm.done():
            comm.cancel()
            try:
                await comm
            except (asyncio.CancelledError, Exception):
                pass


class TerminalTool(BaseTool):
    """Tool for executing terminal commands safely."""

    def __init__(self):
        super().__init__()
        self.name = "run_terminal_command"
        self.description = (
            "Execute a terminal command and return its output. "
            "Shell operators (&&, |, >, etc.) are supported. "
            "Use for system operations, package installation, git commands, etc."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The terminal command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, timeout: int = 30) -> str:
        """Execute a terminal command with timeout.

        Simple commands run via exec; compound shell syntax uses a real shell.
        """
        if not settings.enable_terminal_tool:
            return "Error: Terminal tool is disabled (HOLIX_ENABLE_TERMINAL_TOOL=false)"

        from core.tools.execution_context import is_run_cancelled

        if is_run_cancelled():
            return "Error: Run cancelled — terminal command not started."

        if terminal_whitelist_enabled():
            command_whitelist.apply_extra(terminal_whitelist_extra())
            allowed, reason = command_whitelist.is_command_allowed(command)
            if not allowed:
                return f"Error: Command blocked by safety policy. {reason}"

        try:
            from core.tools.execution_context import is_workspace_jail_enabled
            from core.workspace import get_effective_workspace_root

            jail = is_workspace_jail_enabled()
            root = get_effective_workspace_root()
            root_s = str(root) if root is not None else None

            blocked, reason = _blocked_sensitive_path_access(
                command,
                jail_enabled=jail,
                workspace_root=root_s,
            )
            if blocked:
                return f"Error: Command blocked. {reason}"

            allowed, jail_reason = validate_workspace_command(
                command,
                root_s,
                jail_enabled=jail,
            )
            if not allowed:
                return f"Error: Command blocked. {jail_reason}"

            if jail and root is None:
                return (
                    "Error: Workspace jail is enabled but no workspace root is configured."
                )

            cwd: str | None = str(root) if root is not None else None
            use_shell = command_needs_shell(command)
            spawn_kw = _spawn_kwargs()

            if use_shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    **spawn_kw,
                )
            else:
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
                    **spawn_kw,
                )

            try:
                stdout, stderr = await _communicate_with_cancel(
                    process, timeout=float(timeout or 30)
                )

                output = sanitize_paths_in_text(
                    stdout.decode("utf-8", errors="replace")
                )
                error = sanitize_paths_in_text(
                    stderr.decode("utf-8", errors="replace")
                )
                return _format_process_result(
                    returncode=process.returncode or 0,
                    output=output,
                    error=error,
                )

            except TimeoutError:
                await _kill_process_tree(process)
                return f"Error: Command timed out after {timeout} seconds"
            except asyncio.CancelledError:
                await _kill_process_tree(process)
                return "Error: Run cancelled — terminal command terminated."

        except Exception as e:
            return f"Error executing command: {str(e)}"
