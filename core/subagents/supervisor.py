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
DEFAULT_IDLE_S = 300.0
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
        return self.kind in {
            "loop",
            "thrash",
            "hung",
            "stall",
            "launch",
            "tests_green",
            "empty_reply",
        }


def _activity_message(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("message") or "")
    return str(getattr(item, "message", "") or "")


def _activity_looks_empty(handle: Any) -> bool:
    """True when the runner just recorded an empty model reply."""
    log = getattr(handle, "activity_log", None) or []
    for item in reversed(list(log)[-8:]):
        low = _activity_message(item).lower()
        if "empty model reply" in low or (
            "empty llm" in low and ("retry" in low or "response" in low)
        ):
            return True
    return False


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


def _loop_target(details: Any) -> str:
    """Human-facing path / command / query from the looping tool call."""
    path = _tool_path(details)
    if path:
        return path
    text = str(details or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, dict):
                for key in ("command", "query", "pattern", "url"):
                    val = str(obj.get(key) or "").strip()
                    if val:
                        return val
        except Exception:
            pass
    cmd = _extract_command(details).strip()
    if cmd:
        return " ".join(cmd.split())[:240]
    return ""


def _result_excerpt(result: str, limit: int = 360) -> str:
    text = " ".join(str(result or "").split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _ui_locale(source: Any = None) -> str:
    """Studio / Holix UI locale for human-facing supervisor questions."""
    from core.i18n.locale import LocaleStore, normalize_locale

    profile = ""
    if isinstance(source, str):
        profile = source.strip()
    elif source is not None:
        parent = getattr(source, "_parent", None)
        cfg = getattr(parent, "config", None) if parent is not None else None
        if cfg is None:
            cfg = getattr(source, "config", None)
        raw = getattr(cfg, "profile_name", None) if cfg is not None else None
        if isinstance(raw, str):
            profile = raw.strip()
    if not profile:
        return "ru"
    try:
        return normalize_locale(LocaleStore(profile).get())
    except Exception:
        return "ru"


def format_human_loop_question(
    base: str,
    *,
    details: str = "",
    last_result: str = "",
    locale: str | None = None,
) -> str:
    """Question the human sees: what is stuck, which call, last result."""
    from core.i18n import t

    loc = locale or "ru"
    parts = [str(base or "").strip()]
    target = _loop_target(details)
    if target:
        parts.append(t("supervisor.repeating", loc, target=target))
    # Keep the question short — dump tool output in context, not here.
    return "\n".join(p for p in parts if p)


def format_human_loop_context(
    *,
    problem: str,
    tool: str,
    details: str = "",
    last_result: str = "",
    next_move: str = "",
    known: str = "",
    locale: str | None = None,
) -> str:
    """Structured evidence for the ask_user dialog (not raw supervisor guidance)."""
    from core.i18n import t

    loc = locale or "ru"
    lines = [
        t("supervisor.stuck", loc, problem=problem),
        t("supervisor.tool", loc, tool=tool),
    ]
    target = _loop_target(details)
    if target:
        lines.append(t("supervisor.repeating", loc, target=target))
    if known:
        lines.append(t("supervisor.known", loc, known=known))
    excerpt = _result_excerpt(last_result, 480)
    if excerpt:
        lines.append(t("supervisor.last_tool_result", loc, result=excerpt))
    if next_move:
        lines.append(t("supervisor.asked_agent", loc, next=next_move))
    return "\n".join(lines)


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


def _looks_like_venv_package_hunt(details: str) -> bool:
    blob = (details or "").lower()
    in_venv = any(token in blob for token in ("site-packages", ".venv/", "venv/lib", "/lib/python"))
    hunts = any(token in blob for token in ("grep", "find ", "ls ", "rg ", "pip show", "pip list"))
    return in_venv and hunts


def _looks_like_absence_result(result: str) -> bool:
    blob = (result or "").lower()
    if not blob.strip():
        return False
    return any(
        token in blob
        for token in (
            "not found",
            "no such",
            "none\n",
            "none of",
            "no mako",
            "no alemb",
            "really none",
            "exit code 1",
            "0 match",
            "no matches",
        )
    )


def diagnose_loop_fix(
    *,
    tool: str,
    details: str = "",
    last_result: str = "",
    available_tools: list[str] | None = None,
    inspect_loop: bool = False,
    noop_write_loop: bool = False,
    locale: str | None = None,
    job_name: str = "",
) -> dict[str, str]:
    """What is stuck, what is already known, and what to fix next."""
    from core.i18n import t

    loc = locale or "ru"
    name = (job_name or "").strip() or "coder"
    tool_l = (tool or "tool").strip() or "tool"
    blob = (details or "").lower()
    target = _loop_target(details)
    target_s = f" (`{target}`)" if target else ""
    available = [str(t).strip() for t in (available_tools or []) if str(t).strip()]
    read = _prefer_tool(available, "read_file", "grep", "glob", "list_directory")
    write = _prefer_tool(available, "write_file", "delete_file")
    search = _prefer_tool(available, "grep", "glob", "read_file")

    if inspect_loop or (
        tool_l in {"terminal", "run_terminal_command"}
        and any(x in blob for x in ("inspect.", "python -c", "__init__", "protocol"))
    ):
        return {
            "problem": t("supervisor.p.inspect", loc),
            "known": t("supervisor.k.inspect", loc),
            "next_move": (
                f"stop inspect.getsource / python -c. Write the app with "
                f"{write or 'write_file'} (or {read or 'read_file'} a local file you will edit). "
                "Do not introspect another library method"
            ),
            "user_question": t("supervisor.q.inspect", loc, target=target_s, name=name),
        }

    if noop_write_loop or (tool_l == "write_file" and "no content changes" in blob):
        return {
            "problem": t("supervisor.p.noop_write", loc),
            "known": t("supervisor.k.noop_write", loc),
            "next_move": (
                "STOP rewriting those paths. Run pytest once if you have not, "
                "then the next message must be the final answer with NO tool calls"
            ),
            "user_question": t("supervisor.q.noop_write", loc, target=target_s, name=name),
        }

    if tool_l in {"terminal", "run_terminal_command"}:
        if _looks_like_project_launch(details) or any(
            x in blob for x in ("uvicorn", "gunicorn", "npm run dev", "fastapi run", ".main")
        ):
            bg = _prefer_tool(
                available,
                "start_background_process",
                "run_project",
                "check_background_process",
            )
            return {
                "problem": t("supervisor.p.launch", loc),
                "known": t("supervisor.k.launch", loc),
                "next_move": (
                    f"use {bg or 'start_background_process'} with the same command, "
                    "then check_background_process. Do not use &, nohup, or python -m *.main in terminal"
                ),
                "user_question": t("supervisor.q.launch", loc, target=target_s, name=name),
            }
        if _looks_like_venv_package_hunt(details):
            absence = (
                t("supervisor.k.venv_absent", loc)
                if _looks_like_absence_result(last_result) or "grep" in blob
                else t("supervisor.k.venv", loc)
            )
            return {
                "problem": t("supervisor.p.venv", loc),
                "known": absence,
                "next_move": (
                    f"do not ls/grep site-packages again. If you need a package, "
                    f"`uv add <name>` once; otherwise {write or 'write_file'} the app "
                    f"and run pytest. Searching .venv is not a fix"
                ),
                "user_question": t("supervisor.q.venv", loc, target=target_s, name=name),
            }
        if any(x in blob for x in ("pip install", "uv add", "uv sync")):
            return {
                "problem": t("supervisor.p.install", loc),
                "known": t("supervisor.k.install", loc),
                "next_move": (
                    f"stop re-running the installer; {read or 'read_file'} the project "
                    "and continue implementation or run tests once"
                ),
                "user_question": t("supervisor.q.install", loc, target=target_s, name=name),
            }
        return {
            "problem": t("supervisor.p.terminal", loc, tool=tool_l),
            "known": (
                t("supervisor.k.terminal_result", loc)
                if last_result
                else t("supervisor.k.terminal", loc)
            ),
            "next_move": (
                f"do not re-run this terminal command. {read or 'read_file'} / "
                f"{search or 'grep'} project source, then {write or 'write_file'} "
                "the fix or write the final answer"
            ),
            "user_question": t("supervisor.q.terminal", loc, target=target_s, name=name),
        }

    if tool_l == "read_file":
        return {
            "problem": t("supervisor.p.read", loc),
            "known": t("supervisor.k.read", loc),
            "next_move": (
                f"next {write or 'write_file'} a change or {search or 'grep'} a "
                "different path — do not re-read the same file"
            ),
            "user_question": t("supervisor.q.read", loc, target=target_s, name=name),
        }
    if tool_l in {"grep", "glob"}:
        return {
            "problem": t("supervisor.p.search", loc),
            "known": t("supervisor.k.search", loc),
            "next_move": (
                f"open one hit with {read or 'read_file'}, then {write or 'write_file'} "
                "or answer; do not repeat the same search"
            ),
            "user_question": t("supervisor.q.search", loc, target=target_s, name=name),
        }
    if tool_l == "write_file":
        return {
            "problem": t("supervisor.p.write", loc),
            "known": t("supervisor.k.write", loc),
            "next_move": (
                f"stop rewriting the same file; {read or 'read_file'} to verify or "
                "move to the next deliverable / final answer"
            ),
            "user_question": t("supervisor.q.write", loc, target=target_s, name=name),
        }
    if tool_l in {"web_search", "web_fetch"}:
        return {
            "problem": t("supervisor.p.web", loc),
            "known": t("supervisor.k.web", loc),
            "next_move": (
                "use a different query/URL once, then write the answer from evidence "
                "you already have — do not repeat the same fetch/search"
            ),
            "user_question": t("supervisor.q.web", loc, target=target_s, name=name),
        }
    return {
        "problem": t("supervisor.p.generic", loc, tool=tool_l),
        "known": t("supervisor.k.generic", loc),
        "next_move": (
            f"call a different tool or different arguments "
            f"({read or 'read_file'} / {write or 'write_file'}), "
            "or produce a partial final result"
        ),
        "user_question": t("supervisor.q.generic", loc, tool=tool_l, target=target_s, name=name),
    }


def build_loop_guidance(
    *,
    tool: str,
    details: str = "",
    available_tools: list[str] | None = None,
    attempt: int = 1,
    max_attempts: int = DEFAULT_MAX_INTERVENTIONS,
    last_result: str = "",
    inspect_loop: bool = False,
    noop_write_loop: bool = False,
) -> str:
    """Concrete next-step guidance so the model can leave a tool loop."""
    tool_l = (tool or "tool").strip() or "tool"
    available = [str(t).strip() for t in (available_tools or []) if str(t).strip()]
    read = _prefer_tool(available, "read_file", "grep", "glob", "list_directory")
    ask = _prefer_tool(available, "ask_user") or "ask_user"
    fix = diagnose_loop_fix(
        tool=tool_l,
        details=details,
        last_result=last_result,
        available_tools=available,
        inspect_loop=inspect_loop,
        noop_write_loop=noop_write_loop,
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
            f" LAST CHANCE: apply the fix above. If you cannot, call `{ask}` "
            f"now with this question (do not run another `{tool_l}`): "
            f"{fix['user_question']} "
            "If you repeat the same call instead, the supervisor will ask the "
            "human and then stop the job."
        )
    else:
        warning = (
            f" Attempt {attempt}/{max_attempts}. If you cannot apply the fix, "
            f"call `{ask}` instead of repeating `{tool_l}`."
        )
    return (
        f"SUPERVISOR GUIDANCE: You are looping on `{tool_l}` "
        f"({fix['problem']}). {fix['known']} "
        f"Do NOT call `{tool_l}` with the same arguments again. "
        f"What to fix: {fix['next_move']}.{tools_line}"
        f"{warning}"
    )


def assess_handle(
    handle: Any,
    *,
    policy: SupervisorPolicy | None = None,
    now: float | None = None,
    locale: str | None = None,
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
    last_result = str((traces[-1] or {}).get("result") or "") if traces else ""
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
                "via terminal. If the user asked to run it in the background or to "
                "keep a server/bot running, call "
                f"{bg or 'start_background_process'} with the same command "
                "(label the app), then check_background_process. "
                "Tests (`pytest`, `npm test`) must stay in run_terminal_command. "
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
        fix = diagnose_loop_fix(
            tool=str(tool),
            details=details,
            last_result=last_result,
            available_tools=available,
            inspect_loop=inspect_hit,
            noop_write_loop=noop_write_hit,
            locale=locale,
            job_name=str(getattr(handle, "name", "") or ""),
        )
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
                last_result=last_result,
                inspect_loop=inspect_hit,
                noop_write_loop=noop_write_hit,
            ),
            signals={
                **signals,
                "loop_tool": str(tool),
                "loop_details": details[:240],
                "last_result": last_result[:400],
                "search_loop": search_only,
                "path_loop": path_loop,
                "inspect_loop": inspect_hit,
                "noop_write_loop": noop_write_hit,
                "user_question": format_human_loop_question(
                    fix["user_question"],
                    details=details,
                    last_result=last_result,
                    locale=locale,
                ),
                "user_context": format_human_loop_context(
                    problem=fix["problem"],
                    tool=str(tool),
                    details=details,
                    last_result=last_result,
                    next_move=fix["next_move"],
                    known=fix["known"],
                    locale=locale,
                ),
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

    if _activity_looks_empty(handle):
        from core.llm.completion import EMPTY_FINAL_CONTINUE

        return Diagnosis(
            kind="empty_reply",
            severity="critical",
            summary="empty model reply is not a finished step",
            guidance=EMPTY_FINAL_CONTINUE,
            signals={**signals, "empty_reply": True},
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
        self._escalating: set[str] = set()
        self._escalated: set[str] = set()

    @property
    def policy(self) -> SupervisorPolicy:
        return self._policy

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _locale(self) -> str:
        return _ui_locale(self._manager)

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
        self._escalating.discard(name)
        self._escalated.discard(name)

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
        try:
            from core.subagents.runtime_registry import take_cancel_requests

            owner, _src = self._manager._runtime_meta()
            for cancel_name in take_cancel_requests(self._manager._profile_name(), owner):
                term = getattr(self._manager, "terminate", None)
                if callable(term):
                    await term(cancel_name)
        except Exception:
            logger.debug("supervisor cancel-file drain failed", exc_info=True)
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

    def _job_waiting_for_user(self, name: str, handle: Any) -> bool:
        if getattr(handle, "awaiting_user", False) or name in self._escalating:
            return True
        interactions = getattr(self._manager, "interactions", None)
        list_q = getattr(interactions, "list_pending_questions", None)
        if not callable(list_q):
            return False
        try:
            pending = list_q() or []
        except Exception:
            return False
        if not isinstance(pending, (list, tuple)):
            return False
        return any(
            isinstance(item, dict) and str(item.get("subagent_name") or "") == name
            for item in pending
        )

    async def _maybe_intervene(self, handle: Any) -> None:
        name = str(getattr(handle, "name", "") or "")
        if not name:
            return
        if self._job_waiting_for_user(name, handle):
            return
        diagnosis = assess_handle(handle, policy=self._policy, locale=self._locale())
        if not diagnosis.needs_intervention:
            return
        pinned = int(getattr(handle, "steps_at_user_reply", 0) or 0)
        if pinned and int(getattr(handle, "steps_taken", 0) or 0) <= pinned:
            if diagnosis.kind in {"loop", "launch"}:
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
                        f"`{name}` ({diagnosis.kind}); asking the human"
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
                    if name in self._escalated:
                        last = float(self._last_intervene_at.get(name, 0.0))
                        grace = max(float(self._policy.loop_cooldown_s), 20.0)
                        # Human just answered — do not kill on the next poll.
                        if last and (time.monotonic() - last) < grace:
                            self._last_kind[name] = "user_reply"
                            return
                        await self._stop_loop(handle, diagnosis)
                    else:
                        begin = getattr(handle, "begin_wait_for_user", None)
                        if callable(begin):
                            begin()
                        asyncio.create_task(
                            self._ask_human_then_retry_or_stop(handle, diagnosis),
                            name=f"supervisor-ask-{name[:24]}",
                        )
            return

        now = time.monotonic()
        last = float(self._last_intervene_at.get(name, 0.0))
        cooldown = (
            self._policy.loop_cooldown_s
            if diagnosis.kind in {"loop", "launch", "tests_green"}
            else self._policy.cooldown_s
        )
        # One slow LLM call (qwen reasoning) must not stack 3× hung nudges.
        if diagnosis.kind == "hung":
            cooldown = max(cooldown, float(self._policy.idle_s))
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
                    last_result=str(diagnosis.signals.get("last_result") or ""),
                    inspect_loop=bool(diagnosis.signals.get("inspect_loop")),
                    noop_write_loop=bool(diagnosis.signals.get("noop_write_loop")),
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

    async def _ask_human_then_retry_or_stop(self, handle: Any, diagnosis: Diagnosis) -> None:
        """When the model cannot leave a loop, ask the human what to do."""
        name = str(getattr(handle, "name", "") or "")
        if not name or name in self._escalating:
            return
        self._escalating.add(name)
        begin = getattr(handle, "begin_wait_for_user", None)
        if callable(begin) and not getattr(handle, "awaiting_user", False):
            begin()
        from core.i18n import t

        loc = self._locale()
        question = str(diagnosis.signals.get("user_question") or "").strip() or t(
            "supervisor.fallback_q",
            loc,
            name=name,
            summary=diagnosis.summary,
        )
        interactions = getattr(self._manager, "interactions", None)
        ask = getattr(interactions, "ask_user", None)
        if not callable(ask):
            self._escalating.discard(name)
            end = getattr(handle, "end_wait_for_user", None)
            if callable(end):
                end()
            await self._stop_loop(handle, diagnosis)
            return
        try:
            try:
                handle.record_activity(
                    "status",
                    t("supervisor.awaiting_user", loc, name=name),
                    details=question,
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
            context = str(diagnosis.signals.get("user_context") or "").strip()
            if not context:
                context = format_human_loop_context(
                    problem=diagnosis.summary,
                    tool=str(diagnosis.signals.get("loop_tool") or ""),
                    details=str(diagnosis.signals.get("loop_details") or ""),
                    last_result=str(diagnosis.signals.get("last_result") or ""),
                    next_move=diagnosis.guidance,
                    locale=loc,
                )
            answer = await ask(
                name,
                question,
                context=context,
            )
        except Exception:
            logger.exception("supervisor: ask_user failed for %s", name)
            self._escalating.discard(name)
            end = getattr(handle, "end_wait_for_user", None)
            if callable(end):
                end()
            await self._stop_loop(handle, diagnosis)
            return

        self._escalating.discard(name)
        self._escalated.add(name)
        text = str(answer or "").strip()
        low = text.lower()
        if not text or low.startswith("error:") or low in {"stop", "cancel", "abort", "kill"}:
            end = getattr(handle, "end_wait_for_user", None)
            if callable(end):
                end()
            await self._stop_loop(handle, diagnosis)
            return

        # Fresh budget + cooldown so the reply can actually change the next tool.
        self._interventions[name] = 0
        self._last_kind[name] = "user_reply"
        self._last_intervene_at[name] = time.monotonic()
        reply = Diagnosis(
            kind="loop",
            severity="warning",
            summary="human answered supervisor question",
            guidance=(
                "SUPERVISOR GUIDANCE: The human answered because you could not "
                "leave the tool loop yourself. Follow this and do not repeat "
                f"the previous command:\n{text}"
            ),
            signals=diagnosis.signals,
        )
        await self._send_guidance(handle, reply, attempt=self._interventions[name])
        try:
            handle.record_activity(
                "supervisor_guidance",
                "Supervisor: human reply",
                details=text[:300],
                steps_taken=int(getattr(handle, "steps_taken", 0) or 0),
            )
        except Exception:
            pass
        end = getattr(handle, "end_wait_for_user", None)
        if callable(end):
            end()

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


def drain_guidance_from_input_queue(
    input_queue: Any,
    *,
    max_messages: int = 8,
) -> tuple[list[str], bool]:
    """Drain process-mode supervisor inbox (guidance/revise + cancel)."""
    texts: list[str] = []
    cancelled = False
    if input_queue is None:
        return texts, cancelled
    from core.subagents.communication import AgentMessage

    for _ in range(max_messages):
        try:
            data = input_queue.get_nowait()
        except Exception:
            break
        try:
            msg = data if isinstance(data, AgentMessage) else AgentMessage.deserialize(data)
        except Exception:
            continue
        kind = str(getattr(msg, "msg_type", "") or "")
        if kind == "cancel":
            cancelled = True
            continue
        if kind in {"guidance", "revise"}:
            content = str(getattr(msg, "content", "") or "").strip()
            if content:
                texts.append(content)
    return texts, cancelled


async def collect_subagent_guidance(agent: Any) -> tuple[list[str], bool]:
    """Drain supervisor inbox attached to a child HolixAgent."""
    texts: list[str] = []
    cancelled = False
    if agent is None:
        return texts, cancelled
    name = str(getattr(agent, "_subagent_name", "") or "").strip()
    receive = getattr(agent, "_subagent_guidance_receive", None)
    if callable(receive) and name:
        texts.extend(await drain_guidance_messages(receive, name))
    queue = getattr(agent, "_subagent_input_queue", None)
    if queue is not None:
        q_texts, q_cancel = drain_guidance_from_input_queue(queue)
        texts.extend(q_texts)
        cancelled = cancelled or q_cancel
    return texts, cancelled


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
