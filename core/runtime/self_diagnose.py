"""Inspect the current session: tools vs claims, LLM turns, skills."""

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


def _tool_names_from_trajectory(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        if str(row.get("type") or "") != "tool_call_start":
            continue
        name = str(row.get("tool_name") or row.get("name") or "").strip()
        if name:
            names.append(name)
    return names


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
    tools_traj = _tool_names_from_trajectory(rows)
    tool_set = set(tools_traj)

    send_asked = any(_SEND_ASK.search(u) for u in users) or bool(_SEND_ASK.search(complaint))
    send_claimed = any(_SEND_CLAIM.search(a) for a in assistants)
    if send_asked and "send_chat_files" not in tool_set:
        substitutes = [
            n for n in tools_traj if n in {"read_file", "run_terminal_command", "write_file"}
        ]
        findings.append(
            {
                "code": "claimed_file_send_without_tool",
                "severity": "high",
                "title": "User asked to send a file; send_chat_files was never called",
                "detail": (
                    "Chat text / cat / read_file is not a Telegram/MAX attachment. "
                    "Call send_chat_files on the real path."
                ),
                "evidence": {
                    "send_claimed_in_assistant": send_claimed,
                    "tools_used": tools_traj[-24:],
                    "substitutes": substitutes[-12:],
                    "tool_search_used": "tool_search" in tool_set,
                },
                "next_action": "send_chat_files(paths=[...]) then quote the Sent … result",
            }
        )

    repeats = [u for u in users if _REPEAT_COMPLAINT.search(u)]
    if len(repeats) >= 2:
        findings.append(
            {
                "code": "repeated_user_complaint",
                "severity": "high",
                "title": "User repeated that they cannot see the result",
                "detail": "The agent kept the same approach after the complaint.",
                "evidence": {"complaints": [u[:160] for u in repeats[-4:]]},
                "next_action": "Change the tool (do not repeat cat/read_file).",
            }
        )

    fetch_starts = [n for n in tools_traj if n in {"fetch_url", "web_fetch"}]
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
            {
                "code": "fetch_url_guessing_loop",
                "severity": "medium",
                "title": "Many fetch_url calls with failures or invented paths",
                "detail": "Follow ## Links on this page; use research_site_pages for many same-host URLs.",
                "evidence": {
                    "fetch_url_count": len(fetch_starts),
                    "http_404_or_403": fetch_404,
                },
                "next_action": "Stop guessing paths; fetch the user URL then research_site_pages.",
            }
        )

    skill_hits: list[dict[str, Any]] = []
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
            {
                "code": "skill_teaches_wrong_delivery",
                "severity": "high",
                "title": "A live skill taught the wrong way to send files",
                "detail": "That skill should call send_chat_files, not dump text.",
                "evidence": {"skills": skill_hits},
                "next_action": "Patch the skill Procedure (this tool can stage the fix).",
            }
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

    summary = (
        findings[0]["title"]
        if findings
        else "No high-confidence failure pattern in this session slice."
    )
    return {
        "ok": True,
        "complaint": (complaint or "").strip()[:400],
        "summary": summary,
        "findings": findings,
        "session": {
            "user_turns": len(users),
            "assistant_turns": len(assistants),
            "recent_user": [u[:200] for u in users[-5:]],
            "tools": tools_traj[-40:],
            "distinct_tools": sorted(tool_set),
            "skill_events": traj_skills[-8:],
            "auto_applied_skills": auto[-8:],
        },
        "llm": _llm_stats(rows),
        "how_to_answer": (
            "Explain the findings in plain language. "
            "If claimed_file_send_without_tool: call send_chat_files next. "
            "If a skill was staged, tell the user the proposal id. "
            "Do not claim the original task is done unless a later tool proves it."
        ),
    }
