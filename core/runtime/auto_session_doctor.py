"""Start session_doctor when a turn contradicts its own tool results.

One automatic spawn per user message, on the main agent only. A profile or
``HOLIX_AUTO_SESSION_DOCTOR=0`` turns it off. The default is on.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_SKIP_TOOLS = frozenset(
    {
        "ask_user",
        "todo_write",
        "todo",
        "self_diagnose",
        "delegate_to_subagent",
        "request_admin_support",
    }
)
_IDENTICAL_CALLS = 4
_ERROR_STREAK = 3

AUTO_DOCTOR_NOTICE = "Checking this session: the reply does not match the tool results."


def auto_session_doctor_enabled(agent: Any | None) -> bool:
    """Profile value wins. Missing config stays on."""
    cfg = getattr(agent, "config", None) if agent is not None else None
    if cfg is None:
        return True
    raw = getattr(cfg, "auto_session_doctor", None)
    if raw is None:
        return True
    return bool(raw)


def _slot_allows(agent: Any | None) -> bool:
    slot = str(getattr(agent, "agent_slot", "main") or "main") if agent is not None else "main"
    if slot.startswith("session_doctor"):
        return False
    return slot in {"main", "supervisor"} or slot.startswith("supervisor")


def _claim(agent: Any | None, conversation_id: str, messages: list[dict[str, Any]] | None) -> bool:
    """First automatic doctor for this user text. Later steps of the same turn skip."""
    from core.graph.action_honesty import last_user_text

    if agent is None:
        return True
    seen = getattr(agent, "_auto_doctor_claimed", None)
    if not isinstance(seen, set):
        seen = set()
        agent._auto_doctor_claimed = seen
    key = (str(conversation_id or ""), last_user_text(messages)[:240])
    if key in seen:
        return False
    seen.add(key)
    if len(seen) > 32:
        seen.clear()
        seen.add(key)
    return True


def _calls_since_user(messages: list[dict[str, Any]] | None) -> list[tuple[str, str]]:
    from core.graph.action_honesty import _last_real_user_index

    last = _last_real_user_index(messages)
    calls: list[tuple[str, str]] = []
    for msg in (messages or [])[last + 1 :]:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str((fn or {}).get("name") or tc.get("name") or "").strip()
            raw_args = (fn or {}).get("arguments")
            if raw_args is None:
                raw_args = tc.get("arguments") or ""
            args = raw_args if isinstance(raw_args, str) else str(raw_args)
            if name and name not in _SKIP_TOOLS:
                calls.append((name, args.strip()))
    return calls


def tool_loop_reason(messages: list[dict[str, Any]] | None) -> str:
    """Same tool and arguments four times, or three failures of one tool in a row."""
    from core.graph.action_honesty import (
        _last_real_user_index,
        _tool_call_id_names,
        _tool_name_from_message,
        _tool_result_failed,
    )

    counts = Counter(_calls_since_user(messages))
    if counts:
        (name, _args), count = counts.most_common(1)[0]
        if count >= _IDENTICAL_CALLS:
            return f"tool_loop:{name}"

    last = _last_real_user_index(messages)
    id_to_name = _tool_call_id_names(messages or [])
    streak_name = ""
    streak = 0
    for msg in (messages or [])[last + 1 :]:
        if msg.get("role") != "tool":
            continue
        name = _tool_name_from_message(msg, id_to_name)
        raw = msg.get("content")
        content = raw if isinstance(raw, str) else str(raw or "")
        if name and name not in _SKIP_TOOLS and _tool_result_failed(content):
            if name == streak_name:
                streak += 1
            else:
                streak_name = name
                streak = 1
            if streak >= _ERROR_STREAK:
                return f"tool_errors:{name}"
        else:
            streak_name = ""
            streak = 0
    return ""


def _evidence(reason: str, messages: list[dict[str, Any]] | None, final_response: str) -> str:
    from core.graph.action_honesty import unknown_background_task_ids

    if reason.startswith("invented_task"):
        ids = ", ".join(sorted(unknown_background_task_ids(final_response, messages)))
        return ids or reason
    if reason.startswith("tool_"):
        return reason.split(":", 1)[-1]
    text = " ".join((final_response or "").split())
    return text[:180]


def nudge_text(
    reason: str,
    messages: list[dict[str, Any]] | None,
    final_response: str,
) -> str:
    evidence = _evidence(reason, messages, final_response)
    return (
        "[Self-diagnose] This turn contradicts tool results "
        f"({reason}). Spawn a clean-context session_doctor now: "
        'delegate_to_subagent(agent_type="session_doctor", fork=false, task=…). '
        "In the task include this conversation_id and the evidence below. "
        "Then wait_subagent_result. Do not call self_diagnose yourself. "
        "Do not change system settings. Do not apologize until the doctor returns. "
        "Do not claim the original task is done.\n"
        f"Evidence: {evidence}"
    )


def should_auto_session_doctor(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
    agent: Any | None = None,
    exhausted_claims: bool = True,
) -> str:
    """Reason to spawn the doctor, or empty when this turn should continue as usual."""
    from core.graph.action_honesty import (
        _max_nudges_for_turn,
        _plan_mode_skips_honesty,
        lacks_evidence_for_claim,
        looks_like_plan_monologue,
        looks_like_status_monologue,
        self_diagnose_called_since_last_user,
        should_nudge_missing_service,
        unknown_background_task_ids,
    )

    if not auto_session_doctor_enabled(agent) or not _slot_allows(agent):
        return ""
    if _plan_mode_skips_honesty(state):
        return ""
    if self_diagnose_called_since_last_user(
        messages,
        tool_results=state.get("tool_results") if isinstance(state, dict) else None,
    ):
        return ""

    loop = tool_loop_reason(messages)
    if loop:
        return loop

    text = final_response or ""
    if not text.strip():
        return ""
    count = int(state.get("honesty_nudge_count") or 0)
    if count >= 1 and unknown_background_task_ids(text, messages):
        return "invented_task_id"
    if not exhausted_claims:
        return ""

    if looks_like_status_monologue(text) or looks_like_plan_monologue(text):
        return ""
    user_input = state.get("user_input") if isinstance(state, dict) else None
    tool_results = state.get("tool_results") if isinstance(state, dict) else None
    max_nudges = _max_nudges_for_turn(
        messages,
        final_response=text,
        user_input=user_input,
        tool_results=tool_results,
    )
    if count < max_nudges:
        return ""
    if lacks_evidence_for_claim(
        text,
        messages,
        tool_results=tool_results,
        user_input=user_input,
    ):
        return "unproven_claim"
    if should_nudge_missing_service(text, messages):
        return "missing_service"
    if unknown_background_task_ids(text, messages):
        return "invented_task_id"
    return ""


def delegate_tool_choice(tools: list[Any] | None) -> dict[str, Any] | None:
    """Force the spawn when the native tool is on the schema. Code mode has no such tool."""
    from core.graph.action_honesty import _tools_include_name

    if not _tools_include_name(tools, "delegate_to_subagent"):
        return None
    return {"type": "function", "function": {"name": "delegate_to_subagent"}}


def claim_auto_session_doctor(
    agent: Any | None,
    state: dict[str, Any],
    messages: list[dict[str, Any]] | None,
    *,
    final_response: str | None,
    exhausted_claims: bool = True,
) -> str:
    """Reason when this call is the one automatic spawn. Empty if already used or not due."""
    reason = should_auto_session_doctor(
        state,
        final_response=final_response,
        messages=messages,
        agent=agent,
        exhausted_claims=exhausted_claims,
    )
    if not reason:
        return ""
    conversation_id = str(state.get("conversation_id") or "") if isinstance(state, dict) else ""
    if not _claim(agent, conversation_id, messages):
        return ""
    if agent is not None and hasattr(agent, "emit"):
        from core.agent_events import ThinkingEvent

        agent.emit(
            ThinkingEvent(
                message=AUTO_DOCTOR_NOTICE,
                conversation_id=conversation_id,
            )
        )
    return reason
