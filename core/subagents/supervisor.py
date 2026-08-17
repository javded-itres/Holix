"""Runtime Subagent Supervisor — watch jobs, diagnose stalls, inject guidance.

MVP: asyncio background loop attached to ``SubAgentManager``. Detects loop /
thrash / hang / stall using activity logs and step-budget heuristics, then
sends a ``guidance`` message to the **same** sub-agent so its next reasoning
step can course-correct.

See ``docs/plans/SUBAGENT_SUPERVISOR_PLAN.md``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.runtime.introspect_signals import introspect_loop
from core.runtime.step_budget import (
    _looks_like_error,
    _looks_like_progress,
    _signatures_loop,
    _tool_signature,
)
from core.runtime.test_run_signals import tests_already_green_loop
from core.runtime.write_signals import noop_write_loop

logger = logging.getLogger(__name__)

DEFAULT_POLL_S = 4.0
DEFAULT_IDLE_S = 90.0
DEFAULT_MAX_INTERVENTIONS = 3
DEFAULT_COOLDOWN_S = 45.0
DEFAULT_LOOP_COOLDOWN_S = 8.0
DEFAULT_MIN_STEPS_BEFORE_STALL = 4


@dataclass(slots=True)
class SupervisorPolicy:
    enabled: bool = True
    poll_s: float = DEFAULT_POLL_S
    idle_s: float = DEFAULT_IDLE_S
    max_interventions: int = DEFAULT_MAX_INTERVENTIONS
    cooldown_s: float = DEFAULT_COOLDOWN_S
    loop_cooldown_s: float = DEFAULT_LOOP_COOLDOWN_S
    min_steps_before_stall: int = DEFAULT_MIN_STEPS_BEFORE_STALL

    @classmethod
    def from_config(cls, cfg: Any | None) -> SupervisorPolicy:
        if cfg is None:
            return cls()
        enabled = getattr(cfg, "subagent_supervisor_enabled", True)
        if enabled is None:
            enabled = True
        return cls(
            enabled=bool(enabled),
            poll_s=max(
                1.0,
                float(getattr(cfg, "subagent_supervisor_poll_s", DEFAULT_POLL_S) or DEFAULT_POLL_S),
            ),
            idle_s=max(
                5.0,
                float(getattr(cfg, "subagent_supervisor_idle_s", DEFAULT_IDLE_S) or DEFAULT_IDLE_S),
            ),
            max_interventions=max(
                0,
                int(
                    getattr(
                        cfg,
                        "subagent_supervisor_max_interventions",
                        DEFAULT_MAX_INTERVENTIONS,
                    )
                    or DEFAULT_MAX_INTERVENTIONS
                ),
            ),
            cooldown_s=max(
                0.0,
                float(
                    getattr(cfg, "subagent_supervisor_cooldown_s", DEFAULT_COOLDOWN_S)
                    or DEFAULT_COOLDOWN_S
                ),
            ),
            loop_cooldown_s=max(
                0.0,
                float(
                    getattr(
                        cfg,
                        "subagent_supervisor_loop_cooldown_s",
                        DEFAULT_LOOP_COOLDOWN_S,
                    )
                    or DEFAULT_LOOP_COOLDOWN_S
                ),
            ),
            min_steps_before_stall=max(
                2,
                int(
                    getattr(
                        cfg,
                        "subagent_supervisor_min_steps_before_stall",
                        DEFAULT_MIN_STEPS_BEFORE_STALL,
                    )
                    or DEFAULT_MIN_STEPS_BEFORE_STALL
                ),
            ),
        )


@dataclass(slots=True)
class Diagnosis:
    kind: str  # ok | loop | thrash | hung | stall
    severity: str  # info | warning | critical
    summary: str
    guidance: str
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_intervention(self) -> bool:
        return self.kind in {"loop", "thrash", "hung", "stall", "launch", "tests_green"}


def _activity_tool_traces(handle: Any, *, lookback: int = 12) -> list[dict[str, Any]]:
    """Build tool-like traces from handle.activity_log."""
    log = list(getattr(handle, "activity_log", None) or [])
    traces: list[dict[str, Any]] = []
    # step + tool_start + tool_result ≈ 3 rows per call
    for entry in log[-lookback * 3 :]:
        kind = str(entry.get("kind") or "")
        tool = str(entry.get("tool_name") or "")
        details = str(entry.get("details") or "")
        if kind == "tool_start" and tool:
            traces.append(
                {
                    "name": tool,
                    "arguments": details,
                    "signature": _tool_signature(tool, details),
                    "result": "",
                    "is_error": False,
                }
            )
        elif kind == "tool_result" and traces:
            # Attach result to last matching tool if empty
            for t in reversed(traces):
                if t.get("name") == tool or not t.get("result"):
                    t["result"] = details
                    t["is_error"] = _looks_like_error(details)
                    if not t.get("signature"):
                        t["signature"] = _tool_signature(tool, t.get("arguments"))
                    break
            else:
                traces.append(
                    {
                        "name": tool,
                        "arguments": "",
                        "signature": _tool_signature(tool, ""),
                        "result": details,
                        "is_error": _looks_like_error(details),
                    }
                )
    return traces[-lookback:]


_SEARCH_TOOLS = frozenset({"grep", "glob", "list_directory"})


def _is_search_tool(name: str) -> bool:
    return str(name or "").strip().lower() in _SEARCH_TOOLS


def _extract_command(details: Any) -> str:
    text = str(details or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("command"):
                return str(obj.get("command") or "")
        except Exception:
            pass
    return text


def _looks_like_project_launch(details: Any) -> bool:
    try:
        from core.tools.terminal import _is_untracked_long_running_command
    except Exception:
        return False
    return bool(_is_untracked_long_running_command(_extract_command(details)))


def _looks_like_port_kill(details: Any) -> bool:
    blob = _extract_command(details).lower()
    if "kill" not in blob and "pkill" not in blob:
        return False
    return any(x in blob for x in ("lsof", "fuser", ":8000", ":3000", ":5173", "ti:"))


def _alternating_launch_kill(traces: list[dict[str, Any]]) -> bool:
    terms = [
        t
        for t in traces
        if str(t.get("name") or "").lower() in {"terminal", "run_terminal_command"}
    ]
    if len(terms) < 4:
        return False
    flags = []
    for t in terms[-4:]:
        args = t.get("arguments")
        flags.append(
            "launch"
            if _looks_like_project_launch(args)
            else ("kill" if _looks_like_port_kill(args) else "other")
        )
    return flags in (["launch", "kill", "launch", "kill"], ["kill", "launch", "kill", "launch"])


def _tool_path(details: Any) -> str:
    text = str(details or "").strip()
    if not text:
        return ""
    if text.startswith("{") or text.startswith("["):
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, dict):
                for key in ("path", "file", "target", "root"):
                    val = str(obj.get(key) or "").strip()
                    if val:
                        return val
        except Exception:
            pass
    import re

    hit = re.search(r'"path"\s*:\s*"([^"]+)"', text)
    return hit.group(1) if hit else ""


def _same_path_search_loop(traces: list[dict[str, Any]]) -> bool:
    """True when grep/glob keeps hitting the same file with tweaked patterns."""
    search = [t for t in traces if _is_search_tool(str(t.get("name") or ""))]
    if len(search) < 4:
        return False
    paths = [_tool_path(t.get("arguments")) for t in search[-6:]]
    paths = [p for p in paths if p]
    if len(paths) < 4:
        return False
    last = paths[-1]
    return paths.count(last) >= 4


def _prefer_tool(available: list[str], *candidates: str) -> str | None:
    have = {str(t).strip() for t in available if str(t).strip()}
    if not have:
        return candidates[0] if candidates else None
    for name in candidates:
        if name in have:
            return name
    return None


def build_loop_guidance(
    *,
    tool: str,
    details: str = "",
    available_tools: list[str] | None = None,
    attempt: int = 1,
    max_attempts: int = DEFAULT_MAX_INTERVENTIONS,
) -> str:
    """Concrete next-step guidance so the model can leave a tool loop."""
    tool_l = (tool or "tool").strip() or "tool"
    blob = (details or "").lower()
    available = [str(t).strip() for t in (available_tools or []) if str(t).strip()]
    read = _prefer_tool(available, "read_file", "grep", "glob", "list_directory")
    write = _prefer_tool(available, "write_file", "delete_file")
    search = _prefer_tool(available, "grep", "glob", "read_file")

    if tool_l in {"terminal", "run_terminal_command"}:
        if (
            "inspect." in blob
            or "import inspect" in blob
            or "python -c" in blob
            or "__init__" in blob
            or "protocol" in blob
        ):
            next_move = (
                f"stop inspect.getsource / python -c on libraries. "
                f"You already have enough API surface. Next call must be "
                f"{write or 'write_file'} for the project files "
                f"(or {read or 'read_file'} a local .py you will edit) — "
                f"do not introspect another method"
            )
        elif _looks_like_project_launch(details) or any(
            x in blob for x in ("uvicorn", "gunicorn", "npm run dev", "fastapi run", ".main")
        ):
            bg = _prefer_tool(
                available,
                "start_background_process",
                "run_project",
                "check_background_process",
            )
            next_move = (
                f"stop launching the server via terminal. Use "
                f"{bg or 'start_background_process'} with the same command "
                f"(then check_background_process). Do not use `&`, nohup, or "
                f"python -m *.main in terminal"
            )
        elif any(x in blob for x in ("pip install",)):
            next_move = (
                f"stop re-running that command; {read or 'read_file'} the project "
                "files you already have and continue implementation"
            )
        else:
            next_move = (
                f"do not re-run this terminal command; {read or 'read_file'} / "
                f"{search or 'grep'} the relevant source, then "
                f"{write or 'write_file'} or finish with what you know"
            )
    elif tool_l == "read_file":
        next_move = (
            f"you already have this file; next {write or 'write_file'} a change "
            f"or {search or 'grep'} a different path — do not re-read the same file"
        )
    elif tool_l in {"grep", "glob"}:
        next_move = (
            f"open one hit with {read or 'read_file'}, then {write or 'write_file'} "
            "or answer; do not repeat the same search"
        )
    elif tool_l == "write_file":
        if "no content changes" in blob:
            next_move = (
                "STOP rewriting files that already match disk. "
                "Do not call write_file again on those paths. "
                "Run pytest once if you have not, then the next message must be "
                "the final answer with NO tool calls so the process can continue"
            )
        else:
            next_move = (
                f"stop rewriting the same file; {read or 'read_file'} to verify or "
                "move to the next deliverable / final answer"
            )
    elif tool_l in {"web_search", "web_fetch"}:
        next_move = (
            "use a different query/URL once, then write the answer from evidence "
            "you already have — do not repeat the same fetch/search"
        )
    else:
        next_move = (
            f"call a different tool or different arguments "
            f"({read or 'read_file'} / {write or 'write_file'}), "
            "or produce a partial final result"
        )

    tools_line = ""
    if available:
        tools_line = " Allowed tools: " + ", ".join(available) + "."

    last = attempt >= max(1, int(max_attempts or 1))
    if last and _is_search_tool(tool_l):
        warning = (
            " Stop refining the same search — open the file with "
            f"{read or 'read_file'} now. Search tweaks are not a failure, "
            "but they will not find new facts."
        )
    elif last:
        warning = (
            " LAST CHANCE: if you repeat the same call, the job will be stopped with status loop."
        )
    else:
        warning = f" Attempt {attempt}/{max_attempts}."
    return (
        f"SUPERVISOR GUIDANCE: You are looping on `{tool_l}`. "
        f"Do NOT call `{tool_l}` with the same arguments again. "
        f"Required next move: {next_move}.{tools_line}"
        f"{warning}"
    )


def assess_handle(
    handle: Any,
    *,
    policy: SupervisorPolicy | None = None,
    now: float | None = None,
) -> Diagnosis:
    """Classify sub-agent health from live handle state."""
    pol = policy or SupervisorPolicy()
    status = getattr(handle, "status", None)
    status_val = (status.value if hasattr(status, "value") else str(status or "")).lower()
    is_running = bool(getattr(handle, "is_running", False)) or status_val == "running"
    if not is_running:
        return Diagnosis(
            kind="ok",
            severity="info",
            summary="not running",
            guidance="",
            signals={"status": status_val},
        )

    traces = _activity_tool_traces(handle)
    sigs = [str(t.get("signature") or "") for t in traces if t.get("signature")]
    error_count = sum(1 for t in traces if t.get("is_error"))
    progress_count = sum(1 for t in traces if _looks_like_progress(str(t.get("result") or "")))
    steps = int(getattr(handle, "steps_taken", 0) or 0)
    last_tool = str(getattr(handle, "last_tool", "") or "")
    activity = str(getattr(handle, "current_activity", "") or "")

    path_loop = _same_path_search_loop(traces)
    inspect_hit = introspect_loop(traces)
    noop_write_hit = noop_write_loop(traces)
    loop_hit = _signatures_loop(sigs) or path_loop or inspect_hit or noop_write_hit
    last_args = str((traces[-1] or {}).get("arguments") or "") if traces else ""
    launch_hit = str(last_tool).lower() in {"terminal", "run_terminal_command"} and (
        _looks_like_project_launch(last_args) or _alternating_launch_kill(traces)
    )

    actively = True
    if hasattr(handle, "is_actively_working"):
        try:
            actively = bool(handle.is_actively_working(max_idle_s=pol.idle_s))
        except Exception:
            actively = True

    signals = {
        "steps": steps,
        "traces": len(traces),
        "error_count": error_count,
        "progress_count": progress_count,
        "loop_hit": loop_hit,
        "actively_working": actively,
        "last_tool": last_tool,
        "activity": activity[:120],
    }

    if tests_already_green_loop(traces):
        available = list(getattr(getattr(handle, "config", None), "tools", None) or [])
        return Diagnosis(
            kind="tests_green",
            severity="warning",
            summary="tests already passed — finish so the process can continue",
            guidance=(
                "SUPERVISOR GUIDANCE: Automated tests already passed. "
                "Do NOT run pytest/grep on tests again. "
                "Your next message must be the final answer with NO tool calls "
                "so the Studio process can continue to the next node. "
                "Summarize what you fixed and stop."
            ),
            signals={
                **signals,
                "loop_tool": last_tool or "terminal",
                "loop_details": last_args[:240],
                "search_loop": True,
                "tests_green": True,
            },
        )

    if launch_hit:
        available = list(getattr(getattr(handle, "config", None), "tools", None) or [])
        bg = _prefer_tool(
            available,
            "start_background_process",
            "run_project",
            "check_background_process",
        )
        return Diagnosis(
            kind="launch",
            severity="warning",
            summary="project launch via terminal — use start_background_process",
            guidance=(
                "SUPERVISOR GUIDANCE: You are starting a long-running project/server "
                "via terminal. Stop that. Call "
                f"{bg or 'start_background_process'} with the same command "
                "(label the app), then check_background_process. "
                "Do not use `&`, nohup, python -m *.main, or uvicorn in terminal — "
                "those hang the tool and are not tracked."
            ),
            signals={
                **signals,
                "loop_tool": last_tool or "terminal",
                "loop_details": last_args[:240],
                "search_loop": False,
                "launch_via_terminal": True,
            },
        )

    if loop_hit:
        tool = last_tool or (traces[-1].get("name") if traces else "tool")
        details = str((traces[-1] or {}).get("arguments") or "") if traces else ""
        if noop_write_hit:
            details = str((traces[-1] or {}).get("result") or details)
        available = list(getattr(getattr(handle, "config", None), "tools", None) or [])
        search_only = _is_search_tool(str(tool)) or path_loop
        if noop_write_hit:
            summary = f"write_file no-op loop ({tool})"
        elif inspect_hit:
            summary = f"library introspection loop via terminal ({tool})"
        elif path_loop and not _signatures_loop(sigs):
            summary = f"repeated search on the same path ({tool})"
        else:
            summary = f"repeated identical tool calls ({tool})"
        return Diagnosis(
            kind="loop",
            severity="warn" if search_only else "critical",
            summary=summary,
            guidance=build_loop_guidance(
                tool=str(tool),
                details=details,
                available_tools=available,
                attempt=1,
                max_attempts=pol.max_interventions,
            ),
            signals={
                **signals,
                "loop_tool": str(tool),
                "loop_details": details[:240],
                "search_loop": search_only,
                "path_loop": path_loop,
                "inspect_loop": inspect_hit,
                "noop_write_loop": noop_write_hit,
            },
        )

    if len(traces) >= 3 and error_count == len(traces) and progress_count == 0:
        return Diagnosis(
            kind="thrash",
            severity="critical",
            summary="recent tools only return errors",
            guidance=(
                "SUPERVISOR GUIDANCE: Your last tool calls all failed. "
                "Diagnose the root error (permissions, missing path, bad args). "
                "Fix the underlying issue (correct path, create dir, simpler command) "
                "or report a clear blocker with the exact error — do not retry the "
                "same failing call."
            ),
            signals=signals,
        )

    if not actively:
        return Diagnosis(
            kind="hung",
            severity="critical",
            summary=f"no activity for >{pol.idle_s:.0f}s",
            guidance=(
                "SUPERVISOR GUIDANCE: You appear stalled (no recent progress). "
                "Either complete the current step with a concrete result or "
                "switch strategy. Avoid long silent waits; call a tool or write "
                "your final answer for the assigned task."
            ),
            signals=signals,
        )

    if (
        steps >= pol.min_steps_before_stall
        and progress_count == 0
        and len(traces) >= 2
        and error_count >= 1
    ):
        return Diagnosis(
            kind="stall",
            severity="warning",
            summary="steps advancing without useful progress",
            guidance=(
                "SUPERVISOR GUIDANCE: You are spending steps without useful progress. "
                "Narrow the task: pick one concrete deliverable, use a smaller "
                "tool sequence, and avoid exploratory retries. Prefer write/fix "
                "over re-reading the same inputs."
            ),
            signals=signals,
        )

    return Diagnosis(
        kind="ok",
        severity="info",
        summary="healthy / progressing",
        guidance="",
        signals=signals,
    )


class SubagentSupervisor:
    """Background watcher that nudges stuck sub-agents with guidance."""

    def __init__(
        self,
        manager: Any,
        *,
        policy: SupervisorPolicy | None = None,
    ) -> None:
        self._manager = manager
        self._policy = policy or SupervisorPolicy()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        # job name -> stats
        self._interventions: dict[str, int] = {}
        self._last_intervene_at: dict[str, float] = {}
        self._last_kind: dict[str, str] = {}

    @property
    def policy(self) -> SupervisorPolicy:
        return self._policy

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def ensure_running(self) -> None:
        if not self._policy.enabled:
            return
        if self.is_running:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("supervisor: no running event loop")
            return
        self._stop = asyncio.Event()
        self._task = loop.create_task(self._watch_loop(), name="subagent-supervisor")
        logger.info(
            "SubagentSupervisor started (poll=%.1fs idle=%.0fs max_iv=%d)",
            self._policy.poll_s,
            self._policy.idle_s,
            self._policy.max_interventions,
        )

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("supervisor stop error", exc_info=True)

    def reset_job(self, name: str) -> None:
        self._interventions.pop(name, None)
        self._last_intervene_at.pop(name, None)
        self._last_kind.pop(name, None)

    async def _watch_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("SubagentSupervisor tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._policy.poll_s)
                    break
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.debug("SubagentSupervisor cancelled")
        finally:
            logger.info("SubagentSupervisor stopped")

    async def _tick(self) -> None:
        handles = getattr(self._manager, "_handles", None) or {}
        running = [
            h
            for h in handles.values()
            if getattr(h, "is_running", False)
            or str(getattr(getattr(h, "status", None), "value", "")).lower() == "running"
        ]
        if not running:
            return
        for handle in running:
            await self._maybe_intervene(handle)

    async def _maybe_intervene(self, handle: Any) -> None:
        name = str(getattr(handle, "name", "") or "")
        if not name:
            return
        diagnosis = assess_handle(handle, policy=self._policy)
        if not diagnosis.needs_intervention:
            return

        count = int(self._interventions.get(name, 0))
        if count >= self._policy.max_interventions:
            search_loop = (
                bool(diagnosis.signals.get("search_loop"))
                or _is_search_tool(
                    str(diagnosis.signals.get("loop_tool") or handle.last_tool or "")
                )
                or diagnosis.kind == "launch"
                or diagnosis.kind == "tests_green"
                or bool(diagnosis.signals.get("launch_via_terminal"))
                or bool(diagnosis.signals.get("tests_green"))
            )
            if self._last_kind.get(name) != "exhausted":
                self._last_kind[name] = "exhausted"
                fatal = diagnosis.kind == "loop" and not search_loop
                self._emit(
                    handle,
                    diagnosis,
                    attempt=count,
                    message=(
                        f"Supervisor: max interventions ({count}) reached for "
                        f"`{name}` ({diagnosis.kind}); stopping with status loop"
                        if fatal
                        else f"Supervisor: max interventions ({count}) reached for "
                        f"`{name}` ({diagnosis.kind}); "
                        + (
                            "search tweaks are not a failure — waiting for a read/write"
                            if search_loop
                            else "waiting for natural stop"
                        )
                    ),
                    exhausted=True,
                )
                if fatal:
                    await self._stop_loop(handle, diagnosis)
            return

        now = time.monotonic()
        last = float(self._last_intervene_at.get(name, 0.0))
        cooldown = (
            self._policy.loop_cooldown_s
            if diagnosis.kind in {"loop", "launch", "tests_green"}
            else self._policy.cooldown_s
        )
        if last and (now - last) < cooldown:
            return

        attempt = count + 1
        if diagnosis.kind == "loop":
            diagnosis = Diagnosis(
                kind=diagnosis.kind,
                severity=diagnosis.severity,
                summary=diagnosis.summary,
                guidance=build_loop_guidance(
                    tool=str(diagnosis.signals.get("loop_tool") or handle.last_tool or "tool"),
                    details=str(diagnosis.signals.get("loop_details") or ""),
                    available_tools=list(
                        getattr(getattr(handle, "config", None), "tools", None) or []
                    ),
                    attempt=attempt,
                    max_attempts=self._policy.max_interventions,
                ),
                signals=diagnosis.signals,
            )

        ok = await self._send_guidance(handle, diagnosis, attempt=attempt)
        if not ok:
            return

        self._interventions[name] = attempt
        self._last_intervene_at[name] = now
        self._last_kind[name] = diagnosis.kind
        self._emit(
            handle,
            diagnosis,
            attempt=count + 1,
            message=diagnosis.guidance,
            exhausted=False,
        )
        # Surface in activity log for Studio
        try:
            handle.record_activity(
                "supervisor_guidance",
                f"Supervisor ({diagnosis.kind}): {diagnosis.summary}",
                details=diagnosis.guidance[:300],
                steps_taken=int(getattr(handle, "steps_taken", 0) or 0),
            )
        except Exception:
            pass
        notify = getattr(self._manager, "notify_progress", None)
        if callable(notify):
            try:
                notify(name, force=True)
            except Exception:
                pass

    async def _send_guidance(
        self,
        handle: Any,
        diagnosis: Diagnosis,
        *,
        attempt: int,
    ) -> bool:
        from core.subagents.communication import AgentMessage

        name = handle.name
        msg = AgentMessage(
            from_agent="supervisor",
            to_agent=name,
            msg_type="guidance",
            content=diagnosis.guidance,
            metadata={
                "kind": diagnosis.kind,
                "severity": diagnosis.severity,
                "summary": diagnosis.summary,
                "attempt": attempt,
                "signals": diagnosis.signals,
            },
        )
        bus = getattr(self._manager, "_comm_bus", None)
        if bus is None:
            logger.warning("supervisor: no communication bus")
            return False

        mode = getattr(handle.config, "process_mode", None)
        mode_val = mode.value if hasattr(mode, "value") else str(mode or "async")
        try:
            if str(mode_val).lower() == "process":
                bus.process_bus.send_to_sub_agent(msg)
            else:
                await bus.async_bus.send(msg)
        except Exception:
            logger.exception("supervisor: failed to send guidance to %s", name)
            return False

        logger.info(
            "Supervisor guidance → %s kind=%s attempt=%d: %s",
            name,
            diagnosis.kind,
            attempt,
            diagnosis.summary,
        )
        return True

    async def _stop_loop(self, handle: Any, diagnosis: Diagnosis) -> None:
        """Stop a looping job with status=loop (not cancelled)."""
        from core.subagents.base import SubAgentResult, SubAgentStatus

        name = str(getattr(handle, "name", "") or "")
        error = (
            "loop: repeated identical tool calls after "
            f"{self._policy.max_interventions} supervisor interventions"
        )
        handle.forced_status = SubAgentStatus.LOOP
        handle.result = SubAgentResult(
            name=name,
            success=False,
            error=error,
            steps_taken=int(getattr(handle, "steps_taken", 0) or 0),
            duration_ms=float(getattr(handle, "elapsed_ms", 0) or 0),
        )
        try:
            handle.record_activity(
                "status",
                "loop",
                details=error,
                steps_taken=int(getattr(handle, "steps_taken", 0) or 0),
            )
        except Exception:
            pass
        terminate = getattr(self._manager, "terminate", None)
        if callable(terminate):
            try:
                await terminate(name)
            except Exception:
                logger.exception("supervisor: failed to stop looping job %s", name)
        logger.warning("Supervisor stopped %s with status=loop (%s)", name, diagnosis.summary)

    def _emit(
        self,
        handle: Any,
        diagnosis: Diagnosis,
        *,
        attempt: int,
        message: str,
        exhausted: bool,
    ) -> None:
        try:
            from core.agent_events import SubAgentSupervisorEvent

            emit = getattr(self._manager, "_emit_agent_event", None)
            if not callable(emit):
                parent = getattr(self._manager, "_parent", None)
                emit_fn = getattr(parent, "emit", None) if parent else None
                if callable(emit_fn):
                    emit = lambda e: emit_fn(e)  # noqa: E731
                else:
                    return
            emit(
                SubAgentSupervisorEvent(
                    name=str(handle.name),
                    agent_type=str(
                        getattr(handle, "agent_type", "")
                        or getattr(handle.config, "agent_type", "")
                        or ""
                    ),
                    kind=diagnosis.kind,
                    severity=diagnosis.severity,
                    attempt=attempt,
                    max_interventions=self._policy.max_interventions,
                    summary=diagnosis.summary,
                    message=(message or "")[:2000],
                    exhausted=exhausted,
                )
            )
        except Exception:
            logger.debug("supervisor emit failed", exc_info=True)


async def drain_guidance_messages(
    bus_receive,
    agent_name: str,
    *,
    max_messages: int = 8,
) -> list[str]:
    """Drain guidance messages for a sub-agent (async bus receive coroutine).

    ``bus_receive`` is ``async_bus.receive`` bound method.
    """
    texts: list[str] = []
    for _ in range(max_messages):
        msg = await bus_receive(agent_name, timeout=0.001)
        if msg is None:
            break
        if getattr(msg, "msg_type", "") in {"guidance", "revise"}:
            content = str(getattr(msg, "content", "") or "").strip()
            if content:
                texts.append(content)
    return texts


def format_guidance_system_message(texts: list[str]) -> str:
    if not texts:
        return ""
    body = "\n\n".join(texts)
    return (
        "### Runtime supervisor intervention\n"
        "The parent runtime detected a problem with your recent work and sent "
        "the following guidance. Follow it on this step:\n\n"
        f"{body}"
    )
