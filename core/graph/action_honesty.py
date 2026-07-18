"""Detect false completion claims and nudge the model to use tools."""

from __future__ import annotations

import re
from typing import Any

# Past/result claims that something was done (not mere intent).
_COMPLETION_CLAIM = re.compile(
    r"(?is)"
    r"("
    r"\b(готово|сделано|выполнено|успешно)\b"
    r"|\b(сохран[её]н[аоы]?|сохранил[аи]?|записал[аи]?|записан[аоы]?)\b"
    r"|\b(создал[аи]?|создан[аоы]?|удалил[аи]?|удал[её]н[аоы]?)\b"
    r"|\b(написан[аоы]?|записал\s+план|план\s+сохран)"
    r"|\b(i\s+(have\s+)?(saved|created|deleted|written|done)|i'?ve\s+(saved|created|deleted|written))\b"
    r"|\b(successfully\s+(saved|created|deleted|written|completed|removed))\b"
    r"|\b(file\s+(is\s+)?(saved|created|written)|all\s+projects?\s+deleted)\b"
    r"|\b(файл\s+(лежит|сохран[её]н|создан|записан)|проекты?\s+удален)"
    r")"
)

# Future / intent only — do not treat as a completion claim by itself.
_INTENT_ONLY = re.compile(
    r"(?is)^\s*("
    r"сейчас\s+(сохран|запис|созда|удал|выполн|напиш)"
    r"|буду\s+"
    r"|собираюсь\s+"
    r"|i\s+(will|am\s+going\s+to|'ll)\s+"
    r"|going\s+to\s+"
    r").*$"
)

# Ending the turn with "I'm doing X now" without any tool call.
_ACTION_INTENT = re.compile(
    r"(?is)("
    r"сейчас\s+(сохран|запис|созда|удал|выполн|напиш|исправ)"
    r"|выполняю\s+(запись|сохран|удал|операц)"
    r"|записываю\s+(план|файл)"
    r"|сохран[яю]\s+(план|файл)"
    r"|через\s+`?write_file`?"
    r"|call(?:ing)?\s+`?write_file`?"
    r"|i\s+(will|am\s+going\s+to|'ll|'m\s+going\s+to)\s+"
    r"(save|write|create|delete|remove|run|execute)"
    r"|writing\s+(the\s+)?file\s+(now|right\s+now)"
    r"|saving\s+(the\s+)?(plan|file)\s+(now|right\s+now)"
    r")"
)

_WRITE_CLAIM = re.compile(
    r"(?is)("
    r"сохран|запис|write_file|patch_file|создал\s+файл|создан\s+файл"
    r"|saved\s+(the\s+)?(file|plan)|wrote\s+(the\s+)?file|created\s+(the\s+)?file"
    r"|план\s+сохран|implementation_plan|\.md\b"
    r")"
)

_DELETE_CLAIM = re.compile(
    r"(?is)("
    r"удал|delete|removed|очист"
    r")"
)

_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "patch_file",
        "run_terminal_command",
        "execute_python",
        "update_holix_section",
    }
)
_DELETE_TOOLS = frozenset(
    {
        "run_terminal_command",
        "execute_python",
        "write_file",
    }
)

_ERROR_MARKERS = (
    "error:",
    "error (",
    "error writing",
    "error reading",
    "permission denied",
    "no such file",
    "not found",
    "failed",
    "cannot remove",
    "exit code 1",
    "exit code 2",
)

ACTION_HONESTY_NUDGE = (
    "[Action honesty] You stated that work was completed, but there is no "
    "successful tool result in this turn that proves it. "
    "Do NOT claim success again. Call the required tools now "
    "(e.g. write_file, run_terminal_command), verify the result, "
    "and only then report what the tools actually returned. "
    "If a tool failed, say it failed and show the error."
)

_MAX_HONESTY_NUDGES = 1


def claims_action_completed(text: str | None) -> bool:
    """True when the assistant asserts that an action already succeeded."""
    content = (text or "").strip()
    if not content or len(content) < 8:
        return False
    if not _COMPLETION_CLAIM.search(content):
        return False
    # Pure intent ("Сейчас сохраню…") without a completion claim elsewhere.
    if _INTENT_ONLY.match(content) and not re.search(
        r"(?is)\b(готово|сделано|сохран[её]н|создан|удал[её]н|successfully|i\s+have|i'?ve)\b",
        content,
    ):
        return False
    return True


def _tool_result_failed(content: str | None) -> bool:
    c = (content or "").strip().lower()
    if not c:
        return True
    if c.startswith("error"):
        return True
    return any(m in c for m in _ERROR_MARKERS)


def _tool_name_from_message(msg: dict[str, Any], id_to_name: dict[str, str]) -> str:
    name = msg.get("name") or msg.get("tool_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    meta = msg.get("metadata") or {}
    if isinstance(meta, dict):
        mname = meta.get("tool_name") or meta.get("name")
        if isinstance(mname, str) and mname.strip():
            return mname.strip()
    tid = msg.get("tool_call_id")
    if isinstance(tid, str) and tid in id_to_name:
        return id_to_name[tid]
    return ""


def _tool_call_id_names(messages: list[dict[str, Any]]) -> dict[str, str]:
    id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tid = tc.get("id")
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = (fn or {}).get("name") or tc.get("name")
            if isinstance(tid, str) and tid and isinstance(name, str) and name.strip():
                id_to_name[tid] = name.strip()
    return id_to_name


def successful_tools_since_last_user(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Tool names with non-error results after the last user message."""
    names: list[str] = []
    if messages:
        last_user = -1
        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user = i
        id_to_name = _tool_call_id_names(messages)
        for msg in messages[last_user + 1 :]:
            if msg.get("role") != "tool":
                continue
            raw = msg.get("content")
            content = raw if isinstance(raw, str) else str(raw or "")
            if _tool_result_failed(content):
                continue
            name = _tool_name_from_message(msg, id_to_name)
            names.append(name or "tool")

    # Fallback: latest batch from tool_execution_node (names always present).
    if not names and tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            content = raw if isinstance(raw, str) else str(raw or "")
            if _tool_result_failed(content):
                continue
            name = tr.get("tool_name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
            else:
                names.append("tool")
    return names


def lacks_evidence_for_claim(
    text: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if the reply claims completion without matching successful tools."""
    if not claims_action_completed(text):
        return False
    successes = successful_tools_since_last_user(messages, tool_results=tool_results)
    if not successes:
        return True

    content = text or ""
    success_set = set(successes)
    write_claim = bool(_WRITE_CLAIM.search(content))
    delete_claim = bool(_DELETE_CLAIM.search(content))

    if write_claim and not success_set.intersection(_WRITE_TOOLS | {"tool"}):
        return True
    if delete_claim and not write_claim and not success_set.intersection(_DELETE_TOOLS | {"tool"}):
        return True
    return False


def _tools_attempted_since_last_user(messages: list[dict[str, Any]] | None) -> bool:
    if not messages:
        return False
    last_user = -1
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            last_user = i
    for msg in messages[last_user + 1 :]:
        if msg.get("role") == "tool":
            return True
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            return True
    return False


def ends_turn_on_unexecuted_intent(
    text: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """True when the model only promises an action and never called tools."""
    content = (text or "").strip()
    if not content or not _ACTION_INTENT.search(content):
        return False
    return not _tools_attempted_since_last_user(messages)


def should_nudge_false_completion(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """Whether to block the final answer and force a tool-use retry."""
    if int(state.get("honesty_nudge_count") or 0) >= _MAX_HONESTY_NUDGES:
        return False
    # Plan executor has its own tool-progress nudge.
    plan_steps = state.get("plan_steps") or []
    current = int(state.get("current_plan_step", 0))
    if plan_steps and current < len(plan_steps):
        return False
    if lacks_evidence_for_claim(
        final_response,
        messages,
        tool_results=state.get("tool_results"),
    ):
        return True
    return ends_turn_on_unexecuted_intent(final_response, messages)


def honesty_retry_update(
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    honesty_nudge_count: int = 0,
    include_assistant: bool = True,
) -> dict[str, Any]:
    """Keep the turn open and instruct the model to execute tools."""
    updated = list(messages)
    if include_assistant and final_response:
        # Avoid double-append if caller already added the assistant message.
        last = updated[-1] if updated else None
        already = (
            isinstance(last, dict)
            and last.get("role") == "assistant"
            and (last.get("content") or "") == final_response
        )
        if not already:
            updated.append({"role": "assistant", "content": final_response})
    updated.append({"role": "user", "content": ACTION_HONESTY_NUDGE})
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": False,
        "tool_calls": [],
        "final_response": final_response,
        "honesty_nudge_count": int(honesty_nudge_count) + 1,
    }
