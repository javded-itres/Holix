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
import threading
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
    _last_progress_at: float = 0.0

    def is_running(self) -> bool:
        return self.status == "running"

    def age_seconds(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0, int(end - self.started_at))


def media_generation_already_started(messages: list[dict[str, Any]] | None) -> bool:
    """True after this user turn already started one image or video task.

    A wake-up (``Background task `…``) is a new turn, so the model may continue
    an open checklist, including another generation. Reflexion notes are still
    skipped: a quality retry must not launch a second generation of a picture
    that has not been delivered yet.
    """
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "user":
            if content.startswith("## Reflexion"):
                continue
            # A real user message or a finished-task wake-up starts a fresh turn.
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


def is_background_start_note(text: str | None) -> bool:
    """True when the assistant only echoed the tool's start note."""
    return (text or "").strip().startswith("Background task started:")


def is_agent_task_wakeup(text: str | None) -> bool:
    """True for the hidden turn that delivers a finished task's output."""
    return (text or "").lstrip().startswith("Background task `")


def _latest_user_text(messages: list[Any] | None) -> str:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = str(msg.get("content") or "")
        if content.startswith(("[Action honesty", "[Todo reminder]", "[Self-diagnose]")):
            continue
        return content
    return ""


def wakeup_user_report(text: str) -> str:
    """User-visible status from a wake-up, without the instructions to the model."""
    raw = text or ""
    head = raw.split("\n", 1)[0].strip()
    for cut in (". Tell the user", ". Do not"):
        if cut in head:
            head = head.split(cut, 1)[0].rstrip() + "."
            break
    output = ""
    if "\nOutput:\n" in raw:
        output = raw.split("\nOutput:\n", 1)[1].strip()
    if output == "(no output)":
        output = ""
    try:
        from core.runtime.test_run_signals import is_test_log_dump

        if output and is_test_log_dump(output):
            output = ""
    except Exception:
        pass
    if len(output) > 1200:
        output = output[:1199] + "…"
    if output:
        return f"{head}\n\n{output}"
    return head


def visible_background_final(final_text: str | None, messages: list[Any] | None) -> str:
    """Hide a start note. Fill an empty wake-up from the task output."""
    text = final_text or ""
    if is_background_start_note(text):
        text = ""
    user = _latest_user_text(messages)
    if is_agent_task_wakeup(user) and (not text.strip() or text.startswith("Фоновых задач нет")):
        report = wakeup_user_report(user)
        if report.strip():
            return report
    return text


def format_agent_task_block() -> str:
    """Always-on reminder: one-shot jobs are not persistent processes."""
    return (
        "## Background tasks\n"
        "A finite shell or media job is `run_terminal_command` with `background=true`. "
        "You receive `task_…` at once and a "
        "later wake-up that already contains the output. Do not poll `list_agent_tasks` "
        'while it runs, and do not paste the "Background task started" note into the '
        "chat. When the wake-up arrives, tell the user the result in your own words.\n"
        "Stop that job with `stop_agent_task` and its id. Do not `pkill` it.\n"
        "`list_agent_tasks` is only those jobs in this chat. A server that must stay up "
        "is `start_background_process` and `list_background_processes`, not "
        "`list_agent_tasks`."
    )


def stop_idle_task_lookup(state: dict[str, Any], tool_calls: list[dict[str, Any]]) -> str | None:
    """Final text when the model polls list_agent_tasks after the list is idle.

    Returns None if the calls should run. A wake-up turn already carries the
    new output, so an older idle list must not replace that report.
    """
    if is_agent_task_wakeup(_latest_user_text(state.get("messages"))):
        return None
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
        "Tell the user the result in your own words. "
        "Do not run this same command again if it succeeded.\n\n"
        f"Command: {task.command}\n\n"
        f"Output:\n{body}"
    )


def started_task_message(task: AgentBackgroundTask) -> str:
    return f"Background task started: id={task.task_id} — {task.description}. Running in this chat."


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
        seen = {task.task_id for task in rows}
        for task in _load_finished(profile, conversation_id):
            if task.task_id not in seen:
                rows.append(task)
                seen.add(task.task_id)
        rows.sort(key=lambda task: task.started_at, reverse=True)
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

    def snapshot(self, *, profile: str, conversation_id: str) -> list[dict[str, Any]]:
        """Rows for the Studio task strip. Running tasks, plus ones just finished."""
        now = time.time()
        rows: list[dict[str, Any]] = []
        for task in self.list_for(profile=profile, conversation_id=conversation_id):
            if (
                not task.is_running()
                and task.finished_at is not None
                and now - task.finished_at > 180
            ):
                continue
            rows.append(task_public_row(task))
        return rows

    async def _drain(
        self,
        task: AgentBackgroundTask,
        stream: asyncio.StreamReader | None,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.readline()
            if not chunk:
                return
            task.output = _clip_output(task.output + chunk.decode("utf-8", errors="replace"))
            self._maybe_progress(task)

    async def _watch(self, task: AgentBackgroundTask, process: asyncio.subprocess.Process) -> None:
        try:
            await asyncio.gather(
                self._drain(task, process.stdout),
                self._drain(task, process.stderr),
            )
            if process.returncode is None:
                await process.wait()
            task.exit_code = int(process.returncode if process.returncode is not None else -1)
        except Exception as exc:
            logger.warning("background task %s watcher failed: %s", task.task_id, exc)
            task.exit_code = -1
            if not (task.output or "").strip():
                task.output = str(exc)
        task.finished_at = time.time()
        task.output = _finalize_live_output(task.output)
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
        _save_finished(task)
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

    def _maybe_progress(self, task: AgentBackgroundTask, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - task._last_progress_at < 0.4:
            return
        task._last_progress_at = now
        self._emit_task(task, "progress")

    def _emit_task(self, task: AgentBackgroundTask, phase: str) -> None:
        try:
            from core.agent_events import (
                AgentTaskFinishedEvent,
                AgentTaskProgressEvent,
                AgentTaskStartedEvent,
            )
        except Exception:
            return
        tail = _public_output_tail(task.output)
        if phase == "started":
            event = AgentTaskStartedEvent(
                task_id=task.task_id,
                description=task.description,
                status="running",
                command=task.command,
            )
        elif phase == "progress":
            event = AgentTaskProgressEvent(
                task_id=task.task_id,
                description=task.description,
                status=task.status or "running",
                command=task.command,
                output_tail=tail,
            )
        else:
            event = AgentTaskFinishedEvent(
                task_id=task.task_id,
                description=task.description,
                status=task.status,
                command=task.command,
                exit_code=task.exit_code,
                output_tail=tail,
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


_STORE_LOCK = threading.Lock()
_STORE_KEEP = 12


def _store_path(profile: str):
    try:
        from core.profile.names import ProfileNameError, profile_dir_for_name

        return profile_dir_for_name(profile) / "data" / "agent_tasks.json"
    except (ProfileNameError, OSError, RuntimeError, ValueError):
        return None


def _task_from_record(raw: dict[str, Any]) -> AgentBackgroundTask | None:
    task_id = str(raw.get("task_id") or "").strip()
    if not task_id:
        return None
    try:
        started = float(raw.get("started_at") or 0)
    except (TypeError, ValueError):
        started = 0.0
    finished = raw.get("finished_at")
    try:
        finished_at = float(finished) if finished is not None else None
    except (TypeError, ValueError):
        finished_at = None
    exit_code = raw.get("exit_code")
    try:
        code = int(exit_code) if exit_code is not None else None
    except (TypeError, ValueError):
        code = None
    return AgentBackgroundTask(
        task_id=task_id,
        description=str(raw.get("description") or ""),
        command=str(raw.get("command") or ""),
        profile=str(raw.get("profile") or ""),
        conversation_id=str(raw.get("conversation_id") or ""),
        status=str(raw.get("status") or "completed"),
        exit_code=code,
        output=str(raw.get("output") or ""),
        started_at=started,
        finished_at=finished_at,
    )


def _load_finished(profile: str, conversation_id: str) -> list[AgentBackgroundTask]:
    path = _store_path(profile)
    if path is None or not path.is_file():
        return []
    conv = (conversation_id or "").strip()
    try:
        with _STORE_LOCK:
            payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    rows = payload.get(conv) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    tasks: list[AgentBackgroundTask] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        task = _task_from_record(raw)
        if task is not None and not task.is_running():
            tasks.append(task)
    return tasks


def _save_finished(task: AgentBackgroundTask) -> None:
    if task.is_running():
        return
    path = _store_path(task.profile)
    if path is None:
        return
    record = {
        "task_id": task.task_id,
        "description": task.description,
        "command": (task.command or "")[:500],
        "profile": task.profile,
        "conversation_id": task.conversation_id,
        "status": task.status,
        "exit_code": task.exit_code,
        "output": _public_output_tail(task.output)[:4000],
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }
    conv = (task.conversation_id or "").strip() or "default"
    try:
        with _STORE_LOCK:
            payload: dict[str, Any] = {}
            if path.is_file():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        payload = loaded
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    payload = {}
            rows = [row for row in payload.get(conv) or [] if isinstance(row, dict)]
            rows = [row for row in rows if str(row.get("task_id") or "") != task.task_id]
            rows.insert(0, record)
            payload[conv] = rows[:_STORE_KEEP]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except OSError:
        logger.debug("agent task persist failed", exc_info=True)


def _short_command(command: str) -> str:
    text = " ".join((command or "").split())
    return text[:80] or "command"


_OUTPUT_CAP = 120_000
_OUTPUT_TAIL = 12_000


def task_public_row(task: AgentBackgroundTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "description": task.description,
        "command": task.command,
        "status": task.status,
        "exit_code": task.exit_code,
        "output": _public_output_tail(task.output),
        "age_seconds": task.age_seconds(),
    }


def _clip_output(text: str) -> str:
    if len(text) <= _OUTPUT_CAP:
        return text
    return text[-_OUTPUT_CAP:]


def _public_output_tail(text: str) -> str:
    raw = text or ""
    tail = raw[-_OUTPUT_TAIL:]
    try:
        from core.workspace import sanitize_paths_in_text

        return sanitize_paths_in_text(tail)
    except Exception:
        return tail


def _finalize_live_output(text: str) -> str:
    from core.memory.tool_content import truncate_terminal_output

    return truncate_terminal_output(_sanitize_all(text))


def _sanitize_all(text: str) -> str:
    try:
        from core.workspace import sanitize_paths_in_text

        return sanitize_paths_in_text(text or "")
    except Exception:
        return text or ""


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
