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
    r"sdd_write_artifact|sdd_update_spec"
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
    r"|sdd_update_spec"
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
# Includes progressive/future Russian verbs that leave the job half-done.
_ACTION_INTENT = re.compile(
    r"(?is)("
    r"сейчас\s+(сохран|запис|созда|удал|выполн|напиш|исправ|провер|посмотр|додела|изуч|сдела)"
    r"|сначала\s+(сдела|провер|найд|поиск|ищу|созда)"
    r"|выполняю\s+(запись|сохран|удал|операц)"
    r"|записываю\s+(план|файл|пост)"
    r"|сохран[яю]\s+(план|файл|пост)"
    # Progressive / future: «Создаю пост…» / «Сделаю…» / «Опубликую…»
    r"|\b(созда[юёмм]|создам|сдела[юем]|добавл[юю]|напиш[уем]|опублик[уююем]|"
    r"отправл[юю]|заполн[юю]|исправл[юю]|запущ[уем]|подготовл[юю]|"
    r"собира[юю]|ищу|найд[уем]|провер[юю]|откро[юю]|прочту|додела[юю])\b"
    r"|\b(смотрю|чита[юю]|открываю|работаю|изучаю|проверяю|разбираю|пишу|правлю)\b"
    r"|\b(looking\s+at|reading|opening|working\s+on|checking|inspecting|searching|"
    r"creating|making|posting|publishing|writing|adding)\b"
    r"|ищу\s+(свеж|новост|информац|статус)"
    r"|тестовый\s+пост"
    r"|через\s+`?write_file`?"
    r"|call(?:ing)?\s+`?write_file`?"
    r"|i\s+(will|am\s+going\s+to|'ll|'m\s+going\s+to)\s+"
    r"(save|write|create|delete|remove|run|execute|check|inspect|finish|look|search|post)"
    r"|writing\s+(the\s+)?file\s+(now|right\s+now)"
    r"|saving\s+(the\s+)?(plan|file)\s+(now|right\s+now)"
    r")"
)

# System truncation notice shown when finish_reason=length (not a real answer).
_TRUNCATION_NOTICE = re.compile(
    r"(?is)("
    r"ответ\s+обрезан\s+лимитом\s+токенов"
    r"|response\s+truncated\s+by\s+the\s+model\s+token\s+limit"
    r"|truncated\s+by\s+the\s+model\s+token"
    r"|лимитом\s+токенов\s+модели"
    r")"
)

# Pure planning monologue as the whole reply (no tools) — common spam pattern.
_PLAN_MONOLOGUE = re.compile(
    r"(?is)("
    r"что\s+сделаю"
    r"|^\s*начинаю\b"
    r"|\bначинаю\.?\s*$"
    r"|начну\s+с\b"
    r"|^\s*да[,.]?\s+(работаю|смотрю|читаю|открываю|провер)"
    r"|^\s*да[,.]?\s*$"
    r"|\b(работаю|смотрю|читаю|открываю)\b"
    r"|сейчас\s+(провер|посмотр|додела|сдела|изуч|откро|проч|почин|разбер|проверю)"
    r"|проверю\s+(текущ|код|процесс|состоян|файл|меню|статус|бот)"
    r"|проверяю\s+(статус|код|процесс|состоян|файл|бот|mcp)"
    r"|доделаю\s+(меню|код|функц|бот)"
    r"|изучу\s+(структуру|проект|код|репозитор|состоян)"
    r"|найду,?\s+где\b"
    r"|добавлю\s+(обработку|функц|поддержк)"
    r"|подключу\s+(агент|web_fetch|инструмент)"
    r"|сделаю\s+(генерац|тестов|пост|новост|это|так)"
    r"|\bсделаю\b"
    r"|\bсозда[юёмм]\b|\bсоздам\b"
    r"|сначала\s+сделаю"
    r"|ищу\s+(свеж|новост)"
    r"|через\s+mcp"
    r"|mcp[-_ ]?инструмент"
    r"|here'?s\s+(my\s+)?plan\b"
    r"|i\s+('ll|will)\s+(now\s+)?(start|begin|study|explore|look|add|implement|check)"
    r"|let\s+me\s+(start|begin|first|explore|look|check|read|open)"
    r"|i('ll|\s+will)\s+(check|verify|inspect|finish|look|read)\b"
    r"|i\s+am\s+(working|looking|reading|checking)\b"
    r"|план\s+(такой|действий|работы)\b"
    r"|steps?\s*:\s*$"
    r"|шаги\s*:\s*$"
    r")"
)

# Short status spam as the entire reply (no tools): «Да. Смотрю X…» / «Поняла. Проверяю…»
_STATUS_ONLY_MONOLOGUE = re.compile(
    r"(?is)^\s*"
    r"((да|понял[ао]?|хорошо|ок|ok|alright)[,.!?…]?\s*)*"
    r"("
    r"(работаю|смотрю|читаю|открываю|изучаю|проверяю|проверю|разбираю|пишу|правлю)\b"
    r"|(looking\s+at|reading|opening|working\s+on|checking|inspecting)\b"
    r").{0,280}$"
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
        "sdd_update_spec",
        "sdd_check_task",
        "sdd_set_task_assignee",
        "sdd_set_apply_mode",
        "sdd_archive",
    }
)
# Persisted artifact content (analysis docs, specs). Scaffold-only tools stay out.
_ARTIFACT_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "patch_file",
        "sdd_write_artifact",
        "sdd_update_spec",
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

CODE_MODE_NUDGE_TAIL = (
    " You are in Code mode: the only top-level tool is `run_code`. "
    "Do not call write_file, read_file, run_terminal_command, or "
    "start_background_process as native function calls. Put them inside "
    "the program as tools.name(...)."
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

MONOLOGUE_TOOL_NUDGE = (
    "[Action honesty — tools] You are only narrating progress "
    '("Смотрю…", "Поняла. Проверяю…", "Работаю…", "Looking at…") '
    "without calling tools. That spam burns tokens and loops forever. "
    "Hard limits: at most 1–2 short sentences of prose, then tool_calls — "
    "prefer zero prose. Immediately call the right tools now "
    "(read_file, list_directory, write_file, run_terminal_command, MCP tools, …). "
    "Do NOT reply with another status sentence or repeat «Поняла/Проверяю». "
    "First tool_calls, then answer from tool results only."
)

# After tools already ran: the model still only announces the next file it will write.
UNFINISHED_STEP_NUDGE = (
    "[Action honesty — unfinished] Your last message only announces the next work "
    '("Let me start with…", «Начну с…», «сейчас создам все файлы») '
    "and is not a finished result. That must not close the step. "
    "Continue with tools now: write or patch the remaining files, run tests, "
    "then report what actually exists on disk. "
    "Do not end the turn with a plan of what you will do next."
)

# Shown when the model keeps monologuing after forced tool retries.
MONOLOGUE_HONESTY_REFUSAL = (
    "Не удалось выполнить запрос: модель только описала, что «сделает» "
    "(«Создаю…», «Сделаю…», «Ищу…») и не вызвала инструменты — работа "
    "остановилась на полпути. Повторите запрос; агент должен сразу вызвать "
    "tools (read_file / write_file / run_terminal_command / search и т.д.), "
    "а не заканчивать ответ на намерении."
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
    r"|список\s+пуст"
    r"|каталог\w*\s+пуст"
    r"|директор\w*\s+пуст"
    r"|пуст(ой|ая|ое|ые)?\s+(список|каталог|workspace|воркспейс)"
    r"|сессия\s+ограничен"
    r"|текущая\s+сессия\s+ограничен"
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

# Soft text nudges alone do not stop weak models; pair with tool_choice=required.
_MAX_HONESTY_NUDGES = 3
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
    evidence = extract_workspace_listing_evidence(messages, tool_results=tool_results)
    head = (
        "Инструменты в этом ходе **уже вернули непустой результат** "
        "(list_directory / terminal). Утверждение «tools пустые / workspace пуст / "
        "глухая среда» — ошибка модели, а не инфраструктуры.\n\n"
        "Ниже — фактические ответы tools из этого хода:\n\n"
    )
    if evidence:
        return (
            head
            + evidence
            + (
                "\n\nПродолжаю задачу, опираясь на эти listing'и "
                "(относительные пути, без `~` / `$HOLIX_HOME`)."
            )
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
            re.match(r"^[A-Za-z0-9_.][A-Za-z0-9_.\-]*$", ln)
            and ln not in {"Success", "STDOUT:", "STDERR:"}
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
            if (
                name
                in {
                    "list_directory",
                    "run_terminal_command",
                    "terminal",
                    "read_file",
                    "sdd_list_projects",
                    "sdd_list_specs",
                    "sdd_list_changes",
                    "sdd_status",
                    "sdd_init",
                }
                or not name
            ):
                if _listing_evidence_from_content(content):
                    return True
    if tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            raw = tr.get("result")
            content = raw if isinstance(raw, str) else str(raw or "")
            name = str(tr.get("tool_name") or "").lower()
            if (
                name
                in {
                    "list_directory",
                    "run_terminal_command",
                    "terminal",
                    "read_file",
                    "sdd_list_projects",
                    "sdd_list_specs",
                    "sdd_list_changes",
                    "sdd_status",
                    "sdd_init",
                }
                or not name
            ):
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


def scrub_false_empty_claim_content(
    content: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> str:
    """Blank assistant text that denies visible tool listings (mid-turn or final).

    Models often stream «Список пуст…» together with more tool_calls; that text is
    shown in Studio even though honesty only runs on final answers. Scrub it so
    the UI does not display a contradiction of prior Success listings.
    """
    text = content if isinstance(content, str) else ("" if content is None else str(content))
    if not text.strip():
        return text
    if denies_visible_workspace(text, messages, tool_results=tool_results):
        return ""
    return text


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


def _is_honesty_nudge_message(msg: dict[str, Any] | None) -> bool:
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    raw = msg.get("content")
    text = raw if isinstance(raw, str) else str(raw or "")
    return text.strip().startswith("[Action honesty")


def _last_real_user_index(messages: list[dict[str, Any]] | None) -> int:
    """Index of the last real user turn (honesty injects are not a new request)."""
    last = -1
    if not messages:
        return last
    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        if _is_honesty_nudge_message(msg):
            continue
        last = i
    return last


def successful_tools_since_last_user(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Tool names with non-error results after the last user message."""
    names: list[str] = []
    if messages:
        last_user = _last_real_user_index(messages)
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
    idx = _last_real_user_index(messages)
    if idx < 0 or not messages:
        return ""
    raw = messages[idx].get("content")
    return raw if isinstance(raw, str) else str(raw or "")


def is_sdd_fill_request(text: str | None) -> bool:
    """True when the user/Studio asked to fill SDD change artifacts."""
    return bool(text and _SDD_FILL_REQUEST.search(text))


def claims_sdd_artifacts_filled(text: str | None) -> bool:
    """True when the assistant claims SDD proposal/specs/tasks were written."""
    return bool(text and _SDD_FILL_CLAIM.search(text))


def has_successful_artifact_write(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if a persist tool wrote content after the last real user message.

    ``sdd_write_artifact`` is preferred for OpenSpec, but analysis/docs agents
    often only have ``write_file``. Scaffold-only ``sdd_create_change`` does not
    count.
    """
    success = set(successful_tools_since_last_user(messages, tool_results=tool_results))
    return bool(success.intersection(_ARTIFACT_WRITE_TOOLS))


def has_successful_sdd_write(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> bool:
    """True if SDD/docs content was persisted (sdd_write_artifact or write_file)."""
    return has_successful_artifact_write(messages, tool_results=tool_results)


def persist_tool_summaries(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Short lines for successful persist tools (for empty-final recovery)."""
    lines: list[str] = []
    if not has_successful_artifact_write(messages, tool_results=tool_results):
        return lines
    id_to_name = _tool_call_id_names(messages or [])
    last_user = _last_real_user_index(messages)
    if messages:
        for msg in messages[last_user + 1 :]:
            if msg.get("role") != "tool":
                continue
            raw = msg.get("content")
            content = raw if isinstance(raw, str) else str(raw or "")
            if _tool_result_failed(content):
                continue
            name = _tool_name_from_message(msg, id_to_name) or "tool"
            if name not in _ARTIFACT_WRITE_TOOLS:
                continue
            preview = " ".join(content.split())[:240]
            lines.append(f"- {name}: {preview}")
    if not lines and tool_results:
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            name = str(tr.get("tool_name") or tr.get("name") or "").strip()
            if name not in _ARTIFACT_WRITE_TOOLS:
                continue
            raw = tr.get("result") or tr.get("content") or ""
            content = raw if isinstance(raw, str) else str(raw)
            if _tool_result_failed(content):
                continue
            preview = " ".join(content.split())[:240]
            lines.append(f"- {name}: {preview}")
    return lines[-8:]


def summarize_persist_tools(
    messages: list[dict[str, Any]] | None,
    *,
    tool_results: list[dict[str, Any]] | None = None,
) -> str:
    """Human summary when the model wrote files but returned no final text."""
    lines = persist_tool_summaries(messages, tool_results=tool_results)
    if not lines:
        return ""
    return "Work completed via tools (model returned no final text):\n" + "\n".join(lines)


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

    # SDD/docs fill: claiming artifacts written requires a persist tool this turn.
    # write_file counts — analysis subagents often lack sdd_write_artifact.
    if claims_sdd_artifacts_filled(content) or (
        is_sdd_fill_request(user) and claims_action_completed(content)
    ):
        if not has_successful_artifact_write(messages, tool_results=tool_results):
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
    last_user = _last_real_user_index(messages)
    for msg in messages[last_user + 1 :]:
        if msg.get("role") == "tool":
            return True
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            return True
    return False


def looks_like_status_monologue(text: str | None) -> bool:
    """True for short «Да. Смотрю X…» / «Работаю…» spam as the whole reply."""
    content = (text or "").strip()
    if not content:
        return False
    # Collapse glued loops first so detection still works after stream abort.
    if len(content) > 240:
        try:
            from core.llm.response_text import collapse_repetitive_text

            content = collapse_repetitive_text(content) or content
        except Exception:
            pass
    if _STATUS_ONLY_MONOLOGUE.match(content):
        return True
    # Slightly longer status: «Да, работаю. Смотрю mcp_server.py, чтобы …»
    if len(content) <= 280 and _ACTION_INTENT.search(content):
        # Pure status verbs, no completion claim, no substantial answer.
        if claims_action_completed(content):
            return False
        # Avoid treating real answers that merely contain «смотрю» mid-paragraph.
        if content.count("\n") >= 3 and len(content) > 160:
            return False
        return bool(
            re.search(
                r"(?is)^\s*((да|понял[ао]?|хорошо|ок|ok)[,.!?…]?\s*)*"
                r"(работаю|смотрю|читаю|открываю|изучаю|проверяю|проверю|разбираю|"
                r"looking\s+at|reading|opening|working\s+on|checking)\b",
                content,
            )
        )
    return False


_UNFINISHED_ANNOUNCE = re.compile(
    r"(?is)("
    r"let\s+me\s+(take\s+a\s+step\s+back|start|begin|first|"
    r"now\s+(create|write|build|fix|implement))"
    r"|let\s+me\s+start\s+with"
    r"|take\s+a\s+step\s+back\s+and\s+(create|write|rebuild|implement)"
    r"|create\s+all\s+the\s+files\s+properly"
    r"|i('ll|\s+will)\s+(now\s+)?(create|write|build|start|begin|add|implement)\s+"
    r"(all\s+)?(the\s+)?(files|models|routers|tests|app)"
    r"|начн[уём]\s+с\b"
    r"|сейчас\s+(создам|напишу|соберу|перепишу)\s+(все\s+)?(файл|модел|проект)"
    r"|перепишу\s+вс[её]\s+заново"
    r"|начну\s+(заново|с\s+нуля|с\s+модел)"
    r"|давай\s+(создам|напишу|соберу)\s+(все\s+)?"
    r")"
)


def looks_like_unfinished_work_announcement(text: str | None) -> bool:
    """True when the reply only announces the next write, not a finished step.

    Covers the process-coder pattern: tools already ran, then the model ends
    with «Let me start with the models:» and the parent treats that as done.
    """
    content = (text or "").strip()
    if not content:
        return False
    if not _UNFINISHED_ANNOUNCE.search(content):
        return False
    last = "\n".join(content.splitlines()[-3:])
    if len(content) > 1200 and not _UNFINISHED_ANNOUNCE.search(last):
        return False
    if claims_action_completed(content) and not _UNFINISHED_ANNOUNCE.search(last):
        return False
    return True


_USER_CLARIFY = re.compile(
    r"(?is)("
    r"ответ(ь|ьте|ь,\s+пожалуйста)"
    r"|уточн[июи]"
    r"|несколько\s+вопросов"
    r"|прежде\s+чем\s+(писать|делать|создав|нач)"
    r"|давай\s+определ"
    r"|need\s+to\s+(clarify|confirm|know)"
    r"|before\s+i\s+(write|start|implement)"
    r"|a\s+few\s+questions"
    r")"
)


def looks_like_clarifying_questions(text: str | None) -> bool:
    """True when the model is asking the user to choose, not claiming work."""
    content = (text or "").strip()
    if not content:
        return False
    n_q = content.count("?")
    if n_q >= 2:
        return True
    if n_q >= 1 and _USER_CLARIFY.search(content):
        return True
    return False


def looks_like_plan_monologue(text: str | None) -> bool:
    """True for intermediate 'I'll do X / Начинаю' plans without a real answer."""
    content = (text or "").strip()
    if not content:
        return False
    if looks_like_status_monologue(content):
        return True
    if _STATUS_ONLY_MONOLOGUE.match(content):
        return True
    return bool(_PLAN_MONOLOGUE.search(content))


# User asked to *do* something (not pure FAQ / opinion).
_ACTION_REQUEST = re.compile(
    r"(?is)("
    r"\b(сделай|делай|продолжи|продолжай|добавь|реализуй|почини|исправь|напиши|создай|удали|внедри|"
    r"доделай|поправь|перепиши|обнови|настрой|подключи|запусти|запиши|проверь|проверьте|"
    r"опубликуй|выложи|запости|найди|поищи)\b"
    r"|\b(implement|fix|add|create|build|update|remove|delete|deploy|"
    r"finish|complete|wire|install|continue|post|publish|check|write|find|search)\b"
    r")"
)


def is_action_request(user_text: str | None) -> bool:
    """True when the user message looks like a work request (not pure FAQ)."""
    text = (user_text or "").strip()
    if not text:
        return False
    return bool(_ACTION_REQUEST.search(text))


def is_truncation_notice(text: str | None) -> bool:
    """True when the visible reply is (or ends with) the system truncation notice."""
    content = (text or "").strip()
    if not content:
        return False
    return bool(_TRUNCATION_NOTICE.search(content))


def ends_turn_on_unexecuted_intent(
    text: str | None,
    messages: list[dict[str, Any]] | None,
    *,
    user_input: str | None = None,
    agent_pipeline: str | None = None,
) -> bool:
    """True when the model only promises an action and never called tools.

    Applies on **both** classic and modern pipelines: ending with
    «Создаю/Сделаю/Ищу…» without tool_calls is never a finished task.
    Modern additionally treats truncation notices and status spam.
    """
    from core.agent_pipeline import is_modern_pipeline

    content = (text or "").strip()
    if not content:
        return False
    if looks_like_clarifying_questions(content):
        return False
    if _tools_attempted_since_last_user(messages):
        return False

    user = (user_input or "").strip() or last_user_text(messages)
    modern = is_modern_pipeline(agent_pipeline)

    # Qwen/Hermes often dump ``tool_call`` / ``<tool_call>`` as prose instead
    # of structured tool_calls — never accept that as a finished turn.
    try:
        from core.llm.tool_calls import looks_like_leaked_tool_markup

        if looks_like_leaked_tool_markup(content):
            return True
    except Exception:
        if re.search(r"(?is)\btool_calls?\b|</?tool_call\b", content):
            return True

    # Pathological monologue loops must never end the turn (classic + modern).
    # Classic previously skipped this and could "finish" on 18KB of «Поняла…».
    try:
        from core.llm.response_text import is_pathological_repetition

        if is_pathological_repetition(content, min_repeats=3):
            return True
    except Exception:
        pass

    # Modern: truncation notice / short status spam as incomplete turns.
    if modern:
        if is_truncation_notice(content):
            return True
        if looks_like_status_monologue(content):
            return True
    elif looks_like_status_monologue(content) and len(content) <= 400:
        # Classic: short pure status («Поняла. Запускаю…») without tools.
        return True

    action_user = is_action_request(user)
    # Strong work verbs without tools — always block (even classic).
    if re.search(
        r"(?is)\b("
        r"созда[юёмм]|создам|опублик[уююем]|ищу\s+свеж|тестовый\s+пост|"
        r"запуска[юем]|запущу|останавлива[юем]|провер[яюем]|смотрю|"
        r"write_file|run_terminal|list_directory"
        r")\b",
        content,
    ):
        return True
    # "I'll do it / Сделаю…" without tools — only when the user asked for work
    # (avoid blocking pure FAQ answers that say «Что сделаю: объясню»).
    if action_user and _ACTION_INTENT.search(content):
        return True
    if action_user and looks_like_plan_monologue(content):
        return True
    # Action request + short pure-intent answer.
    if action_user and len(content) <= 600:
        if re.search(
            r"(?is)^\s*((понял[ао]?|хорошо|ок|ok|да)[,.!?…]?\s*)+"
            r".{0,200}$",
            content,
        ) and re.search(
            r"(?is)\b(сдела|созда|добав|напиш|опублик|провер|ищу|найд|запуст)\w*",
            content,
        ):
            return True
    return False


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
    if denies_visible_workspace(final_response, messages, tool_results=tool_results):
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
    pipeline = str(state.get("agent_pipeline") or "") if isinstance(state, dict) else ""
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
    if looks_like_clarifying_questions(final_response):
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
    if (
        sdd_fill_requires_tools(
            messages,
            tool_results=tool_results,
            user_input=user_input,
        )
        and (final_response or "").strip()
    ):
        return True
    if looks_like_unfinished_work_announcement(final_response):
        return True
    return ends_turn_on_unexecuted_intent(
        final_response,
        messages,
        user_input=user_input,
        agent_pipeline=pipeline,
    )


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
    if not denies_visible_workspace(final_response, messages, tool_results=tool_results):
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
    if not _unproven_sdd_fill_final(state, final_response=final_response, messages=messages):
        return False
    user_input = state.get("user_input") if isinstance(state, dict) else None
    max_nudges = _max_nudges_for_turn(
        messages, final_response=final_response, user_input=user_input
    )
    # Only refuse once nudges are exhausted (otherwise should_nudge retries).
    return int(state.get("honesty_nudge_count") or 0) >= max_nudges


def should_refuse_status_monologue(
    state: dict[str, Any],
    *,
    final_response: str | None,
    messages: list[dict[str, Any]] | None,
) -> bool:
    """After max nudges, never accept pure intent monologue as the final answer.

    Classic and modern: if the model still only says «сделаю…» without tools
    after retries, refuse instead of going silent mid-task.
    """
    if _plan_mode_skips_honesty(state):
        return False
    if _tools_attempted_since_last_user(messages):
        return False
    content = (final_response or "").strip()
    if not content:
        return False
    pipeline = str(state.get("agent_pipeline") or "") if isinstance(state, dict) else ""
    user_input = state.get("user_input") if isinstance(state, dict) else None
    if not ends_turn_on_unexecuted_intent(
        content,
        messages,
        user_input=user_input,
        agent_pipeline=pipeline,
    ):
        return False
    max_nudges = _max_nudges_for_turn(
        messages, final_response=final_response, user_input=user_input
    )
    return int(state.get("honesty_nudge_count") or 0) >= max_nudges


def _nudge_for_presentation(nudge: str, tools_presentation: str | None) -> str:
    from core.tools.code_mode.policy import normalize_presentation

    if normalize_presentation(tools_presentation) != "code":
        return nudge
    if "Code mode" in nudge:
        return nudge
    return nudge.rstrip() + CODE_MODE_NUDGE_TAIL


def honesty_retry_update(
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    honesty_nudge_count: int = 0,
    include_assistant: bool = True,
    user_input: str | None = None,
    tools_presentation: str | None = None,
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
    elif looks_like_unfinished_work_announcement(final_response):
        nudge = UNFINISHED_STEP_NUDGE
    elif (
        is_truncation_notice(final_response)
        or looks_like_status_monologue(final_response)
        or (
            looks_like_plan_monologue(final_response)
            and not claims_action_completed(final_response)
        )
    ):
        # Dedicated monologue / truncation nudge — generic "done" text is ignored.
        # Truncation without tools means the model burned the token budget on prose.
        nudge = MONOLOGUE_TOOL_NUDGE
    else:
        nudge = ACTION_HONESTY_NUDGE
    nudge = _nudge_for_presentation(nudge, tools_presentation)
    # Compact assistant history: do not re-feed a monologue wall into the next step.
    if updated and isinstance(updated[-1], dict) and updated[-1].get("role") == "assistant":
        prev = str(updated[-1].get("content") or "")
        if (
            is_truncation_notice(prev)
            or looks_like_status_monologue(prev)
            or (looks_like_plan_monologue(prev) and len(prev) > 240)
        ):
            try:
                from core.llm.response_text import collapse_repetitive_text

                short = collapse_repetitive_text(prev) or prev
            except Exception:
                short = prev
            if len(short) > 280:
                short = short[:280].rstrip() + "…"
            updated[-1] = {
                "role": "assistant",
                "content": short or "(status monologue without tools)",
            }
    updated.append({"role": "user", "content": nudge})
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": False,
        "tool_calls": [],
        # Do not put a 400-char prefix into final_response: hosts (Studio) may
        # emit it as the user-visible final while Holix memory already has the
        # full answer. Clear the field on honesty retry (is_final stays False).
        "final_response": ((final_response or "") if is_truncation_notice(final_response) else ""),
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
    last_content = str(last.get("content") or "") if isinstance(last, dict) else ""
    if (
        isinstance(last, dict)
        and last.get("role") == "assistant"
        and (
            include_assistant
            or (final_response and last_content == final_response)
            or claims_sdd_artifacts_filled(last_content)
            or claims_action_completed(last_content)
            or claims_empty_or_deaf_tools(last_content)
            or looks_like_status_monologue(last_content)
            or looks_like_plan_monologue(last_content)
        )
    ):
        updated[-1] = {"role": "assistant", "content": body}
    elif include_assistant or not (isinstance(last, dict) and last.get("role") == "assistant"):
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
    """Return OpenAI tool_choice for this ReAct step.

    Soft honesty nudges alone do not stop monologue loops on weak models.
    After any honesty nudge — or when the last assistant turn was pure status
    monologue without tools — force ``tool_choice=required`` so the API
    rejects text-only replies.

    For clear action requests (сделай / create / publish…), the **first** LLM
    step of the turn also requires tools so the model cannot burn max_tokens
    on «Поняла. Сейчас сделаю…» prose.
    """
    if not tools:
        return "auto"
    user_input = state.get("user_input") if isinstance(state, dict) else None
    if sdd_fill_requires_tools(
        messages,
        tool_results=state.get("tool_results") if isinstance(state, dict) else None,
        user_input=user_input,
    ):
        # Prefer a forced function call when the schema is available (stronger
        # than tool_choice=required, which some gateways treat loosely).
        if _tools_include_name(tools, "sdd_write_artifact"):
            return {
                "type": "function",
                "function": {"name": "sdd_write_artifact"},
            }
        return "required"
    from core.agent_pipeline import is_classic_pipeline

    pipeline = str(state.get("agent_pipeline") or "") if isinstance(state, dict) else ""
    # After honesty retry, tools are mandatory on both pipelines.
    if int(state.get("honesty_nudge_count") or 0) > 0:
        return "required"

    # Both classic and modern: action request + no tools yet → force tool_calls.
    # Prevents «Создаю/Сделаю…» and then silence mid-task (classic quiet path
    # still must finish the job).
    if is_action_request(user_input or last_user_text(messages)) and not (
        _tools_attempted_since_last_user(messages)
    ):
        return "required"

    # Classic: no extra monologue heuristics (no truncation wall / status spam).
    if is_classic_pipeline(pipeline):
        return "auto"

    # Modern only: force tools if last assistant turn was pure monologue.
    if messages:
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "tool":
                break
            if role == "assistant":
                content = str(msg.get("content") or "")
                if msg.get("tool_calls"):
                    break
                if (
                    is_truncation_notice(content)
                    or looks_like_status_monologue(content)
                    or looks_like_plan_monologue(content)
                ):
                    return "required"
                break
            if role == "user":
                text = str(msg.get("content") or "")
                if text.strip().startswith("[Action honesty"):
                    return "required"
                break
    return "auto"
