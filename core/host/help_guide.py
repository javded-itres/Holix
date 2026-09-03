"""Interactive usage guide for Telegram / MAX `/help` (scenario submenus)."""

from __future__ import annotations

from html import escape as html_escape

from core.i18n.locale import normalize_locale

HELP_CALLBACK_ACTION = "hp"

# Home topics (two-column keyboard). Sub-agents has its own submenu.
HOME_CHILDREN: tuple[str, ...] = (
    "start",
    "chat",
    "sub",
    "skill",
    "sdd",
    "model",
    "mem",
    "cron",
    "mcp",
    "perm",
    "files",
    "cmds",
)

SUB_CHILDREN: tuple[str, ...] = ("subw", "subc", "subr", "subm")

_PARENT: dict[str, str | None] = {
    "home": None,
    "start": "home",
    "chat": "home",
    "sub": "home",
    "skill": "home",
    "sdd": "home",
    "model": "home",
    "mem": "home",
    "cron": "home",
    "mcp": "home",
    "perm": "home",
    "files": "home",
    "cmds": "home",
    "subw": "sub",
    "subc": "sub",
    "subr": "sub",
    "subm": "sub",
}

_CHILDREN: dict[str, tuple[str, ...]] = {
    "home": HOME_CHILDREN,
    "sub": SUB_CHILDREN,
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "home": ("home", "index", "меню", "справка"),
    "start": ("start", "start-here", "начало", "старт"),
    "chat": ("chat", "чат"),
    "sub": ("sub", "subagent", "subagents", "субагент", "субагенты"),
    "subw": ("subw", "what", "что"),
    "subc": ("subc", "config", "configure", "настройка", "настроить"),
    "subr": ("subr", "spawn", "run", "запуск"),
    "subm": ("subm", "code-mode", "codemode", "code"),
    "skill": ("skill", "skills", "навык", "навыки"),
    "sdd": ("sdd", "spec", "specs", "спека", "спеки"),
    "model": ("model", "models", "profile", "режим", "модели", "профиль"),
    "mem": ("mem", "memory", "память"),
    "cron": ("cron", "крон"),
    "mcp": ("mcp",),
    "perm": ("perm", "permission", "sandbox", "права"),
    "files": ("files", "file", "terminal", "pty", "файлы", "терминал"),
    "cmds": ("cmds", "commands", "команды"),
}

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "home": "Help",
        "start": "Getting started",
        "chat": "Chat",
        "sub": "Sub-agents",
        "subw": "What they are",
        "subc": "Configure types",
        "subr": "Spawn a job",
        "subm": "Code mode",
        "skill": "Skills",
        "sdd": "Specs (SDD)",
        "model": "Models & profiles",
        "mem": "Memory",
        "cron": "Cron",
        "mcp": "MCP",
        "perm": "Permissions",
        "files": "Files & shell",
        "cmds": "Command list",
        "back": "← Back",
    },
    "ru": {
        "home": "Справка",
        "start": "Начало работы",
        "chat": "Чат",
        "sub": "Субагенты",
        "subw": "Что это",
        "subc": "Настройка типов",
        "subr": "Запуск задачи",
        "subm": "Code mode",
        "skill": "Навыки",
        "sdd": "Спеки (SDD)",
        "model": "Модели и профили",
        "mem": "Память",
        "cron": "Cron",
        "mcp": "MCP",
        "perm": "Права",
        "files": "Файлы и shell",
        "cmds": "Список команд",
        "back": "← Назад",
    },
}

_BODIES: dict[str, dict[str, str]] = {
    "en": {
        "home": (
            "Write a task in plain language — Holix uses tools, memory, and skills.\n\n"
            "Pick a **scenario** below. Settings panel: `/menu`. Stop a run: `/stop`.\n"
            "`/help sub` opens Sub-agents directly."
        ),
        "start": (
            "1. Send a task: «fix tests in holix-sas», «summarize the last spec».\n"
            "2. Attach files / voice — the bot reads them into the same turn.\n"
            "3. Confirmations appear as buttons (`/yes` `/no` also work).\n"
            "4. `/new` — new session. `/models` — switch LLM for the next turns.\n"
            "5. `/menu` — modes, sub-agents, Reflexion, streaming, cron.\n"
            "6. `/init` — scan the workspace and write `.holix/HOLIX.md`.\n\n"
            "Workspace for Telegram/MAX is the profile `workspace_root` "
            "(not the bot process CWD)."
        ),
        "chat": (
            "The agent edits **one live message** while it works.\n\n"
            "• `/stream` — streaming on/off (buttons).\n"
            "• `/clear` — forget this chat context (`/forget` clears session memory).\n"
            "• `/compress` — shrink long history.\n"
            "• `/stop` — cancel the current run and sub-agents.\n"
            "• `/todos` — session checklist from `todo_write`.\n"
            "• `/trace` — what tools ran (`/trace 80` or `/trace search grep`).\n"
            "• `/last` — last tool output.\n\n"
            "Slash commands are not sent to the LLM. On a Russian macOS keyboard "
            "`,help` / `.help` work as `/help`."
        ),
        "sub": (
            "Sub-agents are **specialized workers**. A **type** is the role "
            "(prompt, tools, model). A **job** is one run of that type.\n\n"
            "Built-in types: `researcher`, `web_researcher`, `page_analyst`, `coder`, "
            "`analyst`, `reviewer`, `writer`.\n\n"
            "Open this submenu for configure / spawn / Code mode, or send "
            "`/subagent-types` and `/menu` → Sub-agents."
        ),
        "subw": (
            "Enable in profile `config.yaml`:\n\n"
            "`enable_subagents: true`\n"
            "`subagent_default_process_mode: async`  (or `process`)\n"
            "`subagent_max_concurrent: 4`\n\n"
            "Default is **on**, mode **async**. If off, `delegate_to_subagent` "
            "and `/subagent-spawn` error.\n\n"
            "Each job is a child Holix agent on the same ReAct graph, with a "
            "**filtered** tool list (it cannot spawn more sub-agents).\n"
            "`fork=true` copies completed parent turns; default is a fresh chat."
        ),
        "subc": (
            "In Telegram / MAX:\n"
            "1. `/menu` → **Sub-agents**, or `/subagent-types` / `/code-mode`.\n"
            "2. **Code mode** for main: `native` / `code` / `both`.\n"
            "3. **Create from description** — one message with the role, e.g. "
            "«security auditor, read code, look for OWASP». Saved to "
            "`types.json` and listed immediately.\n"
            "4. **Built-in type** — personality (generate or paste), model slot, "
            "temperature, tools, Code mode. **Reset** drops the overlay.\n"
            "5. **Custom type** — same fields + **Delete**.\n"
            "6. **Tools** — toggle the allow-list. Extra built-in tools "
            "(background process) stay until you replace the list.\n\n"
            "Skills, MCP, and external CLI (Claude Code, OpenCode) are edited "
            "in TUI: `/subagent-types`.\n\n"
            "Files:\n"
            "• `~/.holix/profiles/<profile>/subagents/types.json`\n"
            "• `.../subagents/overlays.json` — built-in overlays"
        ),
        "subr": (
            "Ask in chat:\n"
            "`Run researcher in the background: gather auth API docs`\n"
            "The main agent calls `delegate_to_subagent`.\n\n"
            "Or slash:\n"
            "`/subagent-spawn coder Fix failing tests in tests/`\n"
            "`/subagent-spawn --fork reviewer Review the last change`\n"
            "`/subagents` — running / recent jobs (buttons).\n"
            "`/subagent-result <job>` · `/subagent-terminate <job>`\n"
            "`/subagent-reply <job> <text>` after `ask_user`.\n\n"
            "If `coder` is busy, Holix starts `coder-2`.\n"
            "`/spec apply` / `sdd_apply` can spawn coder/writer waves from `tasks.md`."
        ),
        "subm": (
            "Code mode is how tools are **presented** to the model.\n\n"
            "• `native` — normal tool calls (`read_file`, `patch_file`, …).\n"
            "• `code` — only `run_code`: the model writes a Python program "
            "against a generated SDK. Each inner `tools.name(...)` still goes "
            "through ActionGuard and the workspace jail.\n"
            "• `both` — native + `run_code`.\n\n"
            "Set for **main** or **per type** in the Sub-agents menu. "
            "Profile keys: `tools_presentation`, `tools_presentation_by_slot` "
            "(e.g. `coder: code`)."
        ),
        "skill": (
            "`/skills` — list. The prompt only has a short index; the model "
            "loads a body with `skill_view`.\n\n"
            "Install from Hub in TUI (`/hub`) or copy `SKILL.md` into "
            "`~/.holix/profiles/<profile>/data/skills/`.\n"
            "Assign per agent slot (`skill_assignments`) in TUI type manager.\n\n"
            "A `/skill-name` slash can invoke an assigned skill."
        ),
        "sdd": (
            "Spec-Driven Development: specify → tasks → code → archive into "
            "`openspec/specs/`.\n\n"
            "`/spec` — list / create / show / apply / archive.\n"
            "`/spec create my-change -- add OAuth to the API`\n"
            "`/spec apply my-change` — implement (`self` / `subagents` / `hybrid`).\n\n"
            "Ask in chat: «спроектируй OAuth» — the agent uses `sdd_*` tools.\n"
            "Deltas live in `openspec/changes/<id>/`. Do not edit main specs "
            "by hand; `sdd_archive` merges them."
        ),
        "model": (
            "`/models` — provider → model (until you switch again).\n"
            "`/profile` — Holix profile (admin in isolated multi-tenant).\n"
            "`/mode` — ReAct / Plan / Hybrid / Auto.\n"
            "`/menu` → Pipeline — Classic vs Modern (anti-spam honesty).\n"
            "`/stream` — live edits on/off.\n\n"
            "Configure `agent_models` in the profile (`holix models` in CLI)."
        ),
        "mem": (
            "`/memory query` — semantic search in long-term memory.\n"
            "`/forget` — clear this session's memory.\n"
            "`/init` — project handbook `.holix/HOLIX.md` (loaded every turn).\n\n"
            "SOUL.md / USER.md — identity. See profile files under "
            "`~/.holix/profiles/<name>/`."
        ),
        "cron": (
            "`/cron` — jobs with enable / disable / delete.\n"
            "`/cron add every day at 9 :: check deploys`\n\n"
            "Natural language in chat can also schedule a job. "
            "Cron runs on the gateway, all profiles."
        ),
        "mcp": (
            "`/mcp` — servers, tools, install, assign, remove.\n"
            "Popular catalogs (Context7, …) can be installed from the menu.\n\n"
            "Assign servers to agent slots so a sub-agent type can use them. "
            "In isolated mode, install/remove is admin-only."
        ),
        "perm": (
            "`/permission` — session sandbox preset:\n"
            "• `workspace-write` — writes only in workspace / tmp (Seatbelt/bwrap).\n"
            "• `read-only` — no mutating tools.\n"
            "• `danger-full-access` — unconfined; HIGH tools auto-allowed.\n\n"
            "Risky tools still ask for confirmation (buttons or `/yes` `/no`).\n"
            "`HOLIX_PERMISSION_MODE` overrides the default. Not stored in config.yaml."
        ),
        "files": (
            "Send a document / photo / voice in chat — Holix extracts text.\n"
            "The agent prefers `patch_file` for edits, `write_file` for new files.\n\n"
            "`/pty on|off|reset` — persistent shell (`cd` / `export` stick) on POSIX.\n"
            "`/change` — SDD git worktree (`switch <id>` / `leave`). "
            "`sdd_create_change` opens a worktree for that change.\n"
            "Background servers: `start_background_process` (buttons: logs / stop).\n"
            "`/todos` — checklist. Relative paths use `workspace_root`."
        ),
        "cmds": "",  # filled from slash specs
    },
    "ru": {
        "home": (
            "Пишите задачу обычным текстом — Holix берёт tools, память и навыки.\n\n"
            "Выберите **сценарий**. Панель настроек: `/menu`. Стоп: `/stop`.\n"
            "`/help субагенты` открывает раздел сразу."
        ),
        "start": (
            "1. Напишите задачу: «почини тесты в holix-sas», «кратко по последней спеке».\n"
            "2. Файл / голос в том же сообщении попадают в тот же ход.\n"
            "3. Подтверждения — кнопки (или `/yes` `/no`).\n"
            "4. `/new` — новая сессия. `/models` — сменить LLM.\n"
            "5. `/menu` — режимы, субагенты, Reflexion, стриминг, cron.\n"
            "6. `/init` — обход workspace → `.holix/HOLIX.md`.\n\n"
            "В Telegram/MAX рабочая папка — `workspace_root` профиля, не cwd процесса бота."
        ),
        "chat": (
            "Агент правит **одно живое сообщение**, пока работает.\n\n"
            "• `/stream` — стриминг вкл/выкл (кнопки).\n"
            "• `/clear` — сбросить контекст чата (`/forget` — память сессии).\n"
            "• `/compress` — сжать длинную историю.\n"
            "• `/stop` — остановить текущий запуск и субагентов.\n"
            "• `/todos` — чеклист сессии (`todo_write`).\n"
            "• `/trace` — какие tools вызывались (`/trace 80` или `/trace search grep`).\n"
            "• `/last` — вывод последнего tool.\n\n"
            "Слэш-команды в LLM не уходят. На русской раскладке macOS "
            "`,help` / `.help` = `/help`."
        ),
        "sub": (
            "Субагент — **узкий воркер**. **Тип** — роль (промпт, tools, модель). "
            "**Job** — один запуск этого типа.\n\n"
            "Встроенные типы: `researcher`, `web_researcher`, `page_analyst`, `coder`, "
            "`analyst`, `reviewer`, `writer`.\n\n"
            "Дальше: настройка типов, запуск, Code mode. Либо `/subagent-types` "
            "и `/menu` → Субагенты."
        ),
        "subw": (
            "В `config.yaml` профиля:\n\n"
            "`enable_subagents: true`\n"
            "`subagent_default_process_mode: async`  (или `process`)\n"
            "`subagent_max_concurrent: 4`\n\n"
            "По умолчанию **вкл**, режим **async**. Если выкл — "
            "`delegate_to_subagent` и `/subagent-spawn` вернут ошибку.\n\n"
            "Job — дочерний Holix-агент на том же ReAct-графе, со **своим** "
            "набором tools (вложенных субагентов нет).\n"
            "`fork=true` копирует завершённые ходы родителя; иначе — новый чат."
        ),
        "subc": (
            "В Telegram / MAX:\n"
            "1. `/menu` → **Субагенты**, либо `/subagent-types` / `/code-mode`.\n"
            "2. **Code mode** для главного агента: `native` / `code` / `both`.\n"
            "3. **Создать по описанию** — одно сообщение с ролью, например: "
            "«аудитор безопасности, читай код, ищи OWASP». Тип пишется в "
            "`types.json` и сразу в списке.\n"
            "4. **Системный тип** — личность (сгенерировать или вставить), слот "
            "модели, температура, tools, Code mode. **Сбросить** снимает оверлей.\n"
            "5. **Свой тип** — те же поля + **Удалить**.\n"
            "6. **Tools** — вкл/выкл. Служебные tools (фоновые процессы) "
            "остаются, пока не перезапишете список.\n\n"
            "Skills, MCP и внешние CLI (Claude Code, OpenCode) — в TUI: "
            "`/subagent-types`.\n\n"
            "Файлы:\n"
            "• `~/.holix/profiles/<профиль>/subagents/types.json`\n"
            "• `.../subagents/overlays.json` — оверлеи системных типов"
        ),
        "subr": (
            "В чате:\n"
            "`Запусти researcher в фоне: собери документацию API auth`\n"
            "Главный агент вызовет `delegate_to_subagent`.\n\n"
            "Слэши:\n"
            "`/subagent-spawn coder Почини падающие тесты в tests/`\n"
            "`/subagent-spawn --fork reviewer Проверь последний diff`\n"
            "`/subagents` — активные и недавние job (кнопки).\n"
            "`/subagent-result <job>` · `/subagent-terminate <job>`\n"
            "`/subagent-reply <job> <текст>` после `ask_user`.\n\n"
            "Если `coder` занят — будет `coder-2`.\n"
            "`/spec apply` / `sdd_apply` может поднять волны coder/writer из `tasks.md`."
        ),
        "subm": (
            "Code mode — **как** модель видит tools.\n\n"
            "• `native` — обычные вызовы (`read_file`, `patch_file`, …).\n"
            "• `code` — только `run_code`: модель пишет Python-программу под SDK. "
            "Каждый внутренний `tools.name(...)` всё равно проходит ActionGuard "
            "и jail workspace.\n"
            "• `both` — native + `run_code`.\n\n"
            "Задаётся для **main** или **на тип** в меню Субагенты. "
            "В профиле: `tools_presentation`, `tools_presentation_by_slot` "
            "(например `coder: code`)."
        ),
        "skill": (
            "`/skills` — список. В промпт попадает короткий индекс; тело "
            "навыка модель читает через `skill_view`.\n\n"
            "Hub в TUI (`/hub`) или файл `SKILL.md` в "
            "`~/.holix/profiles/<профиль>/data/skills/`.\n"
            "Назначение на слот агента (`skill_assignments`) — в TUI менеджере типов.\n\n"
            "Слэш `/имя-навыка` запускает назначенный skill."
        ),
        "sdd": (
            "Spec-Driven Development: сначала спека и задачи, потом код, "
            "в конце archive в `openspec/specs/`.\n\n"
            "`/spec` — список / создать / смотреть / apply / архив.\n"
            "`/spec create my-change -- добавь OAuth в API`\n"
            "`/spec apply my-change` — реализация (`self` / `subagents` / `hybrid`).\n\n"
            "В чате: «спроектируй OAuth» — агент берёт tools `sdd_*`.\n"
            "Дельты в `openspec/changes/<id>/`. Main-спеки руками не править — "
            "только `sdd_archive`."
        ),
        "model": (
            "`/models` — провайдер → модель (пока не смените снова).\n"
            "`/profile` — профиль Holix (в multi-tenant — админ).\n"
            "`/mode` — ReAct / Plan / Hybrid / Auto.\n"
            "`/menu` → Pipeline — Classic vs Modern (anti-spam honesty).\n"
            "`/stream` — живые правки вкл/выкл.\n\n"
            "`agent_models` настраиваются в профиле (`holix models` в CLI)."
        ),
        "mem": (
            "`/memory запрос` — семантический поиск в долгой памяти.\n"
            "`/forget` — очистить память этой сессии.\n"
            "`/init` — справочник проекта `.holix/HOLIX.md` (подмешивается каждый ход).\n\n"
            "SOUL.md / USER.md — идентичность. Файлы: `~/.holix/profiles/<имя>/`."
        ),
        "cron": (
            "`/cron` — список, вкл/выкл, удаление.\n"
            "`/cron add every day at 9 :: проверь деплои`\n\n"
            "Расписание можно описать и обычным текстом. "
            "Cron крутится на gateway по всем профилям."
        ),
        "mcp": (
            "`/mcp` — серверы, tools, установка, назначение, удаление.\n"
            "Популярные каталоги (Context7, …) ставятся из меню.\n\n"
            "Сервер можно назначить на слот агента — тип субагента его увидит. "
            "В isolated-режиме install/remove только у админа."
        ),
        "perm": (
            "`/permission` — пресет песочницы сессии:\n"
            "• `workspace-write` — запись только в workspace / tmp (Seatbelt/bwrap).\n"
            "• `read-only` — без изменяющих tools.\n"
            "• `danger-full-access` — без ограничений; HIGH tools auto-allow.\n\n"
            "Опасные tools всё равно спрашивают подтверждение (кнопки или `/yes` `/no`).\n"
            "`HOLIX_PERMISSION_MODE` перекрывает default. В config.yaml не пишется."
        ),
        "files": (
            "Документ / фото / голос в чат — Holix извлекает текст.\n"
            "Правки существующих файлов — `patch_file`, новые — `write_file`.\n\n"
            "`/pty on|off|reset` — постоянный shell (`cd` / `export` живут) на POSIX.\n"
            "`/change` — git worktree SDD (`switch <id>` / `leave`). "
            "`sdd_create_change` открывает дерево для change.\n"
            "Фоновые серверы: `start_background_process` (логи / стоп — кнопки).\n"
            "`/todos` — чеклист. Относительные пути — от `workspace_root`."
        ),
        "cmds": "",
    },
}


def _lang(locale: str | None) -> str:
    return "ru" if normalize_locale(locale) == "ru" else "en"


def help_topic_ids() -> tuple[str, ...]:
    return tuple(_PARENT.keys())


def resolve_help_topic(raw: str | None) -> str:
    token = (raw or "").strip().lower().lstrip("/")
    if not token:
        return "home"
    if token in _PARENT:
        return token
    for topic_id, aliases in _ALIASES.items():
        if token in aliases:
            return topic_id
    return "home"


def help_label(topic_id: str, locale: str | None) -> str:
    lang = _lang(locale)
    labels = _LABELS[lang]
    return labels.get(topic_id) or _LABELS["en"].get(topic_id) or topic_id


def help_parent(topic_id: str) -> str | None:
    return _PARENT.get(topic_id, None) if topic_id in _PARENT else None


def help_children(topic_id: str) -> tuple[str, ...]:
    return _CHILDREN.get(topic_id, ())


def help_keyboard_rows(topic_id: str, locale: str | None) -> list[list[tuple[str, str]]]:
    """Rows of ``(button_label, topic_id)`` including Back when nested."""
    topic = resolve_help_topic(topic_id)
    children = help_children(topic)
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for child in children:
        row.append((help_label(child, locale), child))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    parent = help_parent(topic)
    if parent is not None:
        rows.append([(help_label("back", locale), parent)])
    return rows


def _md_to_html(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end != -1:
                out.append("<b>" + html_escape(text[i + 2 : end]) + "</b>")
                i = end + 2
                continue
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                out.append("<code>" + html_escape(text[i + 1 : end]) + "</code>")
                i = end + 1
                continue
        nxt = n
        star = text.find("**", i)
        tick = text.find("`", i)
        if star != -1:
            nxt = min(nxt, star)
        if tick != -1:
            nxt = min(nxt, tick)
        out.append(html_escape(text[i:nxt]))
        i = nxt
    return "".join(out)


def _command_list_body(
    locale: str | None,
    *,
    command_lines: list[tuple[str, str]] | None,
) -> str:
    lang = _lang(locale)
    header = "Slash commands:" if lang == "en" else "Слэш-команды:"
    lines = [header, ""]
    specs = command_lines
    if specs is None:
        from core.host.command_menu import host_menu_commands

        specs = host_menu_commands(locale)
    for name, desc in specs:
        lines.append(f"• `/{name}` — {desc}")
    extra = (
        "\nControl panel: `/menu`. Confirmations: buttons or `/yes` `/no`."
        if lang == "en"
        else "\nПанель: `/menu`. Подтверждения: кнопки или `/yes` `/no`."
    )
    return "\n".join(lines) + extra


def help_page_text(
    topic_id: str,
    locale: str | None,
    *,
    html: bool,
    command_lines: list[tuple[str, str]] | None = None,
) -> str:
    topic = resolve_help_topic(topic_id)
    lang = _lang(locale)
    title = help_label(topic, locale)
    if topic == "cmds":
        body = _command_list_body(locale, command_lines=command_lines)
    else:
        catalog = _BODIES.get(lang) or _BODIES["en"]
        body = catalog.get(topic) or _BODIES["en"].get(topic) or ""
    if html:
        return f"<b>{html_escape(title)}</b>\n\n{_md_to_html(body)}"
    return f"**{title}**\n\n{body}"


def render_help_page(
    topic_id: str,
    locale: str | None,
    *,
    html: bool,
    command_lines: list[tuple[str, str]] | None = None,
) -> tuple[str, list[list[tuple[str, str]]]]:
    """Return ``(message, keyboard rows)`` for a help topic."""
    topic = resolve_help_topic(topic_id)
    text = help_page_text(topic, locale, html=html, command_lines=command_lines)
    return text, help_keyboard_rows(topic, locale)
