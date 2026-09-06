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
DEFAULT_USER_MAX_EXTENSIONS = 10
DEFAULT_HARD_CAP = 0  # 0 → derive from base max_steps + extend_by * max_extensions
DEFAULT_LOOKBACK = 6

# Whole-token / line failures — not "TimeoutError:" inside a source dump.
_ERROR_TOKEN_RE = re.compile(
    r"(?i)(?:^|[\s])(?:error|exception|failed|failure)\s*:|"
    r"traceback \(most recent call last\)|"
    r"permission denied|"
    r"timed out|"
    r"❌|⛔"
)

_WEB_ONLY_TOOLS = frozenset({"fetch_url", "web_fetch", "web_search"})

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
    user_max_extensions: int = DEFAULT_USER_MAX_EXTENSIONS
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
            user_max_extensions=max(
                0,
                int(
                    getattr(cfg, "max_steps_user_max_extensions", DEFAULT_USER_MAX_EXTENSIONS)
                    or DEFAULT_USER_MAX_EXTENSIONS
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
    user_extensions_used: int = 0
    from_user: bool = False
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


def web_search_only_loop(traces: list[dict[str, Any]], *, min_calls: int = 4) -> bool:
    """True when recent tools are only public web fetch/search (a crawl, not a write)."""
    if len(traces) < min_calls:
        return False
    names = [str(t.get("name") or "").strip().lower() for t in traces]
    names = [n for n in names if n]
    if len(names) < min_calls:
        return False
    return all(n in _WEB_ONLY_TOOLS for n in names)


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
    raw = (text or "").strip()
    if not raw:
        return True
    if raw.startswith("❌") or raw.startswith("⛔"):
        return True
    return bool(_ERROR_TOKEN_RE.search(raw))


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
    from core.runtime.test_run_signals import tests_failing_without_writes
    from core.runtime.write_signals import no_write_implementation_loop, noop_write_loop

    noop_writes = noop_write_loop(traces)
    red_tests = tests_failing_without_writes(traces)
    read_only = no_write_implementation_loop(traces, task)
    web_only = web_search_only_loop(traces)

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
        "tests_red_no_write": red_tests,
        "read_only_impl": read_only,
        "web_search_only": web_only,
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

    if red_tests:
        return StepBudgetDecision(
            extend=False,
            reason="hung: tests keep failing and no file was written",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if read_only:
        return StepBudgetDecision(
            extend=False,
            reason="hung: implement/fix task only reads or re-runs tests (no write_file)",
            status="hung",
            extensions_used=ext_used,
            new_max_steps=ms,
            signals=signals,
        )

    if web_only:
        return StepBudgetDecision(
            extend=False,
            reason="hung: only web_search/fetch_url — answer from this session, do not crawl further",
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


def _is_terminal_final(text: str | None) -> bool:
    from core.presenters.final_content import is_aborted_final_response, is_usable_user_final

    raw = (text or "").strip()
    if not raw:
        return False
    if is_aborted_final_response(raw):
        return True
    return is_usable_user_final(raw)


def _clear_dump_final(out: dict[str, Any]) -> dict[str, Any]:
    from core.presenters.final_content import is_usable_user_final

    if is_usable_user_final(str(out.get("final_response") or "")):
        return out
    out["is_final"] = False
    out["final_response"] = ""
    out["needs_refinement"] = False
    return out


def _append_continue_nudge(
    out: dict[str, Any],
    state: dict[str, Any],
    *,
    extra: int,
    new_max: int,
) -> None:
    messages = out.get("messages")
    if not isinstance(messages, list):
        raw = state.get("messages") or []
        messages = list(raw) if isinstance(raw, list) else []
    messages.append(
        {
            "role": "user",
            "content": (
                f"[Holix] Step budget extended by {extra} (now max {new_max}). "
                "Continue the task. Do not dump source code or diffs as the final answer; "
                "write a short status instead."
            ),
        }
    )
    out["messages"] = messages


def _emit_extended(
    agent: Any | None,
    *,
    conversation_id: str,
    max_steps: int,
    previous_max_steps: int,
    extra_steps: int,
    extensions: int,
    reason: str,
) -> None:
    if agent is None or not hasattr(agent, "emit"):
        return
    try:
        from core.agent_events import MaxStepsExtendedEvent, ThinkingEvent

        agent.emit(
            MaxStepsExtendedEvent(
                max_steps=max_steps,
                previous_max_steps=previous_max_steps,
                extra_steps=extra_steps,
                extensions=extensions,
                reason=reason,
                conversation_id=conversation_id,
            )
        )
        agent.emit(
            ThinkingEvent(
                message=(
                    f"Step budget extended by {extra_steps} (now max {max_steps}): still working"
                ),
                conversation_id=conversation_id,
            )
        )
    except Exception:
        logger.debug("failed to emit step budget events", exc_info=True)


def apply_extension(
    state: dict[str, Any],
    result: dict[str, Any],
    decision: StepBudgetDecision,
    *,
    agent: Any | None = None,
    previous_max_steps: int,
) -> dict[str, Any]:
    """Apply an auto or user extension to graph/loop state."""
    out = dict(result)
    out["max_steps"] = int(decision.new_max_steps)
    if decision.from_user:
        out["step_budget_user_extensions"] = int(decision.user_extensions_used)
    else:
        out["step_budget_extensions"] = int(decision.extensions_used)
    base_max = int(state.get("base_max_steps") or state.get("max_steps") or previous_max_steps)
    if "base_max_steps" not in state and "base_max_steps" not in out:
        out["base_max_steps"] = base_max
    from core.presenters.final_content import is_usable_user_final

    raw_final = str(out.get("final_response") or "").strip()
    dump_final = bool(raw_final) and not is_usable_user_final(raw_final)
    _clear_dump_final(out)
    if dump_final or decision.from_user:
        _append_continue_nudge(
            out,
            state,
            extra=decision.extra_steps,
            new_max=decision.new_max_steps,
        )
    _emit_extended(
        agent,
        conversation_id=str(state.get("conversation_id") or result.get("conversation_id") or ""),
        max_steps=decision.new_max_steps,
        previous_max_steps=previous_max_steps,
        extra_steps=decision.extra_steps,
        extensions=(
            decision.user_extensions_used if decision.from_user else decision.extensions_used
        ),
        reason=decision.reason,
    )
    return out


def abort_at_step_limit(
    result: dict[str, Any],
    *,
    max_steps: int,
    locale: str = "ru",
) -> dict[str, Any]:
    from core.presenters.final_content import step_limit_aborted_message

    out = dict(result)
    out["is_final"] = True
    out["needs_refinement"] = False
    out["tool_calls"] = []
    out["final_response"] = step_limit_aborted_message(max_steps, locale=locale)
    return out


def maybe_extend_for_graph_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    agent: Any | None = None,
    task: str = "",
) -> dict[str, Any]:
    """If result is at max_steps, maybe bump max_steps when work is still healthy."""
    step_count = int(result.get("step_count", state.get("step_count", 0)) or 0)
    max_steps = int(result.get("max_steps", state.get("max_steps", 0)) or 0)
    if max_steps <= 0:
        max_steps = int(state.get("max_steps", 0) or 0)
    if step_count < max_steps:
        return result
    if result.get("is_final") and _is_terminal_final(str(result.get("final_response") or "")):
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
    return apply_extension(
        state,
        result,
        decision,
        agent=agent,
        previous_max_steps=max_steps,
    )


async def maybe_extend_or_ask(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    agent: Any | None = None,
    task: str = "",
) -> dict[str, Any]:
    """Auto-extend when healthy; otherwise pause the main agent for Continue/Abort."""
    extended = maybe_extend_for_graph_result(state, result, agent=agent, task=task)
    prev_max = int(result.get("max_steps", state.get("max_steps", 0)) or 0)
    new_max = int(extended.get("max_steps", prev_max) or 0)
    if new_max > prev_max:
        return extended

    step_count = int(extended.get("step_count", state.get("step_count", 0)) or 0)
    max_steps = int(extended.get("max_steps", state.get("max_steps", 0)) or 0)
    if max_steps <= 0 or step_count < max_steps:
        return extended
    if extended.get("is_final") and _is_terminal_final(str(extended.get("final_response") or "")):
        return extended

    from core.runtime.step_budget_pause import ask_continue_or_abort, can_ask_user

    policy = policy_from_agent(agent)
    user_used = int(
        extended.get(
            "step_budget_user_extensions",
            state.get("step_budget_user_extensions", 0),
        )
        or 0
    )
    conversation_id = str(extended.get("conversation_id") or state.get("conversation_id") or "")
    locale = _locale_from_agent(agent)
    if not can_ask_user(agent, conversation_id=conversation_id, user_used=user_used, policy=policy):
        return abort_at_step_limit(extended, max_steps=max_steps, locale=locale)

    choice = await ask_continue_or_abort(
        agent=agent,
        conversation_id=conversation_id,
        step_count=step_count,
        max_steps=max_steps,
        extra_steps=policy.extend_by,
        user_used=user_used,
        user_max=policy.user_max_extensions,
        reason=str(extended.get("step_budget_stop_reason") or ""),
        locale=locale,
    )
    if choice != "continue":
        return abort_at_step_limit(extended, max_steps=max_steps, locale=locale)

    extra = policy.extend_by
    decision = StepBudgetDecision(
        extend=True,
        reason=f"user continue; +{extra} steps ({step_count}/{max_steps} → max {max_steps + extra})",
        status="working",
        extra_steps=extra,
        new_max_steps=max_steps + extra,
        extensions_used=int(
            extended.get("step_budget_extensions", state.get("step_budget_extensions", 0)) or 0
        ),
        user_extensions_used=user_used + 1,
        from_user=True,
    )
    logger.info(
        "step budget user-continue: %s → %s (user_ext=%s)",
        max_steps,
        decision.new_max_steps,
        decision.user_extensions_used,
    )
    return apply_extension(
        state,
        extended,
        decision,
        agent=agent,
        previous_max_steps=max_steps,
    )


def _locale_from_agent(agent: Any | None) -> str:
    cfg = getattr(agent, "config", None) if agent is not None else None
    profile = getattr(cfg, "profile_name", None) if cfg is not None else None
    if not profile:
        return "ru"
    try:
        from core.i18n.locale import LocaleStore

        return str(LocaleStore(profile).get() or "ru")
    except Exception:
        return "ru"
