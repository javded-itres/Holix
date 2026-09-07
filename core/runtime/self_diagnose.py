"""Inspect the current session: full history, failures, next actions."""

from __future__ import annotations

import re
from typing import Any

SELF_DIAGNOSE_TOOL = "self_diagnose"

_SEND_ASK = re.compile(
    r"(?is)("
    r"пришли\s+(в\s+чат\s+)?файл"
    r"|отправь\s+(в\s+чат\s+)?файл"
    r"|send\s+(me\s+)?(the\s+)?file"
    r"|пришли\s+\w+\.(md|pdf|docx|xlsx|png|jpg)"
    r"|файлы\s+md"
    r")"
)
_SEND_CLAIM = re.compile(
    r"(?is)("
    r"отправил[аи]?\s+(файл|оба\s+файла|в\s+чат)"
    r"|вот\s+оба\s+файла"
    r"|полностью\s+в\s+чат"
    r"|sent\s+(the\s+)?file"
    r"|files?\s+sent"
    r")"
)
_REPEAT_COMPLAINT = re.compile(
    r"(?is)("
    r"не\s+вижу\s+файл"
    r"|отправь\s+ещ[её]\s+раз"
    r"|ты\s+так\s+и\s+не\s+прислал"
    r"|i\s+(can'?t|cannot)\s+see\s+the\s+file"
    r"|resend"
    r")"
)
_GUESSED_PATH = re.compile(
    r"/admin|/dashboard|/employee|/cabinet|/login|/wp-admin",
    re.IGNORECASE,
)
_WRONG_DELIVERY_STEP = re.compile(
    r"(?is)(read_file|`cat`|\bsplit\s+-l|\bsplit\s+-c)",
)
_USER_UNHAPPY = re.compile(
    r"(?is)("
    r"не\s+(так|то|работает|вижу|получил|приш[её]л|сделал)"
    r"|неправильно|ошибк|слом|опять|ещ[её]\s+раз"
    r"|wrong|broken|failed|still\s+not|doesn'?t\s+work|not\s+working"
    r")"
)
_DIAGNOSE_PHRASE = re.compile(
    r"(?is)(проверь\s+себя|самодиагност|check\s+yourself|self[- ]diagnos|"
    r"проанализируй\s+(свою\s+)?сессию)"
)
_ERROR_HINT = re.compile(
    r"(?is)(\berror\b|traceback|exception|failed|HTTP\s+[45]\d\d|"
    r"\"ok\":\s*false|'ok':\s*False|не найден|permission denied|timeout)"
)
_STEP_LIMIT = re.compile(r"(?is)(max[_ ]steps|лимит\s+шагов|step\s+limit|step budget)")

SESSION_HISTORY_LIMIT = 500
TRAJECTORY_HISTORY_LIMIT = 2000

_DELIVERY_FIX_PROCEDURE = """## Procedure
1. Confirm the file exists (`list_directory` or `ls -l <path>`).
2. Deliver it as a **chat attachment**: `send_chat_files(paths=["<absolute path>"])`.
   2–10 files in one call become a Telegram album.
3. Success only if the tool result starts with `Sent `.
4. If the user still cannot see the file, call `send_chat_files` again on the same path.
   Do not `split` / `cat` / `read_file` the file into chat text.

## Pitfalls
- `read_file`, `cat`, and assistant markdown are **not** Telegram/MAX attachments.
- Do not claim the file was sent unless the tool returned `Sent N file(s)`.
- Do not delete the original unless the user asked.
"""


def _roles(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        raw = msg.get("content")
        content = raw if isinstance(raw, str) else str(raw or "")
        out.append((role, content))
    return out


def _llm_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for r in rows if str(r.get("type") or "") == "llm_call_completed"]
    errors = [r for r in rows if str(r.get("type") or "") == "error"]
    models: dict[str, int] = {}
    reasons: dict[str, int] = {}
    tokens = 0
    for row in calls:
        model = str(row.get("model") or "") or "unknown"
        models[model] = models.get(model, 0) + 1
        reason = str(row.get("finish_reason") or "") or "unknown"
        reasons[reason] = reasons.get(reason, 0) + 1
        try:
            tokens += int(row.get("total_tokens") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "llm_calls": len(calls),
        "models": models,
        "finish_reasons": reasons,
        "total_tokens": tokens,
        "errors": [str(e.get("error") or e.get("message") or "")[:240] for e in errors[-5:] if e],
        "note": (
            "Raw HTTP prompts/completions are not stored (secrets). "
            "This report reconstructs model I/O from conversation + trajectory."
        ),
    }


def _section(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$",
    )
    match = pattern.search(content or "")
    if not match:
        return ""
    start = match.end()
    nxt = re.search(r"(?im)^##\s+\S", content[start:])
    end = start + nxt.start() if nxt else len(content)
    return content[start:end]


def is_wrong_chat_delivery_skill(content: str, description: str = "") -> bool:
    blob = f"{description}\n{content}".lower()
    talks = any(
        key in blob
        for key in (
            "чат",
            "telegram",
            "send_chat",
            "пришли файл",
            "отправь файл",
            "in chat",
            "file-delivery",
            "file delivery",
        )
    )
    if not talks:
        return False
    procedure = _section(content, "Procedure") or content
    if "send_chat_files" in procedure.lower():
        return bool(re.search(r"(?is)отправь.{0,120}(read_file|split\s+-)", procedure))
    return bool(_WRONG_DELIVERY_STEP.search(procedure))


def rewrite_delivery_skill(content: str) -> str | None:
    """Replace Procedure/Pitfalls that teach cat/read_file as chat delivery."""
    if not is_wrong_chat_delivery_skill(content):
        return None
    body = content
    for heading in ("Procedure", "Pitfalls"):
        pattern = re.compile(rf"(?ims)^##\s+{heading}\s*$")
        match = pattern.search(body)
        if not match:
            continue
        start = match.start()
        nxt = re.search(r"(?im)^##\s+\S", body[match.end() :])
        end = match.end() + nxt.start() if nxt else len(body)
        body = body[:start] + body[end:].lstrip("\n")
    # Keep When to Use / Verification; inject corrected procedure before Verification.
    ver = re.search(r"(?im)^##\s+Verification\s*$", body)
    insert = _DELIVERY_FIX_PROCEDURE.rstrip() + "\n\n"
    if ver:
        body = body[: ver.start()] + insert + body[ver.start() :]
    else:
        body = body.rstrip() + "\n\n" + insert
    return body


def _clip(text: str, n: int = 180) -> str:
    raw = " ".join((text or "").split())
    if len(raw) <= n:
        return raw
    return raw[: n - 1] + "…"


def _json_ok_false(content: str) -> bool:
    blob = (content or "").lstrip()
    if not blob.startswith("{"):
        return False
    try:
        import json

        data = json.loads(blob)
    except Exception:
        return False
    return isinstance(data, dict) and data.get("ok") is False


def _looks_failed(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return True
    low = text.lower()
    if low.startswith("error"):
        return True
    if _json_ok_false(text):
        return True
    return bool(_ERROR_HINT.search(text[:2000]))


def _tool_calls_from_assistant(msg: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str((fn or {}).get("name") or tc.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _id_to_tool_name(messages: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for msg in messages:
        if str(msg.get("role") or "") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tid = tc.get("id")
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str((fn or {}).get("name") or tc.get("name") or "").strip()
            if isinstance(tid, str) and tid and name:
                out[tid] = name
    return out


def _tools_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_to_name = _id_to_tool_name(messages)
    rows: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        if role == "assistant":
            for name in _tool_calls_from_assistant(msg):
                rows.append({"name": name, "ok": None, "source": "assistant_call"})
            continue
        if role != "tool":
            continue
        raw = msg.get("content")
        content = raw if isinstance(raw, str) else str(raw or "")
        name = str(msg.get("name") or msg.get("tool_name") or "").strip()
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        if not name:
            name = str(meta.get("tool_name") or meta.get("name") or "").strip()
        tid = msg.get("tool_call_id")
        if not name and isinstance(tid, str):
            name = id_to_name.get(tid, "")
        name = name or "tool"
        rows.append(
            {
                "name": name,
                "ok": not _looks_failed(content),
                "excerpt": _clip(content, 160),
                "source": "message",
            }
        )
    return rows


def _tools_from_trajectory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        etype = str(row.get("type") or "")
        name = str(row.get("tool_name") or row.get("name") or "").strip()
        if etype == "tool_call_start" and name:
            out.append({"name": name, "ok": None, "source": "traj_start"})
        elif etype == "tool_call_result" and name:
            blob = str(row.get("result") or row.get("content") or "")
            out.append(
                {
                    "name": name,
                    "ok": not _looks_failed(blob),
                    "excerpt": _clip(blob, 160),
                    "source": "traj_result",
                }
            )
        elif etype == "tool_call_error":
            blob = str(row.get("error") or row.get("message") or row.get("result") or "")
            out.append(
                {
                    "name": name or "tool",
                    "ok": False,
                    "excerpt": _clip(blob, 160),
                    "source": "traj_error",
                }
            )
    return out


def _merged_tool_names(*groups: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for group in groups:
        for row in group:
            name = str(row.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _session_timeline(
    messages: list[dict[str, Any]],
    trajectory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compact autopsy the answering model can use for any session problem."""
    events: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        raw = msg.get("content")
        content = raw if isinstance(raw, str) else str(raw or "")
        if role == "user":
            kind = (
                "user_diagnose"
                if _DIAGNOSE_PHRASE.search(content) and len(content) < 80
                else "user"
            )
            events.append({"kind": kind, "text": _clip(content, 160)})
        elif role == "assistant":
            names = _tool_calls_from_assistant(msg)
            events.append(
                {
                    "kind": "assistant",
                    "text": _clip(content, 140),
                    "tools": names[:8],
                }
            )
        elif role == "tool":
            events.append({"kind": "tool", "text": _clip(content, 120)})
    for row in trajectory:
        etype = str(row.get("type") or "")
        if etype == "max_steps_reached":
            events.append(
                {
                    "kind": "max_steps",
                    "text": f"max_steps={row.get('max_steps') or row.get('steps') or '?'}",
                }
            )
        elif etype == "error":
            events.append(
                {
                    "kind": "error",
                    "text": _clip(str(row.get("error") or row.get("message") or ""), 160),
                }
            )
    return events[-60:]


def _tools_after_last_real_user(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last = -1
    for i, msg in enumerate(messages):
        if str(msg.get("role") or "") != "user":
            continue
        raw = msg.get("content")
        text = raw if isinstance(raw, str) else str(raw or "")
        if _DIAGNOSE_PHRASE.search(text) and len(text) < 120:
            continue
        last = i
    if last < 0:
        return _tools_from_messages(messages)
    return _tools_from_messages(messages[last + 1 :])


def _finding(
    code: str,
    title: str,
    *,
    severity: str = "medium",
    detail: str = "",
    evidence: dict[str, Any] | None = None,
    next_action: str = "",
    actor: str = "agent",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence": evidence or {},
        "next_action": next_action,
        "actor": actor,  # agent | user | auto
    }


def diagnose_session(
    *,
    complaint: str = "",
    messages: list[dict[str, Any]] | None = None,
    trajectory: list[dict[str, Any]] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure analysis — no I/O. Returns a JSON-serializable report."""
    msgs = list(messages or [])
    rows = list(trajectory or [])
    skill_rows = list(skills or [])
    findings: list[dict[str, Any]] = []
    turns = _roles(msgs)
    users = [c for r, c in turns if r == "user"]
    assistants = [c for r, c in turns if r == "assistant"]
    tools_msg = _tools_from_messages(msgs)
    tools_traj_rows = _tools_from_trajectory(rows)
    names_all = _merged_tool_names(tools_msg, tools_traj_rows)
    tool_set = set(names_all)
    failed = [t for t in tools_msg + tools_traj_rows if t.get("ok") is False]
    ok_names = {str(t.get("name")) for t in tools_msg + tools_traj_rows if t.get("ok") is True}

    send_asked = any(_SEND_ASK.search(u) for u in users) or bool(_SEND_ASK.search(complaint))
    send_claimed = any(_SEND_CLAIM.search(a) for a in assistants)
    if send_asked and "send_chat_files" not in tool_set:
        substitutes = [
            n for n in names_all if n in {"read_file", "run_terminal_command", "write_file"}
        ]
        findings.append(
            _finding(
                "claimed_file_send_without_tool",
                "User asked to send a file; send_chat_files was never called",
                severity="high",
                detail=(
                    "Chat text / cat / read_file is not a Telegram/MAX attachment. "
                    "Call send_chat_files on the real path."
                ),
                evidence={
                    "send_claimed_in_assistant": send_claimed,
                    "tools_used": names_all[-24:],
                    "substitutes": substitutes[-12:],
                    "tool_search_used": "tool_search" in tool_set,
                },
                next_action="send_chat_files(paths=[...]) then quote the Sent … result",
                actor="agent",
            )
        )

    repeats = [u for u in users if _REPEAT_COMPLAINT.search(u)]
    if len(repeats) >= 2:
        findings.append(
            _finding(
                "repeated_user_complaint",
                "User repeated that they cannot see the result",
                severity="high",
                detail="The agent kept the same approach after the complaint.",
                evidence={"complaints": [_clip(u, 160) for u in repeats[-4:]]},
                next_action="Change the tool (do not repeat cat/read_file).",
                actor="agent",
            )
        )

    unhappy = [
        u
        for u in users
        if _USER_UNHAPPY.search(u) and not (_DIAGNOSE_PHRASE.search(u) and len(u) < 120)
    ]
    if len(unhappy) >= 2 and not any(f["code"] == "repeated_user_complaint" for f in findings):
        findings.append(
            _finding(
                "repeated_user_dissatisfaction",
                "User said more than once that the work is wrong or incomplete",
                severity="high",
                detail="Do not repeat the same approach. Use findings + last user ask.",
                evidence={"complaints": [_clip(u, 160) for u in unhappy[-5:]]},
                next_action="Address the last real user request with a different tool path.",
                actor="agent",
            )
        )

    fetch_starts = [n for n in names_all if n in {"fetch_url", "web_fetch"}]
    fetch_404 = 0
    guessed = 0
    for row in rows:
        name = str(row.get("tool_name") or "")
        if name not in {"fetch_url", "web_fetch"}:
            continue
        blob = str(row.get("result") or row.get("content") or row.get("arguments_raw") or "")
        if str(row.get("type") or "") == "tool_call_result" and (
            "HTTP 404" in blob or "HTTP 403" in blob
        ):
            fetch_404 += 1
        if _GUESSED_PATH.search(blob):
            guessed += 1
    if len(fetch_starts) >= 8 and (fetch_404 >= 3 or guessed):
        findings.append(
            _finding(
                "fetch_url_guessing_loop",
                "Many fetch_url calls with failures or invented paths",
                severity="medium",
                detail="Follow ## Links on this page; use research_site_pages for many same-host URLs.",
                evidence={
                    "fetch_url_count": len(fetch_starts),
                    "http_404_or_403": fetch_404,
                },
                next_action="Stop guessing paths; fetch the user URL then research_site_pages.",
                actor="agent",
            )
        )

    if failed:
        by_name: dict[str, int] = {}
        for item in failed:
            by_name[str(item.get("name") or "tool")] = (
                by_name.get(str(item.get("name") or "tool"), 0) + 1
            )
        findings.append(
            _finding(
                "tool_failures",
                f"{len(failed)} failed tool result(s) in this session",
                severity="high" if len(failed) >= 3 else "medium",
                detail="Quote the error and retry with a different command/path; do not claim success.",
                evidence={
                    "counts": by_name,
                    "samples": [
                        {"name": t.get("name"), "excerpt": t.get("excerpt")} for t in failed[-6:]
                    ],
                },
                next_action="Fix or retry the failed tools; tell the user the actual error.",
                actor="agent",
            )
        )

    from core.graph.action_honesty import claims_action_completed

    claimed = [a for a in assistants if claims_action_completed(a)]
    if claimed:
        last_claim = claimed[-1]
        write_ok = bool(
            ok_names.intersection(
                {
                    "write_file",
                    "patch_file",
                    "apply_patch",
                    "sdd_write_artifact",
                    "sdd_archive",
                    "send_chat_files",
                }
            )
        )
        if not write_ok:
            findings.append(
                _finding(
                    "false_completion_claim",
                    "Assistant claimed work was done without a successful write/send tool",
                    severity="high",
                    detail="Honesty: do not repeat «готово». Call the missing tool or admit it failed.",
                    evidence={"claim": _clip(last_claim, 200), "ok_tools": sorted(ok_names)[-16:]},
                    next_action="Perform the claimed action with tools, or correct the claim.",
                    actor="agent",
                )
            )

    counts: dict[str, int] = {}
    for name in names_all:
        counts[name] = counts.get(name, 0) + 1
    loop_name, loop_n = max(counts.items(), key=lambda kv: kv[1]) if counts else ("", 0)
    if loop_n >= 12 and loop_name not in {"self_diagnose"}:
        findings.append(
            _finding(
                "tool_loop",
                f"Tool `{loop_name}` ran {loop_n} times",
                severity="medium",
                detail="Likely stuck. Stop repeating it; change strategy or ask the user.",
                evidence={"tool": loop_name, "count": loop_n},
                next_action=f"Stop calling `{loop_name}`; pick another tool or ask the user.",
                actor="agent",
            )
        )

    aborted = any(_STEP_LIMIT.search(a) for a in assistants) or any(
        str(r.get("type") or "") == "max_steps_reached" for r in rows
    )
    if aborted:
        findings.append(
            _finding(
                "step_limit",
                "The run hit the step budget",
                severity="medium",
                detail="Work may be incomplete. Continue only if the last ask is still open.",
                evidence={"max_steps_events": True},
                next_action="If the task is unfinished: continue (user Continue / /steps) then finish with tools.",
                actor="user",
            )
        )

    last_real_users = [u for u in users if not (_DIAGNOSE_PHRASE.search(u) and len(u) < 120)]
    last_ask = last_real_users[-1] if last_real_users else ""
    after = _tools_after_last_real_user(msgs)
    after_ok = [t for t in after if t.get("ok") is True and t.get("name") != "self_diagnose"]
    actiony = bool(
        re.search(
            r"(?is)(сделай|исправ|почин|залей|задеплой|пришли|отправ|напиши|архив|"
            r"fix|implement|deploy|send|write|archive|create)",
            last_ask,
        )
    )
    if last_ask and not after_ok and not send_asked and (actiony or len(unhappy) >= 1):
        findings.append(
            _finding(
                "no_progress_on_latest_ask",
                "Latest user request has no successful tool work after it",
                severity="high",
                detail="The diagnose turn does not count. Execute the last real ask.",
                evidence={
                    "last_ask": _clip(last_ask, 220),
                    "tools_after": [t.get("name") for t in after][-12:],
                },
                next_action="Do the last user request with tools now.",
                actor="agent",
            )
        )

    delivery_issue = any(
        f["code"] in {"claimed_file_send_without_tool", "repeated_user_complaint"} for f in findings
    )
    skill_hits: list[dict[str, Any]] = []
    if delivery_issue:
        for skill in skill_rows:
            name = str(skill.get("name") or "")
            content = str(skill.get("content") or "")
            desc = str(skill.get("description") or "")
            if not name:
                continue
            if is_wrong_chat_delivery_skill(content, desc):
                skill_hits.append(
                    {
                        "name": name,
                        "reason": "Procedure teaches read_file/cat/split as chat delivery",
                        "protected": bool(skill.get("protected")),
                    }
                )
        if skill_hits:
            findings.append(
                _finding(
                    "skill_teaches_wrong_delivery",
                    "A live skill taught the wrong way to send files",
                    severity="high",
                    detail="That skill should call send_chat_files, not dump text.",
                    evidence={"skills": skill_hits},
                    next_action="Patch the skill Procedure (this tool can stage the fix).",
                    actor="auto",
                )
            )

    traj_skills = [
        str(r.get("skill_name") or "")
        for r in rows
        if str(r.get("type") or "") in {"skill_proposed", "skill_approved"} and r.get("skill_name")
    ]
    auto = [
        str(r.get("skill_name") or "")
        for r in rows
        if str(r.get("type") or "") == "skill_proposed" and r.get("auto_applied")
    ]

    plan = _build_plan(findings, last_ask=last_ask)
    if findings:
        high = [f for f in findings if f.get("severity") == "high"]
        summary = (high[0] if high else findings[0])["title"]
    else:
        summary = (
            "No matching heuristic; use session.timeline and last user ask to decide "
            "what still needs doing."
        )
    return {
        "ok": True,
        "complaint": (complaint or "").strip()[:400],
        "summary": summary,
        "findings": findings,
        "plan": plan,
        "session": {
            "user_turns": len(users),
            "assistant_turns": len(assistants),
            "message_count": len(msgs),
            "trajectory_events": len(rows),
            "recent_user": [_clip(u, 200) for u in users[-8:]],
            "last_real_ask": _clip(last_ask, 240),
            "tools": names_all[-40:],
            "distinct_tools": sorted(tool_set),
            "failed_tools": [
                {"name": t.get("name"), "excerpt": t.get("excerpt")} for t in failed[-8:]
            ],
            "skill_events": traj_skills[-8:],
            "auto_applied_skills": auto[-8:],
            "timeline": _session_timeline(msgs, rows),
        },
        "llm": _llm_stats(rows),
        "how_to_answer": (
            "1) Explain findings in the user's language, citing codes. "
            "2) Immediately do plan.do_now with tools (do not only talk). "
            "3) Ask the user only about plan.ask_user. "
            "4) Mention skill_fixes only if a skill finding exists. "
            "5) Do not claim the original task is done unless a later tool proves it."
        ),
    }


def _build_plan(findings: list[dict[str, Any]], *, last_ask: str = "") -> dict[str, Any]:
    do_now: list[dict[str, Any]] = []
    ask_user: list[dict[str, Any]] = []
    auto_fix: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        code = str(finding.get("code") or "")
        if code in seen:
            continue
        seen.add(code)
        actor = str(finding.get("actor") or "agent")
        item = {
            "code": code,
            "action": finding.get("next_action") or "",
            "title": finding.get("title") or "",
        }
        if actor == "auto":
            auto_fix.append(item)
        elif actor == "user":
            ask_user.append(item)
        else:
            do_now.append(item)
    if (
        last_ask
        and not do_now
        and not any(f.get("code") == "no_progress_on_latest_ask" for f in findings)
    ):
        do_now.append(
            {
                "code": "continue_last_ask",
                "action": "Finish the last real user request with tools.",
                "title": _clip(last_ask, 160),
            }
        )
    return {"do_now": do_now, "ask_user": ask_user, "auto_fix": auto_fix}
