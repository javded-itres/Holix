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
    r"|\b(заполнил[аи]?|заполнен[аоы]?)\b"
    r"|\b(написан[аоы]?|записал\s+план|план\s+сохран)"
    r"|\b(i\s+(have\s+)?(saved|created|deleted|written|done|filled)|i'?ve\s+(saved|created|deleted|written|filled))\b"
    r"|\b(successfully\s+(saved|created|deleted|written|completed|removed|filled))\b"
    r"|\b(file\s+(is\s+)?(saved|created|written)|all\s+projects?\s+deleted)\b"
    r"|\b(файл\s+(лежит|сохран[её]н|создан|записан)|проекты?\s+удален)"
    r")"
)

# Studio / user asks to fill SDD change artifacts (UI auto-prompt after create).
_SDD_FILL_REQUEST = re.compile(
    r"(?is)("
    r"sdd_write_artifact"
    r"|please\s+fill\s+(proposal|delta\s+specs|tasks|artifacts)"
    r"|fill\s+proposal"
    r"|заполни\s+(proposal|спек|tasks|артефакт)"
    r"|SDD\s+change\s+`.+`\s+created"
    r")"
)

# Assistant claims SDD artifacts were filled/written.
_SDD_FILL_CLAIM = re.compile(
    r"(?is)("
    r"заполнил[аи]?\s+(все\s+)?(четыре\s+)?артефакт"
    r"|заполнил[аи]?\s+(спек|proposal|tasks|design|change|delta)"
    r"|filled\s+(all\s+)?(four\s+)?artifact"
    r"|filled\s+(proposal|tasks|specs|design|delta)"
    r"|proposal\.md|tasks\.md|openspec/changes/"
    r"|sdd_write_artifact"
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
    r"|спек[аиу]|openspec|sdd_write|sdd_create|delta\s+spec|proposal\.md"
    r"|заполнил[аи]?\s+(все\s+)?(четыре\s+)?(артефакт|спек|proposal|tasks|change|design)"
    r"|артефакт"
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
        # SDD: tools that persist real content (create_change alone is stubs only)
        "sdd_init",
        "sdd_write_artifact",
        "sdd_check_task",
        "sdd_set_task_assignee",
        "sdd_set_apply_mode",
        "sdd_archive",
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
    "(e.g. write_file, sdd_write_artifact, run_terminal_command), verify the result, "
    "and only then report what the tools actually returned. "
    "For SDD: create_change only scaffolds stubs — fill via sdd_write_artifact "
    "and confirm with sdd_status (apply_ready). Main openspec/specs update only "
    "after sdd_archive. If a tool failed, say it failed and show the error."
)

SDD_FILL_HONESTY_NUDGE = (
    "[Action honesty — SDD] You claimed SDD artifacts were filled, but this turn "
    "has no successful sdd_write_artifact result. "
    "Do NOT invent paths, sizes, or task lists. "
    "Call sdd_write_artifact now for proposal, design, specs (domain), and tasks "
    "(with assignees). Then call sdd_status and only report what tools returned. "
    "Scaffold stubs from create_change are NOT filled specs."
)

# Shown to the user when the model still has no write evidence after max nudges.
SDD_FILL_HONESTY_REFUSAL = (
    "Не удалось заполнить SDD-артефакты: за этот ход не было успешного вызова "
    "`sdd_write_artifact`, поэтому файлы на диске не менялись (остались заглушки "
    "после create_change, если change уже создан). "
    "Повторите запрос — агент обязан вызвать `sdd_write_artifact` для proposal, "
    "design, specs и tasks — либо заполните артефакты вручную."
)

_MAX_HONESTY_NUDGES = 1
_MAX_SDD_FILL_HONESTY_NUDGES = 3


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


def last_user_text(messages: list[dict[str, Any]] | None) -> str:
    """Content of the last real user message (skip honesty nudge injects)."""
    if not messages:
        return ""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        text = content if isinstance(content, str) else str(content or "")
        if text.strip().startswith("[Action honesty"):
            continue
        return text
    return ""


def is_sdd_fill_request(text: str | None) -> bool:
    """True when the user/Studio asked to fill SDD change artifacts."""
    return bool(text and _SDD_FILL_REQUEST.search(text))


def claims_sdd_artifacts_filled(text: str | None) -> bool:
    """True when the assistant claims SDD proposal/specs/tasks were written."""
    return bool(text and _SDD_FILL_CLAIM.search(text))


def has_successful_sdd_write(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if sdd_write_artifact succeeded after the last real user message."""
    return "sdd_write_artifact" in successful_tools_since_last_user(
        messages, tool_results=tool_results
    )


def sdd_fill_requires_tools(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
    user_input: str | None = None,
) -> bool:
    """Force tool use while filling SDD artifacts until a write succeeds."""
    user = (user_input or "").strip() or last_user_text(messages)
    if not is_sdd_fill_request(user):
        return False
    return not has_successful_sdd_write(messages, tool_results=tool_results)


def lacks_evidence_for_claim(
    text: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
    user_input: str | None = None,
) -> bool:
    """True if the reply claims completion without matching successful tools."""
    content = text or ""
    user = (user_input or "").strip() or last_user_text(messages)
    successes = successful_tools_since_last_user(messages, tool_results=tool_results)
    success_set = set(successes)

    # SDD fill: claiming filled artifacts requires sdd_write_artifact this turn.
    if claims_sdd_artifacts_filled(content) or (
        is_sdd_fill_request(user) and claims_action_completed(content)
    ):
        if "sdd_write_artifact" not in success_set:
            return True

    if not claims_action_completed(text):
        return False
    if not successes:
        return True

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


def _max_nudges_for_turn(
    messages: list[dict[str, Any]] | None,
    *,
    final_response: str | None,
    user_input: str | None = None,
) -> int:
    user = (user_input or "").strip() or last_user_text(messages)
    if is_sdd_fill_request(user) or claims_sdd_artifacts_filled(final_response):
        return _MAX_SDD_FILL_HONESTY_NUDGES
    return _MAX_HONESTY_NUDGES


def _plan_mode_skips_honesty(state: dict[str, Any]) -> bool:
    plan_steps = state.get("plan_steps") or []
    current = int(state.get("current_plan_step", 0))
    return bool(plan_steps and current < len(plan_steps))


def _unproven_sdd_fill_final(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """True when this is an SDD-fill turn ending without a successful write."""
    user_input = state.get("user_input") if isinstance(state, dict) else None
    user = (user_input or "").strip() or last_user_text(messages)
    if not is_sdd_fill_request(user):
        return False
    if has_successful_sdd_write(
        messages,
        tool_results=state.get("tool_results") if isinstance(state, dict) else None,
    ):
        return False
    if not (final_response or "").strip():
        return False
    return True


def should_nudge_false_completion(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """Whether to block the final answer and force a tool-use retry."""
    user_input = state.get("user_input") if isinstance(state, dict) else None
    max_nudges = _max_nudges_for_turn(
        messages, final_response=final_response, user_input=user_input
    )
    if int(state.get("honesty_nudge_count") or 0) >= max_nudges:
        return False
    # Plan executor has its own tool-progress nudge.
    if _plan_mode_skips_honesty(state):
        return False
    if lacks_evidence_for_claim(
        final_response,
        messages,
        tool_results=state.get("tool_results"),
        user_input=user_input,
    ):
        return True
    # SDD fill turn: never end with pure text before any sdd_write_artifact.
    if sdd_fill_requires_tools(
        messages,
        tool_results=state.get("tool_results"),
        user_input=user_input,
    ) and (final_response or "").strip():
        return True
    return ends_turn_on_unexecuted_intent(final_response, messages)


def should_refuse_unproven_sdd_fill(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """After max SDD nudges, never accept a final that had no sdd_write_artifact."""
    if _plan_mode_skips_honesty(state):
        return False
    if not _unproven_sdd_fill_final(
        state, final_response=final_response, messages=messages
    ):
        return False
    user_input = state.get("user_input") if isinstance(state, dict) else None
    max_nudges = _max_nudges_for_turn(
        messages, final_response=final_response, user_input=user_input
    )
    # Only refuse once nudges are exhausted (otherwise should_nudge retries).
    return int(state.get("honesty_nudge_count") or 0) >= max_nudges


def honesty_retry_update(
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    honesty_nudge_count: int = 0,
    include_assistant: bool = True,
    user_input: str | None = None,
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
    user = (user_input or "").strip() or last_user_text(updated)
    nudge = (
        SDD_FILL_HONESTY_NUDGE
        if is_sdd_fill_request(user) or claims_sdd_artifacts_filled(final_response)
        else ACTION_HONESTY_NUDGE
    )
    updated.append({"role": "user", "content": nudge})
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": False,
        "tool_calls": [],
        "final_response": final_response,
        "honesty_nudge_count": int(honesty_nudge_count) + 1,
    }


def honesty_refusal_update(
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    honesty_nudge_count: int = 0,
    include_assistant: bool = True,
    final_response: str | None = None,
) -> dict[str, Any]:
    """Replace an unproven SDD success claim with an honest failure final."""
    updated = list(messages)
    refusal = SDD_FILL_HONESTY_REFUSAL
    last = updated[-1] if updated else None
    if (
        isinstance(last, dict)
        and last.get("role") == "assistant"
        and (
            include_assistant
            or (final_response and (last.get("content") or "") == final_response)
            or claims_sdd_artifacts_filled(str(last.get("content") or ""))
            or claims_action_completed(str(last.get("content") or ""))
        )
    ):
        updated[-1] = {"role": "assistant", "content": refusal}
    elif include_assistant or not (
        isinstance(last, dict) and last.get("role") == "assistant"
    ):
        updated.append({"role": "assistant", "content": refusal})
    else:
        updated[-1] = {"role": "assistant", "content": refusal}
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": True,
        "tool_calls": [],
        "final_response": refusal,
        "honesty_nudge_count": int(honesty_nudge_count),
    }


def _tools_include_name(tools: list[Any] | None, name: str) -> bool:
    if not tools:
        return False
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else {}
        n = (fn or {}).get("name") or t.get("name")
        if isinstance(n, str) and n.strip() == name:
            return True
    return False


def resolve_tool_choice(
    state: dict[str, Any],
    messages: list[dict[str, Any]] | None,
    *,
    tools: list[Any] | None = None,
) -> str | dict[str, Any]:
    """Return OpenAI tool_choice for this ReAct step."""
    if not tools:
        return "auto"
    if sdd_fill_requires_tools(
        messages,
        tool_results=state.get("tool_results") if isinstance(state, dict) else None,
        user_input=state.get("user_input") if isinstance(state, dict) else None,
    ):
        # Prefer a forced function call when the schema is available (stronger
        # than tool_choice=required, which some gateways treat loosely).
        if _tools_include_name(tools, "sdd_write_artifact"):
            return {
                "type": "function",
                "function": {"name": "sdd_write_artifact"},
            }
        return "required"
    return "auto"
