"""One-shot background jobs for the current agent (not sub-agents, not servers).

The agent starts a finite command, stays free for the user, and is woken with
the output when the command exits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from core.platform_compat import IS_WINDOWS

logger = logging.getLogger(__name__)

MAX_RUNNING_PER_CONVERSATION = 8
_KEEP_FINISHED = 12

TaskListener = Callable[["AgentBackgroundTask"], None]


@dataclass(slots=True)
class AgentBackgroundTask:
    task_id: str
    description: str
    command: str
    profile: str
    conversation_id: str
    status: str = "running"  # running | completed | failed | killed
    exit_code: int | None = None
    output: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    pid: int | None = None
    stop_requested: bool = False
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _notified: bool = False

    def is_running(self) -> bool:
        return self.status == "running"

    def age_seconds(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0, int(end - self.started_at))


def format_agent_task_wakeup(task: AgentBackgroundTask) -> str:
    """Prompt so the same agent reports the result. Not shown as a user bubble."""
    if task.status == "killed":
        how = "was stopped"
    elif task.exit_code == 0:
        how = "finished successfully"
    else:
        how = f"failed (exit {task.exit_code})"
    body = (task.output or "").strip() or "(no output)"
    return (
        f"Background task `{task.description}` (id={task.task_id}) {how}. "
        "This is the same agent, not a sub-agent. Show the user the result. "
        "Do not re-run the command unless it failed and a fix is obvious.\n\n"
        f"Command: {task.command}\n\n"
        f"Output:\n{body}"
    )


def started_task_message(task: AgentBackgroundTask) -> str:
    return (
        f"Background task started: id={task.task_id} — {task.description}. "
        "You are free to keep helping the user; do not poll and do not wait. "
        "When it finishes you will be woken with the output — report that result. "
        "This is not a sub-agent."
    )


class AgentTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, AgentBackgroundTask] = {}
        self._listeners: list[TaskListener] = []

    def register_listener(self, listener: TaskListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unregister_listener(self, listener: TaskListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def get(self, task_id: str) -> AgentBackgroundTask | None:
        return self._tasks.get((task_id or "").strip())

    def list_for(
        self,
        *,
        profile: str,
        conversation_id: str,
    ) -> list[AgentBackgroundTask]:
        prof = (profile or "").strip()
        conv = (conversation_id or "").strip()
        rows = [
            task
            for task in self._tasks.values()
            if task.profile == prof and task.conversation_id == conv
        ]
        rows.sort(key=lambda task: task.started_at, reverse=True)
        return rows

    def running_count(self, *, profile: str, conversation_id: str) -> int:
        return sum(
            1
            for task in self.list_for(profile=profile, conversation_id=conversation_id)
            if task.is_running()
        )

    async def launch_shell(
        self,
        *,
        command: str,
        description: str,
        profile: str,
        conversation_id: str,
        cwd: str | None,
        use_shell: bool,
        argv: list[str] | None,
        spawn_kw: dict,
    ) -> AgentBackgroundTask | str:
        prof = (profile or "default").strip() or "default"
        conv = (conversation_id or "default").strip() or "default"
        running = self.running_count(profile=prof, conversation_id=conv)
        if running >= MAX_RUNNING_PER_CONVERSATION:
            return (
                f"Error: {running} background tasks are already running in this chat. "
                "Wait for one to finish or stop_agent_task before starting another."
            )
        label = (description or "").strip() or _short_command(command)
        task = AgentBackgroundTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            description=label[:120],
            command=command,
            profile=prof,
            conversation_id=conv,
        )
        try:
            if use_shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    **spawn_kw,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *(argv or []),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    **spawn_kw,
                )
        except Exception as exc:
            return f"Error starting background task: {exc}"
        task.pid = process.pid
        task._process = process
        self._tasks[task.task_id] = task
        self._trim(prof, conv)
        asyncio.create_task(self._watch(task, process))
        return task

    async def stop(self, task_id: str) -> str:
        task = self.get(task_id)
        if task is None:
            return f"Error: Unknown background task '{task_id}'."
        if not task.is_running():
            return f"Task {task.task_id} is already {task.status} (exit {task.exit_code})."
        task.stop_requested = True
        process = task._process
        if process is not None:
            await _kill_process(process)
        return f"Stopping background task {task.task_id} ({task.description})."

    def format_list(self, *, profile: str, conversation_id: str) -> str:
        rows = self.list_for(profile=profile, conversation_id=conversation_id)
        if not rows:
            return "No background tasks in this chat."
        lines = ["Background tasks (same agent, not sub-agents):"]
        for task in rows:
            if task.is_running():
                lines.append(f"- {task.task_id} running {task.age_seconds()}s — {task.description}")
            else:
                lines.append(
                    f"- {task.task_id} {task.status} exit={task.exit_code} "
                    f"({task.age_seconds()}s) — {task.description}"
                )
        return "\n".join(lines)

    async def _watch(self, task: AgentBackgroundTask, process: asyncio.subprocess.Process) -> None:
        try:
            stdout_b, stderr_b = await process.communicate()
        except Exception as exc:
            logger.warning("background task %s watcher failed: %s", task.task_id, exc)
            stdout_b, stderr_b = b"", str(exc).encode()
            task.exit_code = -1
        else:
            task.exit_code = int(process.returncode if process.returncode is not None else -1)
        task.finished_at = time.time()
        task.output = _format_output(stdout_b, stderr_b)
        if task.stop_requested:
            task.status = "killed"
        elif task.exit_code == 0:
            task.status = "completed"
        else:
            task.status = "failed"
        task._process = None
        self._notify(task)

    def _notify(self, task: AgentBackgroundTask) -> None:
        if task._notified:
            return
        task._notified = True
        for listener in list(self._listeners):
            try:
                listener(task)
            except Exception:
                logger.debug("agent task listener failed", exc_info=True)

    def _trim(self, profile: str, conversation_id: str) -> None:
        finished = [
            task
            for task in self.list_for(profile=profile, conversation_id=conversation_id)
            if not task.is_running()
        ]
        if len(finished) <= _KEEP_FINISHED:
            return
        for task in finished[_KEEP_FINISHED:]:
            self._tasks.pop(task.task_id, None)

    def clear(self) -> None:
        """Test helper."""
        self._tasks.clear()
        self._listeners.clear()


def _short_command(command: str) -> str:
    text = " ".join((command or "").split())
    return text[:80] or "command"


def _format_output(stdout_b: bytes, stderr_b: bytes) -> str:
    from core.memory.tool_content import truncate_terminal_output
    from core.workspace import sanitize_paths_in_text

    stdout = sanitize_paths_in_text(stdout_b.decode("utf-8", errors="replace")).strip()
    stderr = sanitize_paths_in_text(stderr_b.decode("utf-8", errors="replace")).strip()
    parts: list[str] = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append("stderr:\n" + stderr)
    return truncate_terminal_output("\n".join(parts))


async def _kill_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if not IS_WINDOWS and process.pid:
            try:
                os.killpg(process.pid, 15)
            except (ProcessLookupError, PermissionError, OSError):
                process.kill()
        else:
            process.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except (TimeoutError, ProcessLookupError):
        try:
            if not IS_WINDOWS and process.pid:
                os.killpg(process.pid, 9)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass


_registry = AgentTaskRegistry()


def get_agent_task_registry() -> AgentTaskRegistry:
    return _registry


def register_agent_task_listener(listener: TaskListener) -> None:
    _registry.register_listener(listener)


def unregister_agent_task_listener(listener: TaskListener) -> None:
    _registry.unregister_listener(listener)
