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

from core.runtime.step_budget import (
    _looks_like_error,
    _looks_like_progress,
    _tool_signature,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_S = 4.0
DEFAULT_IDLE_S = 90.0
DEFAULT_MAX_INTERVENTIONS = 3
DEFAULT_COOLDOWN_S = 45.0
DEFAULT_MIN_STEPS_BEFORE_STALL = 4


@dataclass(slots=True)
class SupervisorPolicy:
    enabled: bool = True
    poll_s: float = DEFAULT_POLL_S
    idle_s: float = DEFAULT_IDLE_S
    max_interventions: int = DEFAULT_MAX_INTERVENTIONS
    cooldown_s: float = DEFAULT_COOLDOWN_S
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
                float(
                    getattr(cfg, "subagent_supervisor_poll_s", DEFAULT_POLL_S)
                    or DEFAULT_POLL_S
                ),
            ),
            idle_s=max(
                5.0,
                float(
                    getattr(cfg, "subagent_supervisor_idle_s", DEFAULT_IDLE_S)
                    or DEFAULT_IDLE_S
                ),
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
        return self.kind in {"loop", "thrash", "hung", "stall"}


def _activity_tool_traces(handle: Any, *, lookback: int = 8) -> list[dict[str, Any]]:
    """Build tool-like traces from handle.activity_log."""
    log = list(getattr(handle, "activity_log", None) or [])
    traces: list[dict[str, Any]] = []
    for entry in log[-lookback * 2 :]:
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


def assess_handle(
    handle: Any,
    *,
    policy: SupervisorPolicy | None = None,
    now: float | None = None,
) -> Diagnosis:
    """Classify sub-agent health from live handle state."""
    pol = policy or SupervisorPolicy()
    status = getattr(handle, "status", None)
    status_val = (
        status.value if hasattr(status, "value") else str(status or "")
    ).lower()
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
    progress_count = sum(
        1 for t in traces if _looks_like_progress(str(t.get("result") or ""))
    )
    steps = int(getattr(handle, "steps_taken", 0) or 0)
    last_tool = str(getattr(handle, "last_tool", "") or "")
    activity = str(getattr(handle, "current_activity", "") or "")

    loop_hit = False
    if len(sigs) >= 3 and sigs[-1] and sigs[-1] == sigs[-2] == sigs[-3]:
        loop_hit = True
    elif len(sigs) >= 4 and sigs[-1] and sigs[-4:].count(sigs[-1]) >= 3:
        loop_hit = True

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

    if loop_hit:
        tool = last_tool or (traces[-1].get("name") if traces else "tool")
        return Diagnosis(
            kind="loop",
            severity="critical",
            summary=f"repeated identical tool calls ({tool})",
            guidance=(
                f"SUPERVISOR GUIDANCE: You are looping on the same tool call "
                f"({tool}). Stop repeating it. Change approach: try a different "
                f"tool, different arguments, read a related file, or summarize "
                f"what you already know and produce a partial result. Do not "
                f"call the same tool with the same arguments again."
            ),
            signals=signals,
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
            # Emit once per "exhausted" transition
            if self._last_kind.get(name) != "exhausted":
                self._last_kind[name] = "exhausted"
                self._emit(
                    handle,
                    diagnosis,
                    attempt=count,
                    message=(
                        f"Supervisor: max interventions ({count}) reached for "
                        f"`{name}` ({diagnosis.kind}); waiting for natural stop"
                    ),
                    exhausted=True,
                )
            return

        now = time.monotonic()
        last = float(self._last_intervene_at.get(name, 0.0))
        if last and (now - last) < self._policy.cooldown_s:
            return

        # Don't spam same kind every poll without cooldown already covered
        ok = await self._send_guidance(handle, diagnosis, attempt=count + 1)
        if not ok:
            return

        self._interventions[name] = count + 1
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
