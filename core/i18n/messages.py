"""UI message catalog (EN default, RU optional)."""

from __future__ import annotations

from core.i18n.locale import DEFAULT_LOCALE, normalize_locale

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "lang.current": "Interface language: {code}",
        "lang.set": "Interface language set to {code}",
        "lang.usage": "Usage: /lang en | /lang ru",
        "lang.invalid": "Unknown language: {value}. Use: en, ru",
        "lang.cmd_desc": "Switch interface language (en / ru)",
        "cleared": "Chat cleared",
        "unknown_cmd": "Unknown: {cmd}",
        "type_help": "Type /help",
        "command_failed": "Command failed: {error}",
        "streaming": "streaming {state}",
        "mode_set": "mode → {mode}",
        "usage_memory": "Usage: /memory <query>",
        "usage_switch": "Usage: /switch N",
        "usage_session_name": "Usage: /session name <name>",
        "usage_profile": "/profile <name|N>",
        "profiles_title": "Profiles",
        "invalid_profile_num": "invalid profile number",
        "unknown_profile": "unknown profile: {name}",
        "models_hint": "Models: configure agent_models in profile (helix models)",
        "memory_cleared": "memory search cleared",
        "copy_nothing": "nothing to copy",
        "copy_label": "copied",
        "copy_tool": "last tool output copied",
        "copy_all": "full transcript copied",
        "transcript_empty": "empty",
        "status_line": "profile {profile} · mode {mode} · session {session}",
        "metrics_error": "metrics error: {error}",
        "skill_not_assigned": "Skill /{name} is not assigned to agent '{slot}'",
        "tg.mode": "Mode: {mode}",
        "tg.streaming": "Streaming: {state}",
        "tg.profile": "Profile: {name}",
        "tg.profile_same": "Already on profile {name}",
        "tg.profile_invalid": "Invalid profile",
        "tg.session": "Session: {title}{model}",
        "tg.session_switched": "Session switched",
        "tg.session_invalid": "Invalid session",
        "tg.new_session": "New session",
        "tg.tool_result": "Tool result",
        "tg.model": "Model: {label}",
        "tg.error": "Error",
        "tg.unknown_action": "Unknown action",
        "tg.no_tools": "No tool calls in this chat yet.",
        "tg.agent_not_ready": "Agent not ready",
        "tg.invalid_preset": "Invalid preset",
        "tg.invalid_provider": "Invalid provider",
        "tg.invalid_model": "Invalid model",
        "tg.cron_enabled": "Enabled: {id}",
        "tg.cron_disabled": "Disabled: {id}",
        "tg.cron_removed": "Removed: {id}",
        "tg.cron_on": "On",
        "tg.cron_off": "Off",
        "tg.cron_how_add": "How to add",
        "tg.mcp_none": "No MCP servers. Install via /mcp install first.",
        "tg.mcp_none_remove": "No MCP servers to remove.",
        "tg.menu.mode": "Mode",
        "tg.menu.profile": "Profile",
        "tg.menu.sessions": "Sessions",
        "tg.menu.streaming": "Streaming",
        "tg.menu.models": "Models",
        "tg.menu.compress": "Compress context",
        "tg.menu.prev": "Prev",
        "tg.menu.next": "Next",
        "tg.help.title": "Helix — commands",
        "tg.help.chat": "Chat",
        "tg.help.chat_body": "Send text — the agent replies in one live message.",
        "tg.help.commands": "Commands (menu left of the input field):",
        "tg.help.buttons": "Buttons",
        "tg.help.buttons_body": "/mode /profile /sessions /stream — pick with buttons\n/models — switch LLM until next message\n/status /menu — quick actions panel",
        "tg.help.extra": "More",
        "tg.help.extra_body": (
            "• /memory query — semantic search\n"
            "• /compress — compress chat history\n"
            "• /init — project analysis → .helix/HELIX.md\n"
            "• /profile name — switch profile\n"
            "• /plan-confirm · /plan-reject — plan review\n"
            "• /cron — scheduled jobs\n"
            "  /cron add every day at 9 :: task\n"
            "• /mcp — MCP servers menu\n"
            "  /mcp remove name — remove server\n\n"
            "Confirmations: buttons under the message or /yes /no"
        ),
        "tg.cmd.help": "Command help",
        "tg.cmd.status": "Profile, mode, session",
        "tg.cmd.models": "Switch LLM model",
        "tg.cmd.menu": "Control panel",
        "tg.cmd.mode": "Execution mode",
        "tg.cmd.profile": "Helix profile",
        "tg.cmd.stream": "Streaming on/off",
        "tg.cmd.sessions": "Session list",
        "tg.cmd.switch": "Session by number",
        "tg.cmd.clear": "Clear chat context",
        "tg.cmd.stop": "Stop running task",
        "tg.cmd.mcp": "MCP servers",
        "tg.cmd.new": "New session",
        "tg.cmd.memory": "Memory search",
        "tg.cmd.skills": "Skills list",
        "tg.cmd.subagents": "Sub-agents",
        "tg.cmd.tools": "Recent tool calls",
        "tg.cmd.last": "Last tool result",
        "tg.cmd.metrics": "Agent metrics",
        "tg.cmd.compress": "Compress context",
        "tg.cmd.init": "Project analysis → HELIX.md",
        "tg.cmd.cron": "Cron jobs",
        "tg.cmd.yes": "Confirm action",
        "tg.cmd.no": "Deny action",
        "tg.cmd.lang": "Interface language (en / ru)",
        "tui.help.title": "Helix code UI",
        "tui.help.keys1": "  Enter — send    Shift+Enter — newline",
        "tui.help.keys2": "  {quit} — quit  {clear} — clear  {end} — bottom  Shift+Tab — mode",
        "tui.help.keys3": "  F2 or /open — copy window ({copy} copies there)",
        "tui.help.keys4": "  In chat: select text → Copy bar",
        "tui.help.macos_scroll": "  ⌃↑/⌃↓/⌃PgUp/PgDn — scroll transcript",
        "tui.help.macos_ru_kb": "  RU keyboard: ,help and .help work like /help; / = Shift+7",
        "tui.help.slash": (
            "  /help /clear /stream /mode /metrics /stop /lang\n"
            "  /copy [/tool|/all]  /open\n"
            "  /new /sessions /switch N /session name <x>\n"
            "  /profile [name|N]  /memory <q>  /last [/N]  /tools\n"
            "  /yes /no  /plan-confirm|auto|refine|reject\n"
            "  /mcp [/list|/install <key|url>|/assign|/test|/tools]"
        ),
        "prompt.lang_block": (
            "## Language\n"
            "The user set the interface language to English (`/lang en`).\n"
            "**You MUST write ALL responses to the user only in English** — explanations, "
            "summaries, clarifying questions, and tool-result commentary — even if the user "
            "writes in another language.\n"
            "Exception: switch language only if the user explicitly asks for a different "
            "language in that specific message."
        ),
    },
    "ru": {
        "lang.current": "Язык интерфейса: {code}",
        "lang.set": "Язык интерфейса: {code}",
        "lang.usage": "Использование: /lang en | /lang ru",
        "lang.invalid": "Неизвестный язык: {value}. Доступно: en, ru",
        "lang.cmd_desc": "Сменить язык интерфейса (en / ru)",
        "cleared": "Чат очищен",
        "unknown_cmd": "Неизвестная команда: {cmd}",
        "type_help": "Введите /help",
        "command_failed": "Ошибка команды: {error}",
        "streaming": "стриминг {state}",
        "mode_set": "режим → {mode}",
        "usage_memory": "Использование: /memory <запрос>",
        "usage_switch": "Использование: /switch N",
        "usage_session_name": "Использование: /session name <имя>",
        "usage_profile": "/profile <имя|N>",
        "profiles_title": "Профили",
        "invalid_profile_num": "неверный номер профиля",
        "unknown_profile": "неизвестный профиль: {name}",
        "models_hint": "Модели: настройте agent_models в профиле (helix models)",
        "memory_cleared": "поиск в памяти сброшен",
        "copy_nothing": "нечего копировать",
        "copy_label": "скопировано",
        "copy_tool": "результат tool скопирован",
        "copy_all": "весь транскрипт скопирован",
        "transcript_empty": "пусто",
        "status_line": "профиль {profile} · режим {mode} · сессия {session}",
        "metrics_error": "ошибка метрик: {error}",
        "skill_not_assigned": "Навык /{name} не назначен агенту '{slot}'",
        "tg.mode": "Режим: {mode}",
        "tg.streaming": "Стриминг: {state}",
        "tg.profile": "Профиль: {name}",
        "tg.profile_same": "Уже профиль {name}",
        "tg.profile_invalid": "Неверный профиль",
        "tg.session": "Сессия: {title}{model}",
        "tg.session_switched": "Сессия переключена",
        "tg.session_invalid": "Неверная сессия",
        "tg.new_session": "Новая сессия",
        "tg.tool_result": "Результат tool",
        "tg.model": "Модель: {label}",
        "tg.error": "Ошибка",
        "tg.unknown_action": "Неизвестное действие",
        "tg.no_tools": "Пока нет вызовов tools в этом чате.",
        "tg.agent_not_ready": "Агент не готов",
        "tg.invalid_preset": "Неверный пресет",
        "tg.invalid_provider": "Неверный провайдер",
        "tg.invalid_model": "Неверная модель",
        "tg.cron_enabled": "Включено: {id}",
        "tg.cron_disabled": "Выключено: {id}",
        "tg.cron_removed": "Удалено: {id}",
        "tg.cron_on": "Вкл",
        "tg.cron_off": "Выкл",
        "tg.cron_how_add": "Как добавить",
        "tg.mcp_none": "Нет MCP серверов. Сначала установи через /mcp install.",
        "tg.mcp_none_remove": "Нет MCP серверов для удаления.",
        "tg.menu.mode": "Режим",
        "tg.menu.profile": "Профиль",
        "tg.menu.sessions": "Сессии",
        "tg.menu.streaming": "Стриминг",
        "tg.menu.models": "Модели",
        "tg.menu.compress": "Сжать контекст",
        "tg.menu.prev": "Пред.",
        "tg.menu.next": "След.",
        "tg.help.title": "Helix — команды",
        "tg.help.chat": "Чат",
        "tg.help.chat_body": "Отправьте текст — агент ответит одним живым сообщением.",
        "tg.help.commands": "Команды (меню слева от поля ввода):",
        "tg.help.buttons": "Кнопки",
        "tg.help.buttons_body": "/mode /profile /sessions /stream — выбор кнопками\n/models — смена LLM до следующего сообщения\n/status /menu — панель быстрых действий",
        "tg.help.extra": "Дополнительно",
        "tg.help.extra_body": (
            "• /memory запрос — семантический поиск\n"
            "• /compress — сжать историю диалога\n"
            "• /init — анализ проекта в .helix/HELIX.md\n"
            "• /profile имя — смена профиля\n"
            "• /plan-confirm · /plan-reject — план\n"
            "• /cron — периодические задачи\n"
            "  /cron add every day at 9 :: задача\n"
            "• /mcp — меню MCP серверов\n"
            "  /mcp remove имя — удалить сервер\n\n"
            "Подтверждения: кнопки под сообщением или /yes /no"
        ),
        "tg.cmd.help": "Справка по командам",
        "tg.cmd.status": "Профиль, режим, сессия",
        "tg.cmd.models": "Сменить LLM модель",
        "tg.cmd.menu": "Панель управления",
        "tg.cmd.mode": "Режим выполнения",
        "tg.cmd.profile": "Профиль Helix",
        "tg.cmd.stream": "Стриминг вкл/выкл",
        "tg.cmd.sessions": "Список сессий",
        "tg.cmd.switch": "Сессия по номеру",
        "tg.cmd.clear": "Очистить контекст чата",
        "tg.cmd.stop": "Остановить задачу",
        "tg.cmd.mcp": "MCP серверы",
        "tg.cmd.new": "Новая сессия",
        "tg.cmd.memory": "Поиск в памяти",
        "tg.cmd.skills": "Список навыков",
        "tg.cmd.subagents": "Субагенты",
        "tg.cmd.tools": "Последние вызовы tools",
        "tg.cmd.last": "Последний результат tool",
        "tg.cmd.metrics": "Метрики агента",
        "tg.cmd.compress": "Сжать контекст",
        "tg.cmd.init": "Анализ проекта → HELIX.md",
        "tg.cmd.cron": "Периодические задачи",
        "tg.cmd.yes": "Подтвердить действие",
        "tg.cmd.no": "Отклонить действие",
        "tg.cmd.lang": "Язык интерфейса (en / ru)",
        "tui.help.title": "Helix code UI",
        "tui.help.keys1": "  Enter — отправить    Shift+Enter — новая строка",
        "tui.help.keys2": "  {quit} — выход  {clear} — очистить  {end} — вниз  Shift+Tab — режим",
        "tui.help.keys3": "  F2 или /open — окно копирования ({copy})",
        "tui.help.keys4": "  В чате: выделите текст → панель Copy",
        "tui.help.macos_scroll": "  ⌃↑/⌃↓/⌃PgUp/PgDn — прокрутка транскрипта",
        "tui.help.macos_ru_kb": "  Русская раскладка: ,help и .help как /help; / = Shift+7",
        "tui.help.slash": (
            "  /help /clear /stream /mode /metrics /stop /lang\n"
            "  /copy [/tool|/all]  /open\n"
            "  /new /sessions /switch N /session name <имя>\n"
            "  /profile [имя|N]  /memory <запрос>  /last [/N]  /tools\n"
            "  /yes /no  /plan-confirm|auto|refine|reject\n"
            "  /mcp [/list|/install <key|url>|/assign|/test|/tools]"
        ),
        "prompt.lang_block": (
            "## Язык\n"
            "Пользователь выбрал язык интерфейса русский (`/lang ru`).\n"
            "**Все ответы пользователю пиши ТОЛЬКО на русском** — пояснения, итоги, "
            "уточняющие вопросы и комментарии к результатам tools — даже если пользователь "
            "пишет на другом языке.\n"
            "Исключение: другой язык только если пользователь явно попросит ответить на нём "
            "в конкретном сообщении."
        ),
    },
}


def t(key: str, locale: str | None = None, **kwargs: object) -> str:
    loc = normalize_locale(locale)
    catalog = MESSAGES.get(loc) or MESSAGES[DEFAULT_LOCALE]
    template = catalog.get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template