"""Start and stop long-running project processes in the background."""

from __future__ import annotations

import re

from core.runtime.background_process_health import ProcessHealthReport
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name


def parse_start_tool_result(text: str) -> dict[str, str | int | bool] | None:
    """Extract process bar fields from start_background_process tool output."""
    body = (text or "").strip()
    if "Background process started" not in body and "Error:" not in body:
        return None

    fields: dict[str, str] = {}
    for key in ("id", "label", "pid"):
        match = re.search(rf"-\s*{key}:\s*(.+)", body, re.I)
        if match:
            fields[key] = match.group(1).strip()

    if "Error:" in body and "id" not in fields:
        return None
    if "id" not in fields:
        return None

    health_match = re.search(
        r"Background process health:\s*(\w+)",
        body,
        re.I,
    )
    health = (health_match.group(1) if health_match else "STARTING").lower()
    unhealthy = health in _UNHEALTHY_STATUSES
    pid_raw = fields.get("pid", "0")
    try:
        pid = int(str(pid_raw).split()[0])
    except ValueError:
        pid = 0

    return {
        "process_id": fields["id"],
        "label": fields.get("label", "process"),
        "pid": pid,
        "healthy": not unhealthy,
        "status": health,
    }


def _chat_id_from_bridge() -> str | None:
    from core.tools.execution_context import get_chat_delivery_bridge

    bridge = get_chat_delivery_bridge()
    if bridge is None:
        return None
    cid = getattr(bridge, "_chat_id", None) or getattr(bridge, "chat_id", None)
    return str(cid) if cid is not None else None


def _emit_process_event(agent_event_cls, **kwargs) -> None:
    import logging

    logger = logging.getLogger(__name__)
    try:
        from core.tools.execution_context import get_agent_emit

        emit = get_agent_emit()
        if emit is None:
            logger.debug("Background process event skipped — no agent emit scope")
            return
        emit(agent_event_cls(**kwargs))
    except Exception as exc:
        logger.warning("Failed to emit background process event: %s", exc)


def _emit_health_events(
    report: ProcessHealthReport,
    *,
    conversation_id: str,
) -> None:
    if report.status == "not_found":
        return
    if report.healthy or report.status in ("starting", "exited"):
        return
    try:
        from core.agent_events import BackgroundProcessErrorEvent

        summary = report.error_snippets[0] if report.error_snippets else report.status
        _emit_process_event(
            BackgroundProcessErrorEvent,
            process_id=report.process_id,
            label=report.label,
            pid=report.pid,
            status=report.status,
            error_summary=summary,
            log_path=report.log_path,
            conversation_id=conversation_id,
        )
    except Exception:
        pass


_UNHEALTHY_STATUSES = frozenset(
    {
        "crashed",
        "error_in_log",
        "port_in_use",
        "wrong_process_on_port",
        "port_not_listening",
    }
)


def _format_start_response(record, report: ProcessHealthReport) -> str:
    lines = [
        "Background process started.",
        f"- id: {record.process_id}",
        f"- label: {record.label}",
        f"- pid: {record.pid}",
        f"- log: {record.log_path}",
        "",
        report.format_text(),
    ]
    if report.status in _UNHEALTHY_STATUSES:
        if report.status in ("port_in_use", "wrong_process_on_port"):
            lines.append(
                "\nStop foreign listeners and restart on the **same** port via "
                "restart_background_process (same command)."
            )
        elif report.status == "port_not_listening":
            lines.append(
                "\nPort not listening — read the log, fix if needed, then "
                "restart_background_process with the same command."
            )
        else:
            lines.append(
                "\nFix the errors above, then restart_background_process with the "
                "same command and verify with check_background_process."
            )
    elif report.status == "starting":
        lines.append(
            "\nProcess is still starting — call check_background_process again in a few seconds."
        )
    else:
        lines.append(
            "\nThe user can stop it from the chat UI (⏹), TUI (/process-stop), "
            "or via stop_background_process."
        )
    return "\n".join(lines)


async def _run_start_or_restart(
    registry,
    *,
    command: str,
    label: str,
    working_directory: str,
    conversation_id: str,
    profile: str,
    chat_id: str | None,
    startup_wait_seconds: float,
    restart: bool,
) -> str:
    from core.runtime.port_utils import parse_listen_ports
    from core.security.workspace_command_guard import validate_workspace_command
    from core.tools.execution_context import is_workspace_jail_enabled
    from core.workspace import get_effective_workspace_root

    jail = is_workspace_jail_enabled()
    ws = get_effective_workspace_root()
    allowed, jail_reason = validate_workspace_command(
        command,
        str(ws) if ws is not None else None,
        jail_enabled=jail,
    )
    if not allowed:
        return f"Error: Command blocked. {jail_reason}"

    launch = registry.restart if restart else registry.start
    try:
        record = await launch(
            command=command,
            label=label or command.split()[0],
            conversation_id=conversation_id,
            profile=profile,
            chat_id=chat_id,
            cwd=working_directory or None,
        )
    except ValueError as exc:
        return (
            f"Error: {exc}\n"
            "Use restart_background_process with the same command after stop_background_process."
        )
    except Exception as exc:
        action = "restart" if restart else "start"
        return f"Error: Failed to {action} background process: {exc}"

    try:
        from core.agent_events import BackgroundProcessStartedEvent

        _emit_process_event(
            BackgroundProcessStartedEvent,
            process_id=record.process_id,
            label=record.label,
            command=record.command,
            pid=record.pid,
            log_path=record.log_path,
            conversation_id=conversation_id,
        )
    except Exception:
        pass

    default_wait = 4.0 if parse_listen_ports(command) else 0.0
    if "--reload" in command or " run dev" in command:
        default_wait = max(default_wait, 5.0)
    wait_s = max(0.0, min(float(startup_wait_seconds or default_wait), 10.0))
    report = await _check_and_format(
        registry,
        process_id=record.process_id,
        profile=profile,
        conversation_id=conversation_id,
        wait_s=wait_s,
    )
    prefix = "Background process restarted." if restart else "Background process started."
    body = _format_start_response(record, report)
    return body.replace("Background process started.", prefix, 1)


async def _check_and_format(
    registry,
    *,
    process_id: str,
    profile: str,
    conversation_id: str,
    wait_s: float,
) -> ProcessHealthReport:
    report = await registry.check_health(
        process_id=process_id,
        profile=profile,
        conversation_id=conversation_id,
        wait_s=wait_s,
    )
    _emit_health_events(report, conversation_id=conversation_id)
    return report


class StartBackgroundProcessTool(BaseTool):
    """Launch a project/server command as a detached background OS process."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "start_background_process"
        self.description = (
            "Start a long-running project command (dev server, API, worker) as a "
            "separate background OS process. Use for `npm run dev`, `uvicorn`, "
            "`python manage.py runserver`, etc. Returns immediately with pid and log path. "
            "Prefer this over run_terminal_command for servers that keep running. "
            "Automatically runs a startup health check; if unhealthy, fix errors and restart."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run in the project workspace",
                },
                "label": {
                    "type": "string",
                    "description": "Short human-readable label (e.g. 'FastAPI :8000')",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional working directory (defaults to workspace root)",
                },
                "startup_wait_seconds": {
                    "type": "number",
                    "description": "Seconds to wait before health check (default 0 — returns immediately; use check_background_process after)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        label: str = "",
        working_directory: str = "",
        startup_wait_seconds: float = 0.0,
    ) -> str:
        from config import settings

        if not settings.enable_terminal_tool:
            return "Error: Background process tool requires terminal tool (HOLIX_ENABLE_TERMINAL_TOOL=true)"

        from core.runtime.background_process import get_background_process_registry

        registry = get_background_process_registry()
        profile = get_profile_name()
        conversation_id = get_conversation_id()
        chat_id = _chat_id_from_bridge()

        return await _run_start_or_restart(
            registry,
            command=command,
            label=label,
            working_directory=working_directory,
            conversation_id=conversation_id,
            profile=profile,
            chat_id=chat_id,
            startup_wait_seconds=startup_wait_seconds,
            restart=False,
        )


class RestartBackgroundProcessTool(BaseTool):
    """Stop listeners on the target port(s) and start the same command again."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "restart_background_process"
        self.description = (
            "Stop any Holix/foreign listeners on the command's port(s), then start the "
            "same dev-server command again on the **same** port. Use when "
            "check_background_process reports crashed, error_in_log, wrong_process_on_port, "
            "or port_in_use — after fixing code/config if needed."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Same shell command as before (must keep the same port)",
                },
                "label": {
                    "type": "string",
                    "description": "Short label (e.g. 'FastAPI :8000')",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional working directory",
                },
                "startup_wait_seconds": {
                    "type": "number",
                    "description": "Seconds to wait before health+port check (default 2 when port in command)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        label: str = "",
        working_directory: str = "",
        startup_wait_seconds: float = 0.0,
    ) -> str:
        from config import settings

        if not settings.enable_terminal_tool:
            return "Error: Background process tool requires terminal tool (HOLIX_ENABLE_TERMINAL_TOOL=true)"

        from core.runtime.background_process import get_background_process_registry

        registry = get_background_process_registry()
        return await _run_start_or_restart(
            registry,
            command=command,
            label=label,
            working_directory=working_directory,
            conversation_id=get_conversation_id(),
            profile=get_profile_name(),
            chat_id=_chat_id_from_bridge(),
            startup_wait_seconds=startup_wait_seconds,
            restart=True,
        )


class CheckBackgroundProcessTool(BaseTool):
    """Verify a background process is alive and scan its log for errors."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "check_background_process"
        self.description = (
            "Check whether a background process is still running and scan its log for "
            "startup/runtime errors. Call after start_background_process and before "
            "telling the user the server is ready. If status is crashed or error_in_log, "
            "read the log, fix the code, restart, and check again."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "description": "Process id (optional — checks active process for this session)",
                },
                "wait_seconds": {
                    "type": "number",
                    "description": "Seconds to wait before reading the log (default 2)",
                },
            },
            "required": [],
        }

    async def execute(self, process_id: str = "", wait_seconds: float = 2.0) -> str:
        from core.runtime.background_process import get_background_process_registry

        registry = get_background_process_registry()
        profile = get_profile_name()
        conversation_id = get_conversation_id()
        wait_s = max(0.0, min(float(wait_seconds or 2.0), 60.0))

        report = await _check_and_format(
            registry,
            process_id=process_id.strip() or None,
            profile=profile,
            conversation_id=conversation_id,
            wait_s=wait_s,
        )
        text = report.format_text()
        if report.status in ("port_in_use", "wrong_process_on_port"):
            text += (
                "\n\nRequired: call restart_background_process with the **same** command "
                "(same port). Do not change the port number."
            )
        elif report.status == "port_not_listening":
            text += (
                "\n\nRequired: read the log, fix if needed, then restart_background_process "
                "with the same command and check again."
            )
        elif report.status in ("crashed", "error_in_log"):
            text += (
                "\n\nRequired: fix the root cause, then restart_background_process "
                "with the same command and check again until healthy."
            )
        elif report.status == "starting":
            text += "\n\nWait a few seconds and call check_background_process again."
        return text


class StopBackgroundProcessTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "stop_background_process"
        self.description = "Stop a background process started with start_background_process."
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "description": "Process id from start_background_process (optional — stops active process for this chat if omitted)",
                },
            },
            "required": [],
        }

    async def execute(self, process_id: str = "") -> str:
        from core.runtime.background_process import get_background_process_registry
        from core.runtime.port_utils import parse_listen_ports, ports_in_use

        registry = get_background_process_registry()
        profile = get_profile_name()
        conversation_id = get_conversation_id()
        target = (process_id or "").strip()

        if target:
            record = await registry.stop(target)
        else:
            record = await registry.stop_for_scope(
                profile=profile,
                conversation_id=conversation_id,
            )
        if record is None:
            record = await registry.stop_for_profile(profile=profile)

        if record is None:
            return "No matching background process found."

        ports = parse_listen_ports(record.command)
        still_busy = ports_in_use(ports) if ports else []

        try:
            from core.agent_events import BackgroundProcessStoppedEvent

            _emit_process_event(
                BackgroundProcessStoppedEvent,
                process_id=record.process_id,
                label=record.label,
                pid=record.pid,
                conversation_id=conversation_id,
            )
        except Exception:
            pass

        msg = f"Stopped background process {record.process_id} (pid {record.pid})."
        if still_busy:
            busy = ", ".join(str(p) for p in still_busy)
            msg += (
                f"\nWarning: port(s) {busy} still in use — another process may be holding them. "
                f"Run `lsof -i :PORT` and kill manually if needed."
            )
        return msg


class ListBackgroundProcessesTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "list_background_processes"
        self.description = (
            "List background processes for the current chat session with running/stopped status."
        )
        self.risk_level = "low"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        from core.runtime.background_process import get_background_process_registry

        registry = get_background_process_registry()
        profile = get_profile_name()
        conversation_id = get_conversation_id()
        records = registry.list_for_scope(
            profile=profile,
            conversation_id=conversation_id,
        )
        if not records:
            return "No background processes for this session."
        lines = []
        for rec in records:
            running = rec.is_running()
            status = "running" if running else "stopped"
            lines.append(
                f"- {rec.process_id}: {rec.label} pid={rec.pid} ({status}) log={rec.log_path}"
            )
        lines.append("Use check_background_process to scan logs for errors.")
        return "\n".join(lines)


def register_background_process_tools(registry) -> None:
    start_tool = StartBackgroundProcessTool()
    registry.register(start_tool)
    registry.register(RestartBackgroundProcessTool())
    registry.register(CheckBackgroundProcessTool())
    registry.register(StopBackgroundProcessTool())
    registry.register(ListBackgroundProcessesTool())