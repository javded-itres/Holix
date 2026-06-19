"""Telegram bot command menu and routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.i18n import t

from integrations.messenger.locale import MESSENGER_DEFAULT_LOCALE, messenger_locale

# (command without /, description key in messages catalog)
_TELEGRAM_COMMAND_KEYS: list[tuple[str, str]] = [
    ("help", "tg.cmd.help"),
    ("status", "tg.cmd.status"),
    ("models", "tg.cmd.models"),
    ("menu", "tg.cmd.menu"),
    ("mode", "tg.cmd.mode"),
    ("profile", "tg.cmd.profile"),
    ("stream", "tg.cmd.stream"),
    ("sessions", "tg.cmd.sessions"),
    ("switch", "tg.cmd.switch"),
    ("clear", "tg.cmd.clear"),
    ("stop", "tg.cmd.stop"),
    ("mcp", "tg.cmd.mcp"),
    ("new", "tg.cmd.new"),
    ("memory", "tg.cmd.memory"),
    ("skills", "tg.cmd.skills"),
    ("subagents", "tg.cmd.subagents"),
    ("tools", "tg.cmd.tools"),
    ("last", "tg.cmd.last"),
    ("metrics", "tg.cmd.metrics"),
    ("compress", "tg.cmd.compress"),
    ("init", "tg.cmd.init"),
    ("cron", "tg.cmd.cron"),
    ("message", "tg.cmd.message"),
    ("lang", "tg.cmd.lang"),
    ("yes", "tg.cmd.yes"),
    ("no", "tg.cmd.no"),
]


@dataclass(frozen=True, slots=True)
class TelegramCommandSpec:
    command: str
    description: str
    slash: str

    @classmethod
    def from_pair(cls, command: str, description: str) -> TelegramCommandSpec:
        return cls(command=command, description=description, slash=f"/{command}")


def telegram_menu_commands(locale: str | None = None) -> list[tuple[str, str]]:
    loc = locale or MESSENGER_DEFAULT_LOCALE
    return [(cmd, t(key, loc)) for cmd, key in _TELEGRAM_COMMAND_KEYS]


def command_specs(locale: str | None = None) -> list[TelegramCommandSpec]:
    return [
        TelegramCommandSpec.from_pair(cmd, desc)
        for cmd, desc in telegram_menu_commands(locale)
    ]


def _bot_commands_for_locale(locale: str | None = None) -> list[Any]:
    try:
        from aiogram.types import BotCommand
    except ImportError:
        return []
    return [
        BotCommand(command=spec.command, description=spec.description[:256])
        for spec in command_specs(locale)
    ]


def authorized_telegram_user_ids(bot_profile: str) -> set[int]:
    """User ids that may use the bot (allowlist + profile bindings)."""
    from integrations.telegram.allowlist import load_allowed_user_ids
    from integrations.telegram.user_profiles import load_user_profiles

    ids = load_allowed_user_ids(bot_profile)
    ids.update(load_user_profiles(bot_profile).keys())
    return ids


async def clear_default_bot_menu(bot: Any) -> None:
    """Hide the global command menu (default scope) for new/unauthorized users."""
    try:
        from aiogram.types import BotCommandScopeDefault, MenuButtonDefault
    except ImportError:
        return

    scope = BotCommandScopeDefault()
    try:
        await bot.delete_my_commands(scope=scope)
    except Exception:
        pass
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception:
        pass


async def hide_chat_menu(bot: Any, chat_id: int) -> None:
    """Remove slash-command menu for one private chat."""
    try:
        from aiogram.types import BotCommandScopeChat, MenuButtonDefault
    except ImportError:
        return

    cid = int(chat_id)
    scope = BotCommandScopeChat(chat_id=cid)
    try:
        await bot.delete_my_commands(scope=scope)
    except Exception:
        pass
    try:
        await bot.set_chat_menu_button(chat_id=cid, menu_button=MenuButtonDefault())
    except Exception:
        pass


def _bot_commands_for_user(
    locale: str | None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> list[Any]:
    if bot_profile is not None and user_id is not None:
        from integrations.telegram.command_access import commands_for_user

        specs = commands_for_user(bot_profile, int(user_id), locale=locale)
    else:
        specs = command_specs(locale)
    try:
        from aiogram.types import BotCommand
    except ImportError:
        return []
    return [
        BotCommand(command=spec.command, description=spec.description[:256])
        for spec in specs
    ]


async def enable_chat_menu(
    bot: Any,
    chat_id: int,
    *,
    locale: str | None = None,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> list[str]:
    """Enable slash-command menu for one authorized private chat."""
    try:
        from aiogram.types import BotCommandScopeChat, MenuButtonCommands
    except ImportError:
        return []

    commands = _bot_commands_for_user(
        locale,
        bot_profile=bot_profile,
        user_id=user_id if user_id is not None else int(chat_id),
    )
    if not commands:
        return []

    import asyncio
    import logging

    cid = int(chat_id)
    scope = BotCommandScopeChat(chat_id=cid)
    try:
        await asyncio.wait_for(
            bot.set_my_commands(commands, scope=scope),
            timeout=15.0,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "set_my_commands failed for chat %s: %s", cid, exc
        )
        return []
    try:
        await asyncio.wait_for(
            bot.set_chat_menu_button(chat_id=cid, menu_button=MenuButtonCommands()),
            timeout=10.0,
        )
    except Exception:
        pass
    return [cmd.command for cmd in commands]


async def register_global_bot_commands(bot: Any, *, locale: str | None = None) -> list[str]:
    """Register commands globally (used when HOLIX_TELEGRAM_ALLOW_ALL=true)."""
    try:
        from aiogram.types import BotCommandScopeDefault, MenuButtonCommands
    except ImportError:
        return []

    commands = _bot_commands_for_locale(locale)
    if not commands:
        return []

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
    return [spec.command for spec in command_specs(locale)]


async def register_bot_commands(
    bot: Any,
    *,
    locale: str | None = None,
    bot_profile: str = "default",
) -> list[str]:
    """Apply menu policy: global when allow-all, per-chat for authorized users only."""
    from integrations.telegram.config import load_telegram_settings

    settings = load_telegram_settings(bot_profile)
    if settings.allow_all:
        return await register_global_bot_commands(bot, locale=locale)

    import asyncio

    await clear_default_bot_menu(bot)

    async def _register_for_user(uid: int) -> None:
        try:
            await enable_chat_menu(
                bot,
                uid,
                locale=locale,
                bot_profile=bot_profile,
                user_id=uid,
            )
        except Exception:
            pass

    # Do not block polling startup on per-chat Telegram API calls (can take minutes).
    for uid in sorted(authorized_telegram_user_ids(bot_profile)):
        asyncio.create_task(_register_for_user(uid), name=f"tg-menu-register-{uid}")
    return []


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

    locale = messenger_locale(profile)
    bot = Bot(token=settings.bot_token)
    try:
        return await register_bot_commands(bot, locale=locale, bot_profile=profile)
    finally:
        await bot.session.close()


def help_message_html(
    locale: str | None = None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> str:
    """HTML help for /help and /start."""
    loc = locale or MESSENGER_DEFAULT_LOCALE
    if bot_profile is not None and user_id is not None:
        from integrations.telegram.command_access import commands_for_user

        specs = commands_for_user(bot_profile, int(user_id), locale=loc)
    else:
        specs = command_specs(loc)
    lines = [
        f"<b>{escape_html_simple(t('tg.help.title', loc))}</b>",
        "",
        f"<b>{escape_html_simple(t('tg.help.chat', loc))}</b>",
        escape_html_simple(t("tg.help.chat_body", loc)),
        "",
        f"<b>{escape_html_simple(t('tg.help.commands', loc))}</b>",
    ]
    for spec in specs:
        lines.append(
            f"• <code>/{spec.command}</code> — {escape_html_simple(spec.description)}"
        )
    lines.extend(
        [
            "",
            f"<b>{escape_html_simple(t('tg.help.buttons', loc))}</b>",
            escape_html_simple(t("tg.help.buttons_body", loc)),
            "",
            f"<b>{escape_html_simple(t('tg.help.extra', loc))}</b>",
            escape_html_simple(t("tg.help.extra_body", loc)),
        ]
    )
    return "\n".join(lines)


def escape_html_simple(text: str) -> str:
    from integrations.telegram.markdown import escape_html

    return escape_html(text)