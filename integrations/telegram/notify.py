"""Outbound Telegram notifications from CLI (approve, admin alerts)."""

from __future__ import annotations

import asyncio
from typing import Any

from integrations.telegram.access_requests import TelegramAccessRequest
from integrations.telegram.markdown import escape_html
from integrations.telegram.setup_api import TelegramApiError, _api_request


def format_access_approved_message(
    profile: str,
    *,
    access_key: str | None = None,
    key_already_set: bool = False,
) -> str:
    profile_esc = escape_html(profile)
    lines = [
        "✅ <b>Доступ одобрен</b>",
        "",
        f"Ваш профиль Helix: <code>{profile_esc}</code>",
    ]
    if access_key:
        key_esc = escape_html(access_key)
        lines.extend(
            [
                "",
                "🔑 <b>Ключ доступа</b> (сохраните — показывается один раз):",
                f"<code>{key_esc}</code>",
                "",
                "Вы уже подключены к своему профилю — просто пишите боту.",
                f"Для ручного переключения: <code>/profile {profile_esc} {key_esc}</code>",
            ]
        )
    elif key_already_set:
        lines.extend(
            [
                "",
                "Профиль уже был защищён — новый ключ не создан.",
                "Если нужен ключ, обратитесь к администратору.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Можете писать боту — начните с задачи или отправьте /help.",
            ]
        )
    return "\n".join(lines)


async def send_user_message(
    token: str,
    chat_id: int,
    text: str,
    *,
    parse_mode: str = "HTML",
) -> dict[str, Any]:
    """Send a message to a Telegram user (private chat: chat_id == user_id)."""
    params: dict[str, Any] = {
        "chat_id": int(chat_id),
        "text": text,
    }
    if parse_mode:
        params["parse_mode"] = parse_mode
    result = await _api_request(token, "sendMessage", **params)
    return result if isinstance(result, dict) else {}


async def notify_access_approved(
    bot_profile: str,
    user_id: int,
    profile: str,
    *,
    access_key: str | None = None,
    key_already_set: bool = False,
) -> None:
    from integrations.telegram.config import load_telegram_settings
    from integrations.telegram.env_store import load_telegram_env_files

    load_telegram_env_files(bot_profile)
    settings = load_telegram_settings(bot_profile)
    token = settings.bot_token.strip()
    if not token:
        raise TelegramApiError("TELEGRAM_BOT_TOKEN is not configured")

    text = format_access_approved_message(
        profile,
        access_key=access_key,
        key_already_set=key_already_set,
    )
    await send_user_message(token, int(user_id), text)
    try:
        from aiogram import Bot
        from core.i18n import LocaleStore
        from integrations.telegram.commands import enable_chat_menu

        locale = LocaleStore(bot_profile).get()
        bot = Bot(token=token)
        try:
            await enable_chat_menu(bot, int(user_id), locale=locale)
        finally:
            await bot.session.close()
    except Exception:
        pass


def format_access_request_admin_message(
    req: TelegramAccessRequest,
    bot_profile: str,
) -> str:
    profile_esc = escape_html(bot_profile)
    name_esc = escape_html(req.display_name)
    username_line = (
        f"\n<b>Username:</b> @{escape_html(req.username)}"
        if req.username
        else ""
    )
    return "\n".join(
        [
            "🔔 <b>Новый запрос доступа</b>",
            "",
            f"<b>Пользователь:</b> {name_esc}{username_line}",
            f"<b>Telegram ID:</b> <code>{req.user_id}</code>",
            "",
            "Одобрить в CLI (выбор или создание профиля):",
            f"<code>helix -p {profile_esc} telegram requests approve {req.user_id} -i</code>",
            "",
            "Или сразу создать профиль:",
            f"<code>helix -p {profile_esc} telegram requests approve {req.user_id} --create-profile NAME</code>",
            "",
            "Отклонить:",
            f"<code>helix -p {profile_esc} telegram requests reject {req.user_id}</code>",
        ]
    )


async def notify_admin_access_request(
    bot_profile: str,
    req: TelegramAccessRequest,
) -> None:
    from integrations.telegram.admin import load_admin_user_id
    from integrations.telegram.config import load_telegram_settings
    from integrations.telegram.env_store import load_telegram_env_files

    admin_id = load_admin_user_id(bot_profile)
    if admin_id is None or int(admin_id) == int(req.user_id):
        return

    load_telegram_env_files(bot_profile)
    settings = load_telegram_settings(bot_profile)
    token = settings.bot_token.strip()
    if not token:
        return

    text = format_access_request_admin_message(req, bot_profile)
    await send_user_message(token, int(admin_id), text)


def notify_access_approved_sync(
    bot_profile: str,
    user_id: int,
    profile: str,
    *,
    access_key: str | None = None,
    key_already_set: bool = False,
) -> None:
    asyncio.run(
        notify_access_approved(
            bot_profile,
            user_id,
            profile,
            access_key=access_key,
            key_already_set=key_already_set,
        )
    )