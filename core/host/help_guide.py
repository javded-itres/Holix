"""Interactive usage guide for Telegram / MAX `/help` (scenario submenus)."""

from __future__ import annotations

from html import escape as html_escape

from core.i18n.locale import normalize_locale

HELP_CALLBACK_ACTION = "hp"

# Home topics (two-column keyboard). Sub-agents has its own submenu.
HOME_CHILDREN: tuple[str, ...] = (
    "start",
    "how",
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
HOW_CHILDREN: tuple[str, ...] = ("howa", "howp", "howc", "hows", "howd")

_PARENT: dict[str, str | None] = {
    "home": None,
    "start": "home",
    "how": "home",
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
    "howa": "how",
    "howp": "how",
    "howc": "how",
    "hows": "how",
    "howd": "how",
}

_CHILDREN: dict[str, tuple[str, ...]] = {
    "home": HOME_CHILDREN,
    "sub": SUB_CHILDREN,
    "how": HOW_CHILDREN,
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "home": ("home", "index", "меню", "справка"),
    "start": ("start", "start-here", "начало", "старт"),
    "how": ("how", "guide", "работа", "как"),
    "howa": ("howa", "abilities", "умеет", "функции"),
    "howp": ("howp", "prompt", "prompts", "промпт", "промпты", "задача", "задачи"),
    "howc": ("howc", "context", "контекст", "compress"),
    "hows": ("hows", "doctor", "проблемы", "ошибка"),
    "howd": ("howd", "document", "documents", "документ", "документы", "rag"),
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
        "how": "How to work",
        "howa": "What it can do",
        "howp": "Prompts and tasks",
        "howc": "Context overflow",
        "hows": "Fix it yourself",
        "howd": "Large documents",
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
        "how": "Как работать",
        "howa": "Что умеет",
        "howp": "Промпты и задачи",
        "howc": "Переполнение",
        "hows": "Сам разбирается",
        "howd": "Большие файлы",
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
            "`/help how` is the guide with examples. `/help sub` opens Sub-agents."
        ),
        "how": (
            "Short guide: what Holix can do, how to write a task, what to do when "
            "the context fills up, and how to make the agent debug itself.\n\n"
            "Open a page below. `/help prompt` jumps to examples."
        ),
        "howa": (
            "Holix is a tool-using agent, not a chat-only model.\n\n"
            "• Read and edit the workspace (`read_file`, `patch_file`, `grep`).\n"
            "• Run commands and long jobs, then report the result.\n"
            "• Search the web and fetch pages.\n"
            "• Remember facts and past sessions; you can review that memory.\n"
            "• Spawn a specialist sub-agent (`coder`, `reviewer`, `researcher`).\n"
            "• Generate an image or a video when media is configured.\n"
            "• Schedule cron, call MCP tools, follow a spec (SDD).\n"
            "• Ask you before a risky step. `/stop` cancels the run.\n\n"
            "It does not invent task ids, and it should not claim a file or a "
            "memory change until the tool result says so."
        ),
        "howp": (
            "One message = one outcome. Name the result, the place, and the limit.\n\n"
            "Weak: «fix the project».\n"
            "Better: «In `api/routers`, the login test fails on a missing token. "
            "Find the cause, patch it, run that test, stop.»\n\n"
            "Weak: «make it nicer».\n"
            "Better: «Rewrite the empty-state text on the billing page. "
            "Do not change the layout. Show me the diff.»\n\n"
            "Attach the file or name the path. Say what to keep. "
            "If there are two valid choices, the agent should ask, not guess."
        ),
        "howc": (
            "A long chat crowds out the task. Holix compresses history, but you "
            "can do it earlier.\n\n"
            "• `/compress` — shrink this chat and keep a summary.\n"
            "• `/new` — fresh session when the topic changed.\n"
            "• `/clear` — drop the transcript. `/forget` clears session memory.\n"
            "• Do not paste a 30-page file into the message. Attach it; "
            "large text is indexed and read in fragments (`/help documents`).\n"
            "• Ask for a short status, not a retelling of every step.\n\n"
            "If answers get vague or repeat old work, compress or start `/new` "
            "and restate the goal in one message."
        ),
        "hows": (
            "When a run fails, ask the agent to diagnose itself before you "
            "retry the same sentence.\n\n"
            "«Проверь себя» / «check yourself» starts `session_doctor`: it reads "
            "the trace in a clean context and says what broke and how to ask next.\n\n"
            "`/trace` — which tools ran. `/last` — the last tool output.\n"
            "`/stop` — halt a stuck run, then send a narrower task.\n\n"
            "Example: «The tests failed. Read `/trace`, name the one error, "
            "fix only that, rerun the same test.»"
        ),
        "howd": (
            "A long PDF, DOCX, Markdown, or text file is not pasted into the chat.\n\n"
            "Holix extracts the text, splits it into fragments, and keeps them "
            "on disk. The turn only sees a short card (id, size, opening lines).\n\n"
            "The agent searches with `search_document` and reads a few fragments "
            "with `read_document`. Ask a question, do not say «прочитай всё».\n\n"
            "Example: attach `contract.pdf` and write «Найди срок оплаты и штраф. "
            "Цитируй фрагмент, не пересказывай весь договор.»\n\n"
            "Several files in one session stay together. `/new` starts another "
            "task: its documents are not visible here, and these are not visible "
            "there. Name the file if more than one is attached.\n\n"
            "A sub-agent of this session receives those cards and can search "
            "the same fragments. Say which file and what to find.\n\n"
            "Short notes still go in full. Scanned PDFs without a text layer "
            "cannot be indexed."
        ),
        "start": (
            "1. Send a task: «fix tests in holix-sas», «summarize the last spec».\n"
            "2. Attach files / voice — the bot reads them into the same turn.\n"
            "3. Confirmations appear as buttons (`/yes` `/no` also work).\n"
            "4. `/new` — new session. `/models` — switch LLM for the next turns.\n"
            "5. `/menu` — modes, sub-agents, Reflexion, step budget, streaming, cron.\n"
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
            "`analyst`, `reviewer`, `writer`, `session_doctor`.\n\n"
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
            "`/models` — provider → model for this chat. Inside a provider: "
            "refresh the live list (r) and set the saved default (d, ★).\n"
            "`/profile` — Holix profile (admin in isolated multi-tenant).\n"
            "`/mode` — ReAct / Plan / Hybrid / Auto.\n"
            "`/menu` → Pipeline — Classic vs Modern (anti-spam honesty).\n"
            "`/stream` — live edits on/off.\n\n"
            "Configure `agent_models` in the profile (`holix models` in CLI)."
        ),
        "mem": (
            "`/memory query` — semantic search in long-term memory.\n"
            "`/forget` — clear this session's memory.\n"
            "«Keep only the last 7 days» deletes the rest without a quiz. "
            "«Show what you remember» quotes each row, not just its type.\n"
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
            "Send a document / photo / voice in chat — Holix extracts text. "
            "Long documents are indexed; see **Large documents**.\n"
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
            "`/help как` — как работать, с примерами. `/help субагенты` — субагенты."
        ),
        "how": (
            "Коротко: что агент умеет, как ставить задачу, что делать при "
            "переполнении контекста и как заставить его разобрать ошибку самому.\n\n"
            "Страницы ниже. Сразу к примерам: `/help промпт`."
        ),
        "howa": (
            "Holix — агент с инструментами, не просто чат.\n\n"
            "• Читает и правит файлы workspace (`read_file`, `patch_file`, `grep`).\n"
            "• Запускает команды и долгие задачи и сообщает результат.\n"
            "• Ищет в сети и открывает страницы.\n"
            "• Помнит факты и прошлые сессии; память можно пересмотреть.\n"
            "• Запускает узкого субагента (`coder`, `reviewer`, `researcher`).\n"
            "• Генерирует картинку или видео, если настроено медиа.\n"
            "• Ставит cron, вызывает MCP, ведёт спеку (SDD).\n"
            "• Спрашивает перед опасным шагом. `/stop` останавливает ход.\n\n"
            "Не выдумывает id задач и не должен говорить, что файл или память "
            "изменены, пока инструмент этого не вернул."
        ),
        "howp": (
            "Одно сообщение — один результат. Назовите итог, место и границу.\n\n"
            "Слабо: «почини проект».\n"
            "Лучше: «В `api/routers` падает тест логина: нет токена. "
            "Найди причину, поправь, запусти этот тест и остановись.»\n\n"
            "Слабо: «сделай красивее».\n"
            "Лучше: «Перепиши текст пустого состояния на странице оплаты. "
            "Вёрстку не трогай. Покажи diff.»\n\n"
            "Приложите файл или путь. Напишите, что оставить. "
            "Если выбора два, агент должен спросить, а не угадать."
        ),
        "howc": (
            "Длинный чат вытесняет задачу. Holix сжимает историю, но лучше раньше.\n\n"
            "• `/compress` — сжать этот чат, оставив сводку.\n"
            "• `/new` — новая сессия, если тема сменилась.\n"
            "• `/clear` — стереть транскрипт. `/forget` — память сессии.\n"
            "• Не вставляйте файл на 30 страниц в текст. Прикрепите его: "
            "длинный текст индексируется и читается фрагментами (`/help документы`).\n"
            "• Просите короткий статус, а не пересказ каждого шага.\n\n"
            "Если ответы стали общими или агент повторяет старую работу — "
            "`/compress` или `/new` и заново одна цель."
        ),
        "hows": (
            "Если ход сломался, попросите агента разобрать себя, "
            "а не повторяйте ту же фразу.\n\n"
            "«Проверь себя» запускает `session_doctor`: он читает след в чистом "
            "контексте и говорит, что сломалось и как спросить дальше.\n\n"
            "`/trace` — какие tools вызывались. `/last` — последний вывод.\n"
            "`/stop` — остановить зависший ход, затем более узкая задача.\n\n"
            "Пример: «Тесты упали. Посмотри `/trace`, назови одну ошибку, "
            "исправь только её и перезапусти тот же тест.»"
        ),
        "howd": (
            "Длинный PDF, DOCX, Markdown или текст не вставляется в чат целиком.\n\n"
            "Holix извлекает текст, режет на фрагменты и хранит их на диске. "
            "В ход попадает короткая карточка: id, размер, начало.\n\n"
            "Агент ищет через `search_document` и читает несколько фрагментов "
            "через `read_document`. Спросите вопрос, не «прочитай всё».\n\n"
            "Пример: приложите `contract.pdf` и напишите «Найди срок оплаты и штраф. "
            "Процитируй фрагмент, не пересказывай весь договор.»\n\n"
            "Несколько файлов в одной сессии остаются вместе. `/new` — другая "
            "задача: её документы сюда не попадают, и эти там не видны. Если "
            "файлов несколько, назовите нужный.\n\n"
            "Субагент этой сессии получает те же карточки и может искать "
            "по тем же фрагментам. Напишите, какой файл и что найти.\n\n"
            "Короткие заметки по-прежнему попадают целиком. Скан PDF без текстового "
            "слоя проиндексировать нельзя."
        ),
        "start": (
            "1. Напишите задачу: «почини тесты в holix-sas», «кратко по последней спеке».\n"
            "2. Файл / голос в том же сообщении попадают в тот же ход.\n"
            "3. Подтверждения — кнопки (или `/yes` `/no`).\n"
            "4. `/new` — новая сессия. `/models` — сменить LLM.\n"
            "5. `/menu` — режимы, субагенты, Reflexion, бюджет шагов, стриминг, cron.\n"
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
            "`analyst`, `reviewer`, `writer`, `session_doctor`.\n\n"
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
            "`/models` — провайдер → модель для этого чата. В провайдере: "
            "обновить список (↻) и выбрать модель по умолчанию (★).\n"
            "`/profile` — профиль Holix (в multi-tenant — админ).\n"
            "`/mode` — ReAct / Plan / Hybrid / Auto.\n"
            "`/menu` → Pipeline — Classic vs Modern (anti-spam honesty).\n"
            "`/stream` — живые правки вкл/выкл.\n\n"
            "`agent_models` настраиваются в профиле (`holix models` в CLI)."
        ),
        "mem": (
            "`/memory запрос` — семантический поиск в долгой памяти.\n"
            "`/forget` — очистить память этой сессии.\n"
            "«Оставь память за 7 дней, остальное удали» — агент удалит сам. "
            "«Покажи, что помнишь» — в вопросе будет текст каждой записи, не только тип.\n"
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
            "Документ / фото / голос в чат — Holix извлекает текст. "
            "Длинные документы индексируются; см. **Большие файлы**.\n"
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
