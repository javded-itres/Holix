"""Run one non-interactive command on another machine over SSH."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from core.memory.tool_content import truncate_terminal_output
from core.security.safety import command_whitelist
from core.tools.base import BaseTool
from core.tools.terminal import (
    _communicate_with_cancel,
    _format_process_result,
    _spawn_kwargs,
)
from core.workspace import sanitize_paths_in_text

_DEFAULT_TIMEOUT_S = 120
_MAX_TIMEOUT_S = 600
_MAX_STDIN_CHARS = 512_000
_CONNECT_TIMEOUT_S = "8"


def validate_ssh_host(host: str) -> str | None:
    """Return an error message when *host* is not a single SSH destination."""
    text = (host or "").strip()
    if not text:
        return "Error: host is empty. Pass an SSH config alias or user@host."
    if any(ch.isspace() for ch in text) or any(ch in text for ch in "|&;<>$`'\"\\"):
        return (
            "Error: host must be one destination (an SSH config alias or user@host), "
            "not a shell command."
        )
    if text.startswith("-"):
        return "Error: host must not look like an SSH option."
    user, _, destination = text.rpartition("@")
    if not destination or (user == "" and "@" in text):
        return "Error: host is missing the destination after @."
    if user and (not _token_ok(user) or "@" in user):
        return "Error: SSH user contains unsupported characters."
    bare = destination
    if destination.startswith("[") and "]" in destination:
        bare = destination[1 : destination.index("]")]
        rest = destination[destination.index("]") + 1 :]
        if rest and not _port_suffix(rest):
            return "Error: host port is invalid."
        if not bare or any(ch not in "0123456789abcdefABCDEF:" for ch in bare):
            return "Error: host is not a single destination."
        return None
    if ":" in destination:
        bare, _, port = destination.rpartition(":")
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            return "Error: host port is invalid."
    if not bare or not _token_ok(bare):
        return "Error: host is not a single destination."
    return None


def _token_ok(value: str) -> bool:
    return bool(value) and all(ch.isalnum() or ch in "._-" for ch in value)


def _port_suffix(rest: str) -> bool:
    if not rest.startswith(":"):
        return False
    port = rest[1:]
    return port.isdigit() and 1 <= int(port) <= 65535


def build_ssh_argv(host: str, command: str) -> list[str]:
    """Local argv. The remote command is one argument, not a local shell string."""
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={_CONNECT_TIMEOUT_S}",
        "-o",
        "RequestTTY=no",
        "--",
        host,
        command,
    ]


def clamp_ssh_timeout(timeout: int | float | None) -> float:
    try:
        value = int(timeout if timeout is not None else _DEFAULT_TIMEOUT_S)
    except (TypeError, ValueError):
        value = _DEFAULT_TIMEOUT_S
    return float(min(_MAX_TIMEOUT_S, max(1, value)))


def parse_ssh_config_hosts(text: str) -> tuple[list[tuple[str, str]], str]:
    """Return ``([(alias, user)], default_user)`` from an SSH config.

    ``Host *`` supplies the default user. Wildcard aliases are omitted.
    """
    aliases: list[tuple[str, str]] = []
    default_user = ""
    current: list[str] = []
    user = ""
    in_block = False

    def flush() -> None:
        nonlocal current, user, default_user
        for alias in current:
            if alias == "*":
                if user and not default_user:
                    default_user = user
                continue
            if any(ch in alias for ch in "*?!"):
                continue
            aliases.append((alias, user))
        current = []
        user = ""

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        key = parts[0].lower()
        if key == "host":
            if in_block:
                flush()
            current = parts[1:]
            user = ""
            in_block = True
        elif key == "user" and in_block and len(parts) >= 2:
            user = parts[1]
    if in_block:
        flush()
    return aliases, default_user


def format_ssh_target_hint(config_path: Path | None = None) -> str:
    """One line of SSH aliases for the system prompt. Empty when there is no config."""
    path = config_path or (Path.home() / ".ssh" / "config")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    aliases, default_user = parse_ssh_config_hosts(text)
    if not aliases and not default_user:
        return ""
    shown = aliases[:30]
    bits = []
    for alias, user in shown:
        bits.append(f"{alias} (user {user})" if user else alias)
    line = "SSH config aliases: " + ", ".join(bits) + "."
    if len(aliases) > len(shown):
        line += f" {len(aliases) - len(shown)} more aliases are in the SSH config."
    if default_user:
        line += f" When an alias sets no user, the config default user is {default_user}."
    line += " Pass that alias as host. For an IP with no alias, pass user@ip."
    return line


def format_ssh_exec_block(config_path: Path | None = None) -> str:
    """Short always-on instructions. The skill holix-ssh has the procedure."""
    lines = [
        "## Remote commands",
        "Run a command on another machine with `ssh_exec`. "
        "`host` and `command` are separate arguments.",
        "Do not use `run_terminal_command` for `ssh`, `scp`, or `sftp`.",
        "Do not open an interactive login, allocate a TTY, run `ssh-add`, "
        "or retry a failure with `ssh -v`.",
        "Pass a script in `stdin`. The default timeout is 120 seconds.",
        "On the first remote step of a task, load the skill `holix-ssh` with `skill_view`.",
        "If `ssh_exec` fails, show its stderr and stop.",
        "If a Studio run target matches the host, use the Studio runtime tools "
        "instead of ssh_exec.",
    ]
    hint = format_ssh_target_hint(config_path)
    if hint:
        lines.append(hint)
    return "\n".join(lines)


class SshExecTool(BaseTool):
    """One non-interactive SSH command. No local shell and no TTY."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "ssh_exec"
        self.risk_level = "high"
        self.description = (
            "Run one non-interactive command on another machine. "
            "host is an SSH config alias or user@host. command is the remote "
            "command and is not parsed by the local shell. Pass a script as "
            "stdin. BatchMode is forced, so a password prompt fails immediately. "
            "Do not use run_terminal_command with ssh, scp, or sftp. "
            "Load skill holix-ssh with skill_view before the first remote command."
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "SSH config alias or user@host. Not a shell snippet.",
                },
                "command": {
                    "type": "string",
                    "description": "Remote command. The remote shell parses it.",
                },
                "stdin": {
                    "type": "string",
                    "description": "Optional text piped to the remote command.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds to wait (default 120, maximum 600).",
                    "default": _DEFAULT_TIMEOUT_S,
                },
            },
            "required": ["host", "command"],
        }

    async def execute(
        self,
        host: str = "",
        command: str = "",
        stdin: str = "",
        timeout: int = _DEFAULT_TIMEOUT_S,
    ) -> str:
        from core.tools.execution_context import is_run_cancelled

        if is_run_cancelled():
            return "Error: Run cancelled — ssh_exec not started."
        host_error = validate_ssh_host(host)
        if host_error:
            return host_error
        remote = (command or "").strip()
        if not remote:
            return "Error: command is empty."
        blocked, reason = command_whitelist.blocks_dangerous_patterns(remote)
        if blocked:
            return f"Error: Command blocked by safety policy. {reason}"
        # Remote profile paths are the other machine's files. The local
        # terminal guard still blocks ~/.holix on this host.
        if stdin and len(stdin) > _MAX_STDIN_CHARS:
            return f"Error: stdin is longer than {_MAX_STDIN_CHARS} characters."
        ssh_bin = shutil.which("ssh")
        if not ssh_bin:
            return "Error: ssh is not installed on this machine."
        argv = build_ssh_argv(host.strip(), remote)
        argv[0] = ssh_bin
        wait_s = clamp_ssh_timeout(timeout)
        payload = stdin.encode("utf-8") if stdin else None
        try:
            from core.security.os_sandbox import SandboxUnavailable, confine_argv
            from core.security.permission_preset import sandbox_mode_for_session
            from core.tools.execution_context import get_conversation_id, get_profile_name

            mode = sandbox_mode_for_session(get_profile_name(), get_conversation_id())
            if mode != "danger-full-access":
                argv = confine_argv(argv, mode=mode, workspace_root=None)
        except SandboxUnavailable as exc:
            return f"Error: {exc}"

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if payload is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_spawn_kwargs(),
            )
        except OSError as exc:
            return f"Error: Could not start ssh: {exc}"

        try:
            stdout, stderr = await _communicate_with_cancel(
                process,
                timeout=wait_s,
                command="ssh",
                stdin=payload,
            )
        except TimeoutError:
            return (
                f"Error: ssh_exec timed out after {int(wait_s)}s waiting for {host.strip()}. "
                "Show this to the user and stop. Do not retry with ssh -v."
            )
        except asyncio.CancelledError:
            return "Error: Run cancelled — ssh_exec stopped."

        output = truncate_terminal_output(
            sanitize_paths_in_text(stdout.decode("utf-8", errors="replace"))
        )
        error = truncate_terminal_output(
            sanitize_paths_in_text(stderr.decode("utf-8", errors="replace")),
            max_chars=8_192,
        )
        return _format_process_result(
            returncode=process.returncode or 0,
            output=output,
            error=error,
            command=remote,
        )
