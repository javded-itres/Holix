"""Step-budget health check and extension for main agent + sub-agents.

When a run reaches ``max_steps``, Holix does **not** always stop. It evaluates
whether the agent is still making relevant progress:

* **working + relevant** → grant extra steps (bounded by extension count / hard cap)
* **hung / looping / no signal** → stop (caller finalizes / fails the job)

This mirrors wait-timeout extension for sub-agents (activity-based), but applies
to the *reasoning step* budget.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Defaults (overridable via Settings / agent config)
DEFAULT_EXTEND_BY = 30
DEFAULT_MAX_EXTENSIONS = 10
DEFAULT_HARD_CAP = 0  # 0 → derive from base max_steps + extend_by * max_extensions
DEFAULT_LOOKBACK = 6

_ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "timeout",
    "timed out",
    "permission denied",
    "not found",
    "invalid",
    "❌",
    "⛔",
)

_PROGRESS_MARKERS = (
    "ok",
    "done",
    "success",
    "created",
    "updated",
    "written",
    "saved",
    "found",
    "result",
    "completed",
    "✅",
)


@dataclass(slots=True)
class StepBudgetPolicy:
    """Tunable limits for step-budget extension."""

    enabled: bool = True
    extend_by: int = DEFAULT_EXTEND_BY
    max_extensions: int = DEFAULT_MAX_EXTENSIONS
    hard_cap: int = DEFAULT_HARD_CAP  # absolute max_steps after extensions
    lookback: int = DEFAULT_LOOKBACK

    @classmethod
    def from_config(cls, cfg: Any | None = None) -> StepBudgetPolicy:
        if cfg is None:
            return cls()
        enabled = getattr(cfg, "max_steps_extend_enabled", True)
        if enabled is None:
            enabled = True
        return cls(
            enabled=bool(enabled),
            extend_by=max(
                1, int(getattr(cfg, "max_steps_extend_by", DEFAULT_EXTEND_BY) or DEFAULT_EXTEND_BY)
            ),
            max_extensions=max(
                0,
                int(
                    getattr(cfg, "max_steps_max_extensions", DEFAULT_MAX_EXTENSIONS)
                    or DEFAULT_MAX_EXTENSIONS
                ),
            ),
            hard_cap=max(0, int(getattr(cfg, "max_steps_hard_cap", DEFAULT_HARD_CAP) or 0)),
            lookback=max(
                3, int(getattr(cfg, "max_steps_lookback", DEFAULT_LOOKBACK) or DEFAULT_LOOKBACK)
            ),
        )


@dataclass(slots=True)
class StepBudgetDecision:
    """Outcome of a max-steps health check."""

    extend: bool
    reason: str
    status: str  # working | hung | stop | disabled | not_at_limit
    extra_steps: int = 0
    new_max_steps: int = 0
    extensions_used: int = 0
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def should_stop(self) -> bool:
        return not self.extend


def _norm_args(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (dict, list)):
        try:
            import json

            return json.dumps(raw, sort_keys=True, ensure_ascii=False)[:400]
        except Exception:
            return str(raw)[:400]
    text = str(raw).strip()
    return text[:400]


def _tool_signature(name: str, arguments: Any = None) -> str:
    return f"{(name or '').strip().lower()}::{_norm_args(arguments)}"


def identical_tool_loop(
    tool_calls_log: list[dict[str, Any]] | None,
    *,
    lookback: int = DEFAULT_LOOKBACK,
) -> bool:
    """True when the same tool+args signature repeats 3× in a row (or 3 of last 4)."""
    traces = collect_tool_traces(tool_calls_log=tool_calls_log, lookback=lookback)
    sigs = [str(t.get("signature") or "") for t in traces if t.get("signature")]
    return _signatures_loop(sigs)


def _signatures_loop(sigs: list[str]) -> bool:
    if len(sigs) >= 3 and sigs[-1] and sigs[-1] == sigs[-2] == sigs[-3]:
        return True
    if len(sigs) >= 4 and sigs[-1] and sigs[-4:].count(sigs[-1]) >= 3:
        return True
    return False


def _looks_like_error(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return True
    if low.startswith("❌") or low.startswith("⛔"):
        return True
    return any(m in low for m in _ERROR_MARKERS)


def _looks_like_progress(text: str) -> bool:
    low = (text or "").strip().lower()
    if len(low) < 8:
        return False
    if _looks_like_error(low):
        return False
    # Identical rewrite is not progress even though the summary says "Updated".
    if "no content changes" in low:
        return False
    if any(m in low for m in _PROGRESS_MARKERS):
        return True
    # Non-trivial payload without error markers counts as progress
    return len(low) >= 40


def _token_overlap(a: str, b: str) -> float:
    """Jaccard-ish overlap on alphanumeric tokens (relevance proxy)."""

    def toks(s: str) -> set[str]:
        return {t for t in re.findall(r"[a-zA-Zа-яА-Я0-9_]{3,}", (s or "").lower()) if t}

    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def collect_tool_traces(
    messages: list[dict[str, Any]] | None = None,
    *,
    tool_calls_log: list[dict[str, Any]] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    lookback: int = DEFAULT_LOOKBACK,
) -> list[dict[str, Any]]:
    """Build recent tool traces from messages and/or explicit logs."""
    traces: list[dict[str, Any]] = []

    if tool_calls_log:
        for item in tool_calls_log[-lookback:]:
            name = str(item.get("name") or item.get("tool_name") or "")
            args = item.get("arguments") or item.get("args") or ""
            result = str(item.get("result") or item.get("content") or item.get("details") or "")
            traces.append(
                {
                    "name": name,
                    "arguments": args,
                    "signature": _tool_signature(name, args),
                    "result": result,
                    "is_error": _looks_like_error(result) if result else False,
                }
            )

    if tool_results:
        for item in tool_results[-lookback:]:
            name = str(item.get("name") or item.get("tool_name") or "")
            content = str(item.get("content") or item.get("result") or "")
            args = item.get("arguments") or ""
            traces.append(
                {
                    "name": name,
                    "arguments": args,
                    "signature": _tool_signature(name, args),
                    "result": content,
                    "is_error": bool(item.get("is_error")) or _looks_like_error(content),
                }
            )

    # Reconstruct from conversation messages (assistant tool_calls + tool results)
    if messages and not traces:
        pending: dict[str, dict[str, Any]] = {}
        for msg in messages:
            role = msg.get("role")
            if role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") if isinstance(tc, dict) else None
                    if not isinstance(fn, dict):
                        fn = {}
                    tid = str(tc.get("id") or "")
                    name = str(fn.get("name") or tc.get("name") or "")
                    args = fn.get("arguments") if fn else tc.get("arguments")
                    pending[tid] = {
                        "name": name,
                        "arguments": args,
                        "signature": _tool_signature(name, args),
                        "result": "",
                        "is_error": False,
                    }
            elif role == "tool":
                tid = str(msg.get("tool_call_id") or "")
                content = str(msg.get("content") or "")
                entry = pending.pop(tid, None) or {
                    "name": str(msg.get("name") or ""),
                    "arguments": "",
                    "signature": _tool_signature(str(msg.get("name") or ""), ""),
                }
                entry["result"] = content
                entry["is_error"] = _looks_like_error(content)
                traces.append(entry)
        # leftover unexecuted calls still count as intent to work
        for entry in pending.values():
            traces.append(entry)

    return traces[-lookback:]


def evaluate_step_budget(
    *,
    step_count: int,
    max_steps: int,
    extensions_used: int = 0,
    pending_tool_calls: list[Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    tool_calls_log: list[dict[str, Any]] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    task: str = "",
    policy: StepBudgetPolicy | None = None,
    base_max_steps: int | None = None,
) -> StepBudgetDecision:
    """Decide whether to extend the step budget at/after the limit.

    Call when ``step_count >= max_steps`` (or about to stop for that reason).
    """
    pol = policy or StepBudgetPolicy()
    sc = int(step_count or 0)
    ms = int(max_steps or 0)
    ext_used = max(0, int(extensions_used or 0))
    base = int(base_max_steps or ms)

    if not pol.enabled:
        return StepBudgetDecision(
            extend=False,
            reason="step budget extension disabled",
            status="disabled",
            extensions_used=ext_used,
            new_max_steps=ms,
        )

    if ms <= 0 or sc < ms:
        return StepBudgetDecision(
            extend=False,
            reason="not at max_steps",
            status="not_at_limit",
            extensions_used=ext_used,
            new_max_steps=ms,
        )

    if ext_used >= pol.max_extensions:
        return StepBudgetDecision(
            extend=False,
            reason=f"extension limit reached ({ext_used}/{pol.max_extensions})",
            status="stop",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals={"extensions_used": ext_used},
        )

    hard = pol.hard_cap
    if hard <= 0:
        hard = base + pol.extend_by * pol.max_extensions
    hard = max(ms, hard)

    if ms >= hard:
        return StepBudgetDecision(
            extend=False,
            reason=f"hard cap reached ({ms}>={hard})",
            status="stop",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals={"hard_cap": hard},
        )

    pending = list(pending_tool_calls or [])
    traces = collect_tool_traces(
        messages,
        tool_calls_log=tool_calls_log,
        tool_results=tool_results,
        lookback=pol.lookback,
    )

    from core.runtime.introspect_signals import (
        introspect_loop,
        is_introspect_trace,
    )

    sigs = [t.get("signature") or "" for t in traces if t.get("signature")]
    unique_sigs = {s for s in sigs if s}
    error_count = sum(1 for t in traces if t.get("is_error"))
    progress_count = sum(
        1
        for t in traces
        if _looks_like_progress(str(t.get("result") or "")) and not is_introspect_trace(t)
    )
    recent_names = " ".join(str(t.get("name") or "") for t in traces)
    recent_results = " ".join(str(t.get("result") or "")[:200] for t in traces)
    relevance = (
        max(
            _token_overlap(task, recent_names),
            _token_overlap(task, recent_results),
        )
        if task
        else 0.0
    )

    loop_hit = _signatures_loop([str(s) for s in sigs])
    from core.runtime.test_run_signals import tests_already_green_loop

    green_repeat = tests_already_green_loop(traces)
    inspect_repeat = introspect_loop(traces)
    from core.runtime.write_signals import noop_write_loop

    noop_writes = noop_write_loop(traces)

    signals = {
        "pending_tools": len(pending),
        "traces": len(traces),
        "unique_sigs": len(unique_sigs),
        "error_count": error_count,
        "progress_count": progress_count,
        "loop_hit": loop_hit,
        "tests_green_repeat": green_repeat,
        "inspect_repeat": inspect_repeat,
        "noop_write_repeat": noop_writes,
        "relevance": round(relevance, 3),
        "extensions_used": ext_used,
        "hard_cap": hard,
    }

    # --- Hung: repeated identical work or pure error thrash ---
    if loop_hit:
        return StepBudgetDecision(
            extend=False,
            reason="hung: repeated identical tool calls (loop)",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if green_repeat:
        return StepBudgetDecision(
            extend=False,
            reason="tests already passed — re-running is not progress",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if inspect_repeat:
        return StepBudgetDecision(
            extend=False,
            reason="hung: inspect.getsource / python -c introspection is not progress",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if noop_writes:
        return StepBudgetDecision(
            extend=False,
            reason="hung: write_file with no content changes is not progress",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if len(traces) >= 3 and error_count == len(traces) and progress_count == 0:
        return StepBudgetDecision(
            extend=False,
            reason="hung: recent tools failed without progress",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    # --- Working: still has tools to run or recent successful relevant work ---
    working = False
    if pending:
        working = True
    elif progress_count > 0 and (len(unique_sigs) >= 2 or progress_count >= 2):
        working = True
    elif traces and progress_count > 0 and error_count < len(traces):
        working = True

    if not working:
        return StepBudgetDecision(
            extend=False,
            reason="no active work signal at max_steps (stop)",
            status="stop",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    # Relevance: require weak signal when we have a task string and tool names
    if task and recent_names and relevance < 0.02 and progress_count == 0:
        return StepBudgetDecision(
            extend=False,
            reason="work not relevant to the task",
            status="stop",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    extra = min(pol.extend_by, hard - ms)
    if extra <= 0:
        return StepBudgetDecision(
            extend=False,
            reason=f"no room under hard cap ({ms}/{hard})",
            status="stop",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    new_max = ms + extra
    return StepBudgetDecision(
        extend=True,
        reason=(f"working with relevant progress; +{extra} steps ({sc}/{ms} → max {new_max})"),
        status="working",
        extra_steps=extra,
        new_max_steps=new_max,
        extensions_used=ext_used + 1,
        signals=signals,
    )


def policy_from_agent(agent: Any | None) -> StepBudgetPolicy:
    cfg = getattr(agent, "config", None) if agent is not None else None
    return StepBudgetPolicy.from_config(cfg)


def apply_decision_to_state(
    state: dict[str, Any],
    decision: StepBudgetDecision,
) -> dict[str, Any]:
    """Return partial graph state updates when extending."""
    if not decision.extend:
        return {}
    return {
        "max_steps": int(decision.new_max_steps),
        "step_budget_extensions": int(decision.extensions_used),
    }


def maybe_extend_for_graph_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    agent: Any | None = None,
    task: str = "",
) -> dict[str, Any]:
    """If result is at max_steps with pending tools, maybe bump max_steps on result."""
    step_count = int(result.get("step_count", state.get("step_count", 0)) or 0)
    max_steps = int(result.get("max_steps", state.get("max_steps", 0)) or 0)
    if max_steps <= 0:
        max_steps = int(state.get("max_steps", 0) or 0)
    if step_count < max_steps:
        return result
    if result.get("is_final"):
        return result

    pending = result.get("tool_calls") or state.get("tool_calls") or []
    messages = result.get("messages") or state.get("messages") or []
    tool_results = result.get("tool_results") or state.get("tool_results") or []
    extensions_used = int(
        result.get("step_budget_extensions", state.get("step_budget_extensions", 0)) or 0
    )
    base_max = int(state.get("base_max_steps") or state.get("max_steps") or max_steps)
    policy = policy_from_agent(agent)
    decision = evaluate_step_budget(
        step_count=step_count,
        max_steps=max_steps,
        extensions_used=extensions_used,
        pending_tool_calls=pending,
        messages=messages if isinstance(messages, list) else None,
        tool_results=tool_results if isinstance(tool_results, list) else None,
        task=task or str(state.get("user_input") or ""),
        policy=policy,
        base_max_steps=base_max,
    )
    if not decision.extend:
        logger.info(
            "step budget stop at %s/%s: %s (%s)",
            step_count,
            max_steps,
            decision.status,
            decision.reason,
        )
        return result

    logger.info(
        "step budget extended: %s → %s (ext=%s) %s",
        max_steps,
        decision.new_max_steps,
        decision.extensions_used,
        decision.reason,
    )
    out = dict(result)
    out["max_steps"] = decision.new_max_steps
    out["step_budget_extensions"] = decision.extensions_used
    if "base_max_steps" not in state and "base_max_steps" not in out:
        out["base_max_steps"] = base_max
    # Notify UIs
    if agent is not None and hasattr(agent, "emit"):
        try:
            from core.agent_events import MaxStepsExtendedEvent, ThinkingEvent

            agent.emit(
                MaxStepsExtendedEvent(
                    max_steps=decision.new_max_steps,
                    previous_max_steps=max_steps,
                    extra_steps=decision.extra_steps,
                    extensions=decision.extensions_used,
                    reason=decision.reason,
                    conversation_id=str(state.get("conversation_id") or ""),
                )
            )
            agent.emit(
                ThinkingEvent(
                    message=(
                        f"Step budget extended by {decision.extra_steps} "
                        f"(now max {decision.new_max_steps}): still working"
                    ),
                    conversation_id=str(state.get("conversation_id") or ""),
                )
            )
        except Exception:
            logger.debug("failed to emit step budget events", exc_info=True)
    return out
