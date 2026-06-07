"""Telegram bot command menu and routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# (command without /, description ≤ 256 chars for Bot API)
TELEGRAM_MENU_COMMANDS: list[tuple[str, str]] = [
    ("help", "Справка по командам"),
    ("status", "Профиль, режим, сессия"),
    ("models", "Сменить LLM модель"),
    ("menu", "Панель управления"),
    ("mode", "Режим выполнения"),
    ("profile", "Профиль Helix"),
    ("stream", "Стриминг вкл/выкл"),
    ("sessions", "Список сессий"),
    ("switch", "Сессия по номеру"),
    ("clear", "Очистить контекст чата"),
    ("stop", "Остановить задачу"),
    ("mcp", "MCP серверы (доп. инструменты)"),
    ("new", "Новая сессия"),
    ("memory", "Поиск в памяти"),
    ("skills", "Список навыков (skills)"),
    ("subagents", "Субагенты: список задач"),
    ("tools", "Последние вызовы tools"),
    ("last", "Последний результат tool"),
    ("metrics", "Метрики агента"),
    ("compress", "Сжать контекст диалога"),
    ("init", "Анализ проекта → .helix/HELIX.md"),
    ("cron", "Периодические задачи (cron)"),
    ("yes", "Подтвердить действие"),
    ("no", "Отклонить действие"),
]


@dataclass(frozen=True, slots=True)
class TelegramCommandSpec:
    command: str
    description: str
    slash: str

    @classmethod
    def from_pair(cls, command: str, description: str) -> TelegramCommandSpec:
        return cls(command=command, description=description, slash=f"/{command}")


def command_specs() -> list[TelegramCommandSpec]:
    return [TelegramCommandSpec.from_pair(c, d) for c, d in TELEGRAM_MENU_COMMANDS]


async def register_bot_commands(bot: Any) -> list[str]:
    """Register commands in Telegram menu (side button + autocomplete)."""
    try:
        from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
    except ImportError:
        return []

    specs = command_specs()
    commands = [
        BotCommand(command=spec.command, description=spec.description[:256])
        for spec in specs
    ]
    scope = BotCommandScopeDefault()
    try:
        await bot.delete_my_commands(scope=scope)
    except Exception:
        pass
    await bot.set_my_commands(commands, scope=scope)
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception:
        pass
    return [spec.command for spec in specs]


async def sync_bot_menu(profile: str = "default") -> list[str]:
    """Push command menu to Telegram API (no polling)."""
    from integrations.telegram.config import load_telegram_settings

    settings = load_telegram_settings(profile)
    if not settings.bot_token:
        raise RuntimeError("Telegram bot token not configured")

    try:
        from aiogram import Bot
    except ImportError as e:
        raise ImportError("uv sync --extra telegram") from e

    bot = Bot(token=settings.bot_token)
    try:
        return await register_bot_commands(bot)
    finally:
        await bot.session.close()


def help_message_html() -> str:
    """HTML help for /help and /start."""
    lines = [
        "<b>Helix — команды</b>",
        "",
        "<b>Чат</b>",
        "Отправьте текст — агент ответит одним живым сообщением.",
        "",
        "<b>Команды</b> (меню слева от поля ввода):",
    ]
    for spec in command_specs():
        lines.append(f"• <code>/{spec.command}</code> — {escape_html_simple(spec.description)}")
    lines.extend(
        [
            "",
            "<b>Кнопки</b>",
            "<code>/mode</code> <code>/profile</code> <code>/sessions</code> <code>/stream</code> — выбор кнопками",
            "<code>/models</code> — смена LLM на лету (до следующего сообщения)",
            "<code>/status</code> <code>/menu</code> — панель быстрых действий",
            "",
            "<b>Дополнительно</b>",
            "• <code>/memory запрос</code> — семантический поиск",
            "• <code>/compress</code> — сжать историю диалога (освободить окно контекста)",
            "• <code>/init</code> — глубокий анализ проекта в .helix/HELIX.md",
            "• <code>/profile имя</code> — смена профиля текстом",
            "• <code>/plan-confirm</code> · <code>/plan-reject</code> — план",
            "• <code>/cron</code> — периодические задачи (список, вкл/выкл, удаление)",
            "  <code>/cron add every day at 9 :: задача</code>",
            "• <code>/mcp</code> — меню MCP серверов (list / install / assign / remove / test / tools)",
            "  <code>/mcp remove имя</code> — удалить MCP сервер",
            "",
            "Подтверждения: кнопки под сообщением или <code>/yes</code> <code>/no</code>",
        ]
    )
    return "\n".join(lines)


def escape_html_simple(text: str) -> str:
    from integrations.telegram.markdown import escape_html

    return escape_html(text)