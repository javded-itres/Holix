import asyncio
import os
import shlex

from config import settings
from core.platform_compat import IS_WINDOWS, subprocess_shell_kwargs
from core.runtime.introspect_signals import (
    INTROSPECT_REFUSAL,
    is_introspect_command,
)
from core.runtime.service_detect import (
    is_long_oneshot_job,
    is_untracked_long_running_command,
    listen_ports_for_pid_tree,
    service_watch_after,
    service_watch_interval,
)
from core.security.safety import command_needs_shell, command_whitelist
from core.security.workspace_command_guard import (
    references_holix_profiles,
    validate_workspace_command,
)
from core.tools.base import BaseTool
from core.workspace import sanitize_paths_in_text

# Re-exports so supervisor / tests keep importing from this module.
_is_untracked_long_running_command = is_untracked_long_running_command


class PromoteForegroundService(Exception):
    """Foreground command is a listening service — move it to the registry."""

    def __init__(self, ports: list[int]):
        self.ports = list(ports)
        super().__init__(f"foreground service on ports {self.ports}")


def _env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def terminal_whitelist_enabled() -> bool:
    """Whether the terminal allowlist is enforced.

    Priority:
    1. Profile ``.env`` (Settings UI / ``profile whitelist``) — wins over systemd
       EnvironmentFile. Studio often sets ``HOLIX_TERMINAL_COMMAND_WHITELIST`` in
       ``/etc/holix/studio.env`` at process start; those keys are shell-locked and
       would otherwise ignore profile toggles until restart.
    2. Process environment (if profile file has no key).
    3. Settings singleton default.
    """
    try:
        from core.env_loader import active_profile_name, read_profile_env_map
        from core.terminal_whitelist_config import (
            WHITELIST_ENABLED_KEY,
            WHITELIST_ENABLED_LEGACY_KEY,
            read_whitelist_enabled,
        )

        profile = active_profile_name()
        env_map = read_profile_env_map(profile)
        if WHITELIST_ENABLED_KEY in env_map or WHITELIST_ENABLED_LEGACY_KEY in env_map:
            return read_whitelist_enabled(profile)
    except Exception:
        pass
    for key in ("HOLIX_TERMINAL_COMMAND_WHITELIST", "TERMINAL_COMMAND_WHITELIST"):
        if key in os.environ:
            return _env_bool(os.environ.get(key), default=True)
    return bool(settings.terminal_command_whitelist)


def terminal_whitelist_extra() -> str:
    """Extra allowlist prefixes — profile file first (same reason as enabled)."""
    try:
        from core.env_loader import active_profile_name, read_profile_env_map
        from core.terminal_whitelist_config import (
            WHITELIST_EXTRA_KEY,
            WHITELIST_EXTRA_LEGACY_KEY,
            format_command_list,
            read_whitelist_extra,
        )

        profile = active_profile_name()
        env_map = read_profile_env_map(profile)
        if WHITELIST_EXTRA_KEY in env_map or WHITELIST_EXTRA_LEGACY_KEY in env_map:
            return format_command_list(read_whitelist_extra(profile))
    except Exception:
        pass
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

    The profile **workspace** is always allowed when ``workspace_root`` is known
    (jail on or off). Without that exception, jail-off admin profiles could not
    ``mv``/``cp`` into ``.../profiles/<name>/workspace`` because the path still
    matches the Holix profiles tree — while secrets (``.env``, other profiles)
    stay blocked either way.

    ``jail_enabled`` is kept for call-site clarity; allowlisting uses
    ``workspace_root`` only.
    """
    del jail_enabled  # secrets guard is independent of jail; see allow_under
    normalized = command.replace("\\", "/").lower()
    # Always allow the configured workspace, even when jail is disabled.
    allow_under = workspace_root if workspace_root else None
    if references_holix_profiles(command, allow_under=allow_under):
        ws_hint = f" Own workspace is allowed: `{workspace_root}`." if workspace_root else ""
        return (
            True,
            "Access to Holix profile directories and secrets is not allowed "
            f"(`.env`, other profiles, profile data — not the workspace).{ws_hint}",
        )
    if (
        ".holix/memory-cache" in normalized
        or "/memory-cache/" in normalized
        or ".runtime-cache" in normalized
        or "/.runtime-cache/" in normalized
    ):
        return True, "Direct access to decrypted memory cache is not allowed."
    return False, ""


def _format_access_denial(*, returncode: int, output: str, error: str) -> str | None:
    """Human-readable explanation for common permission / policy failures."""
    blob = f"{output or ''}\n{error or ''}".lower()
    if not blob.strip() and returncode == 0:
        return None

    # sudo / root
    if (
        "i'm afraid i can't do that" in blob
        or "a password is required" in blob
        or "sudo: " in blob
        and ("not allowed" in blob or "password" in blob or "sorry" in blob)
        or "must be run as root" in blob
        or "operation not permitted" in blob
        or "permission denied" in blob
    ):
        return (
            f"Error (exit code {returncode}): **нет прав доступа**.\n"
            "Команда отклонена ОС (часто: `sudo` недоступен пользователю `holix`, "
            "нет root, или нет прав на файл/каталог).\n"
            "Что делать:\n"
            "- **не** пытаться через sudo от имени holix — это ожидаемо запрещено;\n"
            "- выполнять только в workspace профиля / то, что разрешено jail;\n"
            "- для systemctl/kill чужих процессов нужен root **вне** агента "
            "(ops/SSH), либо отдельный unit, которым holix уже владеет;\n"
            "- переформулировать задачу без привилегий (остановить *свой* "
            "background process через stop_background_process).\n"
            f"STDOUT:\n{output or '(пусто)'}\nSTDERR:\n{error or '(пусто)'}"
        )
    if "access denied" in blob or "authentication failed" in blob:
        return (
            f"Error (exit code {returncode}): **доступ запрещён** (auth/ACL).\n"
            "Проверьте токены/ключи, права на API и что команда идёт от holix.\n"
            f"STDOUT:\n{output or '(пусто)'}\nSTDERR:\n{error or '(пусто)'}"
        )
    return None


def _format_process_result(
    *,
    returncode: int,
    output: str,
    error: str,
) -> str:
    if returncode == 0:
        return f"Success (exit code 0):\n{output}" if output else "Success (no output)"
    access = _format_access_denial(returncode=returncode, output=output, error=error)
    if access:
        return access
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
    command: str = "",
) -> tuple[bytes, bytes]:
    """Wait for process output, honouring cooperative cancel and hard timeout.

    After ~60s, if the command is still running and the process tree has a
    TCP LISTEN socket, raise :class:`PromoteForegroundService` so the caller
    can restart it as a tracked background process. Long one-shots
    (``cargo test``, ``mvn package``, ``pytest``) are never promoted.
    """
    from core.tools.execution_context import is_run_cancelled

    comm = asyncio.create_task(process.communicate())
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + max(0.1, float(timeout))
    poll = 0.2
    watch_after = service_watch_after()
    watch_interval = service_watch_interval()
    # First listen-check fires as soon as ``watch_after`` elapses.
    last_watch = started - watch_interval
    watch_command = (command or "").strip()
    allow_watch = bool(watch_command) and not is_long_oneshot_job(watch_command)

    try:
        while not comm.done():
            if is_run_cancelled():
                await _kill_process_tree(process)
                raise asyncio.CancelledError("run cancelled")

            now = loop.time()
            remaining = deadline - now
            if remaining <= 0:
                await _kill_process_tree(process)
                raise TimeoutError()

            if (
                allow_watch
                and process.returncode is None
                and (now - started) >= watch_after
                and (now - last_watch) >= watch_interval
            ):
                last_watch = now
                pid = int(process.pid or 0)
                ports = await asyncio.to_thread(listen_ports_for_pid_tree, pid)
                if ports:
                    await _kill_process_tree(process)
                    raise PromoteForegroundService(ports)

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


def _promote_label(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return "promoted-service"
    token = text.split()[0]
    return (token or "promoted-service")[:120]


async def _promote_to_background(
    command: str,
    *,
    cwd: str | None,
    ports: list[int],
) -> str:
    """Kill already happened; start the same command via the bg registry."""
    from core.runtime.port_utils import force_free_ports
    from core.tools.background_process import _chat_id_from_bridge, _run_start_or_restart
    from core.tools.execution_context import get_conversation_id, get_profile_name

    if ports:
        await asyncio.to_thread(force_free_ports, ports)

    from core.runtime.background_process import get_background_process_registry

    registry = get_background_process_registry()
    port_txt = ", ".join(str(p) for p in ports) if ports else "unknown"
    try:
        body = await _run_start_or_restart(
            registry,
            command=command,
            label=_promote_label(command),
            working_directory=cwd or "",
            conversation_id=get_conversation_id(),
            profile=get_profile_name(),
            chat_id=_chat_id_from_bridge(),
            startup_wait_seconds=3.0,
            restart=False,
        )
    except Exception as exc:
        return (
            f"Error: Command ran in the foreground for over a minute and "
            f"opened TCP listen port(s) {port_txt} — this is a service, not "
            f"a one-shot job. It was stopped. Restart it with "
            f"start_background_process using the same command.\n"
            f"Auto-restart failed: {exc}"
        )
    if body.startswith("Error:"):
        return (
            f"The foreground command was a service (listen on {port_txt} "
            f"after ~1 min) and was stopped. Restart it with "
            f"start_background_process.\n{body}"
        )
    return (
        f"The command kept running for over a minute and opened TCP listen "
        f"port(s) {port_txt} — this is a service, not a long one-shot "
        f"(compile/test). It was stopped in the foreground and restarted "
        f"via start_background_process.\n\n"
        f"{body}\n\n"
        "Use check_background_process / stop_background_process from now on. "
        "Do not launch this command via run_terminal_command again."
    )


class TerminalTool(BaseTool):
    """Tool for executing terminal commands safely."""

    def __init__(self):
        super().__init__()
        self.name = "run_terminal_command"
        self.description = (
            "Execute a short terminal command and return its output. "
            "Shell operators (&&, |, >, etc.) are supported. "
            "Use for system operations, package installation, git commands, tests, builds. "
            "Do NOT use for long-running bots/servers "
            "(uvicorn, cargo run, go run, java -jar, dotnet run, npm run dev, …) — "
            "use start_background_process so the process is tracked across restarts. "
            "If a missed server stays in the foreground for over a minute and "
            "opens a listen port, this tool stops it and restarts it in the background. "
            "Permission errors (sudo/root) are returned as clear access-denied messages."
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

        if is_introspect_command(command):
            return INTROSPECT_REFUSAL

        # Nudge away from untracked long-running bots/servers.
        # Do not treat `pip install uvicorn` as launching uvicorn.
        if _is_untracked_long_running_command(command):
            return (
                "Error: This looks like a **long-running** bot/server "
                "(uvicorn, cargo run, go run, java -jar, dotnet run, "
                "npm run dev, docker compose up, …). "
                "Do **not** launch it via run_terminal_command (it will not be "
                "tracked after reboot and can conflict with Holix Telegram). "
                "Use **start_background_process** with the same command instead, "
                "then check_background_process / stop_background_process. "
                "Never start a second Telegram long-poll with the same bot token "
                "as holix-gateway (TelegramConflictError). "
                "Installing packages and running tests/builds "
                "(`pip install`, `cargo test`, `go test`, `mvn package`) is fine "
                "here; only *starting* the server belongs in start_background_process."
            )

        # Destructive patterns always apply; full command allowlist is optional.
        if terminal_whitelist_enabled():
            command_whitelist.apply_extra(terminal_whitelist_extra())
            allowed, reason = command_whitelist.is_command_allowed(command)
            if not allowed:
                return f"Error: Command blocked by safety policy. {reason}"
        else:
            blocked_danger, danger_reason = command_whitelist.blocks_dangerous_patterns(command)
            if blocked_danger:
                return f"Error: Command blocked by safety policy. {danger_reason}"

        try:
            from core.tools.execution_context import (
                get_workspace_root,
                is_workspace_jail_enabled,
            )
            from core.workspace import get_effective_workspace_root

            jail = is_workspace_jail_enabled()
            # Jail root (None when jail off) — used for cwd + path escape checks.
            root = get_effective_workspace_root()
            root_s = str(root) if root is not None else None
            # Configured profile workspace even when jail is off — needed so
            # commands may touch .../profiles/<name>/workspace without being
            # treated as a secrets-path hit.
            configured_ws = (get_workspace_root() or "").strip() or None
            secrets_allow = root_s or configured_ws

            blocked, reason = _blocked_sensitive_path_access(
                command,
                jail_enabled=jail,
                workspace_root=secrets_allow,
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
                return "Error: Workspace jail is enabled but no workspace root is configured."

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
                    process,
                    timeout=float(timeout or 30),
                    command=command,
                )

                from core.memory.tool_content import truncate_terminal_output

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
                )

            except PromoteForegroundService as promo:
                await _kill_process_tree(process)
                return await _promote_to_background(
                    command,
                    cwd=cwd,
                    ports=promo.ports,
                )
            except TimeoutError:
                await _kill_process_tree(process)
                return f"Error: Command timed out after {timeout} seconds"
            except asyncio.CancelledError:
                await _kill_process_tree(process)
                return "Error: Run cancelled — terminal command terminated."

        except Exception as e:
            return f"Error executing command: {str(e)}"
