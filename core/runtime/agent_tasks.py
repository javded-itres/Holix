"""One-shot background jobs for the current agent (not sub-agents, not servers).

The agent starts a finite command, stays free for the user, and is woken with
the output when the command exits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

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
    _async_job: asyncio.Task[None] | None = field(default=None, repr=False)
    _notified: bool = False

    def is_running(self) -> bool:
        return self.status == "running"

    def age_seconds(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0, int(end - self.started_at))


def media_generation_already_started(messages: list[dict[str, Any]] | None) -> bool:
    """True after this user turn already started one image or video task.

    Reflection notes are skipped, so a quality retry cannot launch a second
    generation to "fix" the picture.
    """
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "user":
            if content.startswith("## Reflexion"):
                continue
            if content.startswith("Background task `"):
                continue
            return False
        if role == "tool" and content.startswith("Background task started:"):
            return True
    return False


def task_list_is_idle(text: str | None) -> bool:
    """True when a list_agent_tasks result has nothing still running."""
    body = text or ""
    if "No background tasks" in body:
        return True
    if re.search(r"\brunning\b", body):
        return False
    return any(word in body for word in ("completed", "failed", "killed"))


_MEDIA_TOOL_NAMES = frozenset({"generate_image", "generate_video"})


def _tool_call_name(call: dict[str, Any]) -> str:
    fn = call.get("function") if isinstance(call, dict) else None
    if not isinstance(fn, dict):
        return ""
    return str(fn.get("name") or "")


def _tool_call_prompt(call: dict[str, Any]) -> str:
    fn = call.get("function") if isinstance(call, dict) else None
    if not isinstance(fn, dict):
        return ""
    raw = fn.get("arguments") or ""
    if not isinstance(raw, str):
        raw = json.dumps(raw)
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw.strip()
    if not isinstance(parsed, dict):
        return ""
    return str(parsed.get("prompt") or "").strip()


def collapse_repeat_media_calls(
    tool_calls: list[dict[str, Any]],
    *,
    profile: str,
    conversation_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Drop duplicate image/video calls. Stop if every one was already started.

    One model step can request the same ``generate_image`` dozens of times.
    Each call is a line in the transcript even when the tool refuses it.
    """
    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    media_prompts: list[tuple[str, str]] = []
    for call in tool_calls or []:
        name = _tool_call_name(call)
        if name not in _MEDIA_TOOL_NAMES:
            kept.append(call)
            continue
        prompt = _tool_call_prompt(call)
        key = (name, prompt)
        if key in seen:
            continue
        seen.add(key)
        media_prompts.append(key)
        kept.append(call)
    if not media_prompts:
        return kept, None
    if any(_tool_call_name(call) not in _MEDIA_TOOL_NAMES for call in kept):
        return kept, None
    matched = [
        task
        for task in get_agent_task_registry().list_for(
            profile=profile, conversation_id=conversation_id
        )
        if (task.command or "").strip() in {prompt for _name, prompt in media_prompts if prompt}
        and (task.is_running() or task.status == "completed")
    ]
    prompts = {prompt for _name, prompt in media_prompts if prompt}
    if matched and prompts <= {(task.command or "").strip() for task in matched}:
        lines = ["Повторно запускать генерацию не нужно."]
        for task in matched:
            if task.is_running():
                lines.append(
                    f"Задача {task.task_id} ещё выполняется. Ссылка появится, когда файл сохранится."
                )
            else:
                lines.append(f"Задача {task.task_id} уже завершена.")
                saved = (task.output or "").strip()
                if saved:
                    lines.append(saved)
        return [], "\n".join(lines)
    return kept, None


def stop_idle_task_lookup(state: dict[str, Any], tool_calls: list[dict[str, Any]]) -> str | None:
    """Final text when the model polls list_agent_tasks after the list is idle.

    Returns None if the calls should run.
    """
    names: list[str] = []
    for call in tool_calls or []:
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict):
            return None
        names.append(str(fn.get("name") or ""))
    if not names or any(name != "list_agent_tasks" for name in names):
        return None
    if not _already_listed_idle_tasks(state):
        return None
    return (
        "Фоновых задач нет. Повторно их искать не нужно. "
        "Если картинка уже сгенерирована, ссылка на файл уже в переписке."
    )


def _already_listed_idle_tasks(state: dict[str, Any]) -> bool:
    for item in reversed(state.get("tool_results") or []):
        if not isinstance(item, dict) or item.get("tool_name") != "list_agent_tasks":
            continue
        return task_list_is_idle(str(item.get("result") or ""))
    for msg in reversed(state.get("messages") or []):
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        if content.startswith("Background tasks") or content.startswith("No background tasks"):
            return task_list_is_idle(content)
    return False


def format_agent_task_wakeup(task: AgentBackgroundTask) -> str:
    """Prompt so the same agent reports the result. Not shown as a user bubble."""
    if task.status == "killed":
        how = "was stopped"
    elif task.exit_code == 0:
        how = "finished successfully"
    else:
        how = f"failed (exit {task.exit_code})"
    body = (task.output or "").strip() or "(no output)"
    if task.exit_code == 0 and "details button" in body and body.startswith("Saved "):
        return (
            f"Background task `{task.description}` (id={task.task_id}) finished successfully. "
            "The image or video is already in the chat with a details button. "
            "Do not mention provider, model, seed, size, path, bytes, or the prompt. "
            "Do not call send_chat_files or generate again. "
            "Reply with one short sentence at most.\n\n"
            f"Output:\n{body}"
        )
    return (
        f"Background task `{task.description}` (id={task.task_id}) {how}. "
        "This is the same agent, not a sub-agent. Tell the user the result "
        "in your own words. Do not paste this note. "
        "Do not run this same command again if it succeeded. "
        "If it failed, fix the obvious cause once (for example `source` is not "
        "a command in /bin/sh — call `.venv/bin/pip` directly). "
        "A finished install is not a running bot or server. If the user asked "
        "to start or restart one, or agreed when you offered, call "
        "start_background_process now with the project command. "
        "Do not use nohup, `&`, or run_terminal_command for that process.\n\n"
        f"Command: {task.command}\n\n"
        f"Output:\n{body}"
    )


def started_task_message(task: AgentBackgroundTask) -> str:
    return (
        f"Background task started: id={task.task_id} — {task.description}. "
        "Do not paste this note to the user and do not end the turn with only it. "
        "Do not poll. You will be woken with the output when it exits. "
        "If the user asked to start or restart a bot or server, this job is not "
        "that process: after it finishes, call start_background_process. "
        "Do not launch it with nohup, `&`, source, or run_terminal_command. "
        "This is not a sub-agent."
    )


class AgentTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, AgentBackgroundTask] = {}
        self._listeners: list[TaskListener] = []
        self._start_listeners: list[TaskListener] = []

    def register_listener(self, listener: TaskListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def register_start_listener(self, listener: TaskListener) -> None:
        if listener not in self._start_listeners:
            self._start_listeners.append(listener)

    def unregister_start_listener(self, listener: TaskListener) -> None:
        try:
            self._start_listeners.remove(listener)
        except ValueError:
            pass

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
        self._announce_start(task)
        asyncio.create_task(self._watch(task, process))
        return task

    async def launch_async(
        self,
        *,
        description: str,
        profile: str,
        conversation_id: str,
        runner: Callable[[], Awaitable[str]],
        command: str = "",
    ) -> AgentBackgroundTask | str:
        """Run an in-process job. Returns immediately; the agent is woken when it ends.

        No wall-clock limit. ``stop`` cancels the job. The task copies the caller's
        context (chat delivery, profile) at creation time.
        """
        prof = (profile or "default").strip() or "default"
        conv = (conversation_id or "default").strip() or "default"
        running = self.running_count(profile=prof, conversation_id=conv)
        if running >= MAX_RUNNING_PER_CONVERSATION:
            return (
                f"Error: {running} background tasks are already running in this chat. "
                "Wait for one to finish or stop_agent_task before starting another."
            )
        label = (description or "").strip() or "background job"
        task = AgentBackgroundTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            description=label[:120],
            command=(command or label)[:500],
            profile=prof,
            conversation_id=conv,
        )
        self._tasks[task.task_id] = task
        self._trim(prof, conv)
        self._announce_start(task)
        task._async_job = asyncio.create_task(self._watch_async(task, runner))
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
        job = task._async_job
        if job is not None and not job.done():
            job.cancel()
            try:
                await job
            except asyncio.CancelledError:
                pass
        # Cancel before the watcher starts never enters its try/finally.
        if task.is_running():
            task.status = "killed"
            task.exit_code = -1
            task.finished_at = time.time()
            if not (task.output or "").strip():
                task.output = "stopped"
            self._notify(task)
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

    async def _watch_async(
        self,
        task: AgentBackgroundTask,
        runner: Callable[[], Awaitable[str]],
    ) -> None:
        try:
            task.output = await runner()
            task.exit_code = 0
            task.status = "killed" if task.stop_requested else "completed"
        except asyncio.CancelledError:
            task.exit_code = -1
            task.status = "killed"
            if not (task.output or "").strip():
                task.output = "stopped"
            raise
        except Exception as exc:
            logger.warning("background task %s failed: %s", task.task_id, exc)
            task.exit_code = 1
            task.status = "failed"
            task.output = str(exc)
        finally:
            if task.finished_at is None:
                task.finished_at = time.time()
                task._async_job = None
                self._notify(task)

    def _notify(self, task: AgentBackgroundTask) -> None:
        if task._notified:
            return
        task._notified = True
        self._emit_task(task, "finished")
        for listener in list(self._listeners):
            try:
                listener(task)
            except Exception:
                logger.debug("agent task listener failed", exc_info=True)

    def _announce_start(self, task: AgentBackgroundTask) -> None:
        self._emit_task(task, "started")
        for listener in list(self._start_listeners):
            try:
                listener(task)
            except Exception:
                logger.debug("agent task start listener failed", exc_info=True)

    def _emit_task(self, task: AgentBackgroundTask, phase: str) -> None:
        try:
            from core.agent_events import AgentTaskFinishedEvent, AgentTaskStartedEvent
        except Exception:
            return
        if phase == "started":
            event = AgentTaskStartedEvent(
                task_id=task.task_id,
                description=task.description,
                status="running",
            )
        else:
            event = AgentTaskFinishedEvent(
                task_id=task.task_id,
                description=task.description,
                status=task.status,
            )
        event.conversation_id = task.conversation_id
        for bus in list(_buses):
            try:
                bus.emit(event)
            except Exception:
                logger.debug("agent task event emit failed", exc_info=True)

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
        self._start_listeners.clear()


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


_buses: list[Any] = []
_registry = AgentTaskRegistry()


def bind_agent_task_bus(bus: Any) -> None:
    """Forward task start/finish onto an agent event bus (Studio, TUI, logs)."""
    if bus is not None and bus not in _buses:
        _buses.append(bus)


def get_agent_task_registry() -> AgentTaskRegistry:
    return _registry


def register_agent_task_listener(listener: TaskListener) -> None:
    _registry.register_listener(listener)


def register_agent_task_start_listener(listener: TaskListener) -> None:
    _registry.register_start_listener(listener)


def unregister_agent_task_start_listener(listener: TaskListener) -> None:
    _registry.unregister_start_listener(listener)


def unregister_agent_task_listener(listener: TaskListener) -> None:
    _registry.unregister_listener(listener)
