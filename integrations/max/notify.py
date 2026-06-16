"""Outbound MAX notifications from CLI and bot (approve, admin alerts)."""

from __future__ import annotations

from integrations.max.access_requests import MaxAccessRequest
from integrations.max.client import MaxClient
from integrations.max.markdown import escape_html, truncate_max_html


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
        f"Ваш профиль Holix: <code>{profile_esc}</code>",
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
    client: MaxClient,
    user_id: int,
    text: str,
    *,
    attachments: list[dict] | None = None,
) -> dict:
    return await client.send_message(
        truncate_max_html(text),
        user_id=int(user_id),
        fmt="html",
        attachments=attachments,
    )


async def notify_access_approved(
    bot_profile: str,
    user_id: int,
    profile: str,
    *,
    access_key: str | None = None,
    key_already_set: bool = False,
) -> None:
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import load_max_env_files

    load_max_env_files(bot_profile)
    settings = load_max_settings(bot_profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not configured")

    text = format_access_approved_message(
        profile,
        access_key=access_key,
        key_already_set=key_already_set,
    )
    async with MaxClient(token) as client:
        await send_user_message(client, int(user_id), text)
        try:
            from integrations.messenger.locale import messenger_locale

            from integrations.max.commands import register_bot_commands

            locale = messenger_locale(bot_profile)
            await register_bot_commands(client, locale=locale)
        except Exception:
            pass


def format_access_request_admin_message(
    req: MaxAccessRequest,
    bot_profile: str,
    *,
    pick_profile: bool = False,
) -> str:
    from integrations.max.access_approval import suggest_holix_profile_name

    name_esc = escape_html(req.display_name)
    username_line = (
        f"\n<b>Username:</b> @{escape_html(req.username)}"
        if req.username
        else ""
    )
    suggested = suggest_holix_profile_name(req)
    if pick_profile:
        header = "📁 <b>Выбор профиля Holix</b>"
        footer = "Нажмите кнопку профиля или создайте новый."
    else:
        header = "🔔 <b>Новый запрос доступа</b>"
        footer = (
            "Одобрите или отклоните кнопками ниже.\n"
            f"Быстрое одобрение создаст профиль <code>{escape_html(suggested)}</code> "
            "(если его ещё нет)."
        )
    return "\n".join(
        [
            header,
            "",
            f"<b>Пользователь:</b> {name_esc}{username_line}",
            f"<b>MAX user id:</b> <code>{req.user_id}</code>",
            "",
            footer,
        ]
    )


async def notify_admin_access_request(
    bot_profile: str,
    req: MaxAccessRequest,
) -> None:
    from integrations.max.admin import load_admin_user_id
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import load_max_env_files
    from integrations.max.keyboards import access_request_admin_keyboard

    admin_id = load_admin_user_id(bot_profile)
    if admin_id is None or int(admin_id) == int(req.user_id):
        return

    load_max_env_files(bot_profile)
    settings = load_max_settings(bot_profile)
    token = settings.access_token.strip()
    if not token:
        return

    text = format_access_request_admin_message(req, bot_profile)
    keyboard = access_request_admin_keyboard(req.user_id)
    async with MaxClient(token) as client:
        await send_user_message(client, int(admin_id), text, attachments=[keyboard])


async def notify_access_rejected(bot_profile: str, user_id: int) -> None:
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import load_max_env_files

    load_max_env_files(bot_profile)
    settings = load_max_settings(bot_profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not configured")

    text = (
        "❌ <b>Доступ не одобрен</b>\n\n"
        "Администратор отклонил запрос. "
        "Если это ошибка — свяжитесь с администратором Holix."
    )
    async with MaxClient(token) as client:
        await send_user_message(client, int(user_id), text)


async def notify_access_revoked(bot_profile: str, user_id: int) -> None:
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import load_max_env_files

    load_max_env_files(bot_profile)
    settings = load_max_settings(bot_profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not configured")

    text = (
        "❌ <b>Доступ отозван</b>\n\n"
        "Администратор удалил ваш доступ к боту Holix.\n"
        "Чтобы снова запросить доступ — отправьте /start."
    )
    async with MaxClient(token) as client:
        await send_user_message(client, int(user_id), text)


def notify_access_revoked_sync(bot_profile: str, user_id: int) -> None:
    from core.asyncio_sync import run_coroutine_sync

    run_coroutine_sync(notify_access_revoked(bot_profile, user_id))


def notify_access_rejected_sync(bot_profile: str, user_id: int) -> None:
    from core.asyncio_sync import run_coroutine_sync

    run_coroutine_sync(notify_access_rejected(bot_profile, user_id))


def notify_access_approved_sync(
    bot_profile: str,
    user_id: int,
    profile: str,
    *,
    access_key: str | None = None,
    key_already_set: bool = False,
) -> None:
    from core.asyncio_sync import run_coroutine_sync

    run_coroutine_sync(
        notify_access_approved(
            bot_profile,
            user_id,
            profile,
            access_key=access_key,
            key_already_set=key_already_set,
        )
    )