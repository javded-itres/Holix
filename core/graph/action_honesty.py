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

# Model denies tool visibility despite successful list_directory / ls results.
_EMPTY_OR_DEAF_CLAIM = re.compile(
    r"(?is)("
    r"workspace\s+(practically\s+)?(is\s+)?empty"
    r"|workspace\s+пуст"
    r"|воркспейс\s+пуст"
    r"|рабоч(ая|ей)\s+директор(ия|ии)\s+пуст"
    r"|нет\s+папк[иа]\s+"
    r"|нет\s+ни\s+одной\s+директор"
    r"|нет\s+ни\s+одного\s+(файл|проект|каталог)"
    r"|ноль\s+каталог"
    r"|вижу\s+ноль"
    r"|проект[а]?\s+.+\s+нигде\s+нет"
    r"|проект[а]?\s+.+\s+нет\b"
    r"|самой\s+папки\s+сейчас\s+.+\s+нет"
    r"|физически\s+отсутств"
    r"|tools?\s+(return|returned|are)\s+empty"
    r"|пустые?\s+ответы?"
    r"|пустой\s+результат"
    r"|пустые?\s+результат"
    r"|вернули\s+пусто"
    r"|вернул[аи]?\s+пусто"
    r"|дали\s+пусто"
    r"|дал[аи]?\s+пусто"
    r"|пусто/null"
    r"|пусто\s*/\s*null"
    r"|возвращают\s+пуст"
    r"|упрямо\s+возвраща"
    r"|не\s+возвращают\s+(никакого\s+)?результат"
    r"|глухонемая\s+сред"
    r"|глух(ая|ой)\s+сред"
    r"|инструменты\s+(молчат|не\s+работают|не\s+отвечают|не\s+видят)"
    r"|тул[ыа]?\s+(молчат|пуст|не\s+работа)"
    r"|команды\s+вернул"
    r"|list_directory\s+.+\s+(пуст|глюч|empty)"
    r"|не\s+могу\s+(сейчас\s+)?(дать|увидеть|прочитать|перечитать)\s+"
    r"|не\s+вижу\s+(полн|содерж|файл|директор|workspace|воркспейс|ни\s)"
    r"|unable\s+to\s+(see|list|read)\s+(the\s+)?(workspace|directory|filesystem)"
    r"|no\s+(visible\s+)?(project|directory|files?)\s+(in\s+)?(the\s+)?workspace"
    r"|without\s+confirmation\s+from\s+(the\s+)?workspace"
    r"|без\s+подтверждения\s+из\s+workspace"
    r"|без\s+успешных\s+ответов\s+тул"
    r"|данных,?\s+которых\s+не\s+было"
    r")"
)

_LISTING_MARKERS = (
    "[dir]",
    "[file]",
    "contents of",
    "success (exit code 0)",
    "total ",
    '"ok": true',
    '"ok":true',
    '"projects"',
    "content of ",
)

# Dir/file names listed by tools this turn.
_LISTED_NAME_RE = re.compile(
    r"(?im)^(?:\[(?:DIR|FILE)\]\s+|drwx|[-d][rwx-]{9}\s+\d+\s+\S+\s+\S+\s+\d+\s+\S+\s+\d+\s+\d+:\d+\s+)?([A-Za-z0-9][A-Za-z0-9_.-]{1,80})\s*$"
)
_DENIES_NAME_RE = re.compile(
    r"(?is)("
    r"нет\s+(?:ни\s+)?(?:проекта\s+|папки\s+|каталога\s+|файла\s+)?"
    r"|отсутств\w*\s+"
    r"|не\s+(?:вижу|нашёл|нашел|нашла)\s+"
    r"|missing\s+"
    r"|does\s+not\s+exist"
    r")"
)

WORKSPACE_GROUNDING_NUDGE = (
    "[Action honesty — workspace] You claimed the workspace is empty or that "
    "tools returned nothing, but this turn already has successful listing "
    "results (list_directory / run_terminal_command with directories or files). "
    "Those tool results are ground truth. Do NOT say tools are deaf/empty. "
    "Re-read the tool outputs in this turn, name the directories/files they show, "
    "and continue the user task using relative paths only (not ~, /, $HOLIX_HOME). "
    "A single blocked path outside the jail does not erase successful listings."
)

_MAX_WORKSPACE_GROUNDING_NUDGES = 2

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


def extract_workspace_listing_evidence(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
    max_chars: int = 1800,
) -> str:
    """Collect recent successful listing payloads for forced user-facing correction."""
    chunks: list[str] = []

    def _take(label: str, content: str) -> None:
        body = (content or "").strip()
        if not body:
            return
        useful = _listing_evidence_from_content(body) or (
            '"ok"' in body.lower() and "true" in body.lower()
        )
        if not useful:
            return
        if len(body) > 600:
            body = body[:600].rstrip() + "…"
        chunks.append(f"**{label}:**\n```\n{body}\n```")

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
            name = _tool_name_from_message(msg, id_to_name) or "tool"
            _take(name, content)
    if not chunks and tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            content = raw if isinstance(raw, str) else str(raw or "")
            name = str(tr.get("tool_name") or "tool")
            _take(name, content)

    if not chunks:
        return ""
    joined = "\n\n".join(chunks[-4:])
    if len(joined) > max_chars:
        return joined[:max_chars].rstrip() + "…"
    return joined


def workspace_grounding_refusal_text(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> str:
    """User-visible correction when the model keeps denying visible tool listings."""
    evidence = extract_workspace_listing_evidence(
        messages, tool_results=tool_results
    )
    head = (
        "Инструменты в этом ходе **уже вернули непустой результат** "
        "(list_directory / terminal). Утверждение «tools пустые / workspace пуст / "
        "глухая среда» — ошибка модели, а не инфраструктуры.\n\n"
        "Ниже — фактические ответы tools из этого хода:\n\n"
    )
    if evidence:
        return head + evidence + (
            "\n\nПродолжаю задачу, опираясь на эти listing'и "
            "(относительные пути, без `~` / `$HOLIX_HOME`)."
        )
    return head + "(listing evidence present but could not be formatted)."


def claims_empty_or_deaf_tools(text: str | None) -> bool:
    """True when the assistant claims workspace/tools show nothing."""
    content = (text or "").strip()
    if not content or len(content) < 12:
        return False
    return bool(_EMPTY_OR_DEAF_CLAIM.search(content))


def _listing_evidence_from_content(content: str) -> bool:
    """True if a tool payload clearly lists workspace entries or a successful ls."""
    c = (content or "").strip()
    if not c or _tool_result_failed(c):
        return False
    lower = c.lower()
    if any(m in lower for m in _LISTING_MARKERS):
        return True
    # Relative name dumps like "it-resources-site\nit_rs_vue"
    lines = [ln.strip() for ln in c.splitlines() if ln.strip()]
    if 1 <= len(lines) <= 40 and all(
        not ln.lower().startswith("error") and "/" not in ln[:1] for ln in lines
    ):
        # at least one non-meta line that looks like a filename/dirname
        if any(
            re.match(r"^[A-Za-z0-9_.][A-Za-z0-9_.\-]*$", ln) and ln not in {"Success", "STDOUT:", "STDERR:"}
            for ln in lines
        ):
            return True
    return False


def has_successful_workspace_listing(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if list_directory / terminal already returned a usable listing this turn."""
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
            name = _tool_name_from_message(msg, id_to_name).lower()
            if name in {
                "list_directory",
                "run_terminal_command",
                "terminal",
                "read_file",
                "sdd_list_projects",
                "sdd_list_specs",
                "sdd_list_changes",
                "sdd_status",
                "sdd_init",
            } or not name:
                if _listing_evidence_from_content(content):
                    return True
    if tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            content = raw if isinstance(raw, str) else str(raw or "")
            name = str(tr.get("tool_name") or "").lower()
            if name in {
                "list_directory",
                "run_terminal_command",
                "terminal",
                "read_file",
                "sdd_list_projects",
                "sdd_list_specs",
                "sdd_list_changes",
                "sdd_status",
                "sdd_init",
            } or not name:
                if _listing_evidence_from_content(content):
                    return True
    return False


def _collect_listed_entry_names(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Entry names visible in successful tool listings this turn."""
    names: set[str] = set()
    skip = {
        "total",
        "success",
        "stdout",
        "stderr",
        "ok",
        "path",
        "label",
        "projects",
        "workspace",
        "initialized",
        "content",
        "of",
        "drwxrws---",
        "drwxr-xr-x",
        "..",
        ".",
    }

    def _absorb(content: str) -> None:
        if not _listing_evidence_from_content(content):
            return
        for line in content.splitlines():
            m = _LISTED_NAME_RE.match(line.strip())
            if not m:
                # also [DIR]  name form
                m2 = re.match(r"^\[(?:DIR|FILE)\]\s+(\S+)", line.strip(), re.I)
                if not m2:
                    continue
                name = m2.group(1).strip().rstrip("/")
            else:
                name = m.group(1).strip().rstrip("/")
            low = name.lower()
            if low in skip or len(name) < 2:
                continue
            if name.startswith("-") or name.startswith("total"):
                continue
            names.add(name)
        # JSON project paths from sdd_list_projects
        for m in re.finditer(r'"path"\s*:\s*"([^"]+)"', content):
            p = m.group(1).strip().strip("/")
            if p and p not in skip:
                names.add(p.split("/")[0])
        for m in re.finditer(r'"label"\s*:\s*"([^"]+)"', content):
            p = m.group(1).strip()
            if p and p not in {".", *skip}:
                names.add(p)

    if messages:
        last_user = -1
        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user = i
        for msg in messages[last_user + 1 :]:
            if msg.get("role") != "tool":
                continue
            raw = msg.get("content")
            _absorb(raw if isinstance(raw, str) else str(raw or ""))
    if tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            _absorb(raw if isinstance(raw, str) else str(raw or ""))
    return names


def denies_names_shown_by_tools(
    text: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if the model says a tool-listed name is missing."""
    content = (text or "").strip()
    if not content or not _DENIES_NAME_RE.search(content):
        return False
    listed = _collect_listed_entry_names(messages, tool_results=tool_results)
    if not listed:
        return False
    lower = content.lower()
    for name in listed:
        if name.lower() in lower and re.search(
            rf"(?is)(нет|отсутств|не\s+вижу|не\s+нашёл|не\s+нашел|missing|does\s+not\s+exist).{{0,40}}{re.escape(name)}|{re.escape(name)}.{{0,40}}(нет|отсутств|не\s+вижу|missing)",
            content,
        ):
            return True
        # weaker: name + empty-claim nearby
        if name.lower() in lower and claims_empty_or_deaf_tools(content):
            return True
    return False


def denies_visible_workspace(
    text: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True when the model claims empty/deaf tools despite successful listings."""
    if not has_successful_workspace_listing(messages, tool_results=tool_results):
        # also treat sdd_list_projects JSON as listing evidence
        if not _has_sdd_or_json_listing(messages, tool_results=tool_results):
            return False
    if claims_empty_or_deaf_tools(text):
        return True
    if denies_names_shown_by_tools(text, messages, tool_results=tool_results):
        return True
    return False


def _has_sdd_or_json_listing(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True for successful sdd_list_* / JSON project listings this turn."""
    def _ok(content: str, name: str = "") -> bool:
        c = (content or "").strip()
        if not c or _tool_result_failed(c):
            return False
        low = c.lower()
        n = (name or "").lower()
        if "sdd_list" in n or "sdd_status" in n or "sdd_init" in n:
            return '"ok"' in low and "true" in low
        if '"projects"' in low and '"ok"' in low:
            return True
        return False

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
            if _ok(content, _tool_name_from_message(msg, id_to_name)):
                return True
    if tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            content = raw if isinstance(raw, str) else str(raw or "")
            if _ok(content, str(tr.get("tool_name") or "")):
                return True
    return False


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
    tool_results: list[dict[str, Any]] | None = None,
) -> int:
    user = (user_input or "").strip() or last_user_text(messages)
    if is_sdd_fill_request(user) or claims_sdd_artifacts_filled(final_response):
        return _MAX_SDD_FILL_HONESTY_NUDGES
    if denies_visible_workspace(
        final_response, messages, tool_results=tool_results
    ):
        return _MAX_WORKSPACE_GROUNDING_NUDGES
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
    tool_results = state.get("tool_results") if isinstance(state, dict) else None
    max_nudges = _max_nudges_for_turn(
        messages,
        final_response=final_response,
        user_input=user_input,
        tool_results=tool_results,
    )
    if int(state.get("honesty_nudge_count") or 0) >= max_nudges:
        return False
    # Plan executor has its own tool-progress nudge.
    if _plan_mode_skips_honesty(state):
        return False
    if lacks_evidence_for_claim(
        final_response,
        messages,
        tool_results=tool_results,
        user_input=user_input,
    ):
        return True
    if denies_visible_workspace(
        final_response,
        messages,
        tool_results=tool_results,
    ):
        return True
    # SDD fill turn: never end with pure text before any sdd_write_artifact.
    if sdd_fill_requires_tools(
        messages,
        tool_results=tool_results,
        user_input=user_input,
    ) and (final_response or "").strip():
        return True
    return ends_turn_on_unexecuted_intent(final_response, messages)


def should_refuse_false_empty_workspace(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """After workspace grounding nudges, replace persistent 'empty tools' lies."""
    if _plan_mode_skips_honesty(state):
        return False
    tool_results = state.get("tool_results") if isinstance(state, dict) else None
    if not denies_visible_workspace(
        final_response, messages, tool_results=tool_results
    ):
        return False
    max_nudges = _max_nudges_for_turn(
        messages,
        final_response=final_response,
        user_input=state.get("user_input") if isinstance(state, dict) else None,
        tool_results=tool_results,
    )
    return int(state.get("honesty_nudge_count") or 0) >= max_nudges


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
    if is_sdd_fill_request(user) or claims_sdd_artifacts_filled(final_response):
        nudge = SDD_FILL_HONESTY_NUDGE
    elif denies_visible_workspace(final_response, updated):
        nudge = WORKSPACE_GROUNDING_NUDGE
    else:
        nudge = ACTION_HONESTY_NUDGE
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
    refusal: str | None = None,
) -> dict[str, Any]:
    """Replace an unproven claim with an honest failure / evidence final."""
    updated = list(messages)
    body = (refusal or SDD_FILL_HONESTY_REFUSAL).strip()
    last = updated[-1] if updated else None
    if (
        isinstance(last, dict)
        and last.get("role") == "assistant"
        and (
            include_assistant
            or (final_response and (last.get("content") or "") == final_response)
            or claims_sdd_artifacts_filled(str(last.get("content") or ""))
            or claims_action_completed(str(last.get("content") or ""))
            or claims_empty_or_deaf_tools(str(last.get("content") or ""))
        )
    ):
        updated[-1] = {"role": "assistant", "content": body}
    elif include_assistant or not (
        isinstance(last, dict) and last.get("role") == "assistant"
    ):
        updated.append({"role": "assistant", "content": body})
    else:
        updated[-1] = {"role": "assistant", "content": body}
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": True,
        "tool_calls": [],
        "final_response": body,
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
