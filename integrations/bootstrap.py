"""Register integration hooks into core (call once at process startup)."""

from __future__ import annotations

from core.plugins.hooks import (
    register_companion_hooks,
    register_notify_hooks,
    register_profile_lifecycle_hooks,
)


def register_integration_hooks() -> None:
    """Wire Telegram/MAX/CLI companion and notify implementations into core."""
    _register_companions()
    _register_notify()
    _register_profile_lifecycle()


def _register_companions() -> None:
    from cli.services.supervisor import telegram_should_start
    from integrations.max.gateway_routes import max_should_poll

    async def start_telegram(profile: str) -> None:
        from integrations.telegram.bot import HolixTelegramBot

        bot = HolixTelegramBot(profile=profile)
        await bot.run_polling()

    async def start_max(profile: str) -> None:
        from integrations.max.config import load_max_settings
        from integrations.max.polling import run_polling

        await run_polling(load_max_settings(profile), profile=profile)

    register_companion_hooks(
        telegram_should_start=telegram_should_start,
        start_telegram=start_telegram,
        max_should_poll=max_should_poll,
        start_max=start_max,
    )


def _register_notify() -> None:
    async def send_telegram(
        chat_id: int,
        message: str,
        *,
        bot_token: str | None = None,
        profile: str = "default",
        parse_mode: str = "HTML",
    ) -> bool:
        import logging

        logger = logging.getLogger(__name__)
        try:
            from aiogram import Bot
        except ImportError:
            logger.warning("aiogram not installed, cannot send Telegram notification")
            return False

        if not bot_token:
            from integrations.telegram.config import load_telegram_settings

            bot_token = load_telegram_settings(profile).bot_token
        if not bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        bot = Bot(token=bot_token)
        try:
            await bot.send_message(chat_id, message, parse_mode=parse_mode)
            return True
        except Exception as e:
            logger.warning("Failed to send Telegram notification: %s", e)
            return False
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

    async def send_max(
        message: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        profile: str = "default",
    ) -> bool:
        import logging

        logger = logging.getLogger(__name__)
        try:
            from integrations.max.client import MaxClient
            from integrations.max.config import load_max_settings
            from integrations.max.markdown import prepare_max_markdown
        except ImportError:
            logger.warning("MAX integration unavailable for cron notification")
            return False

        settings = load_max_settings(profile)
        if not settings.bot_token:
            logger.warning("MAX bot token not configured")
            return False

        client = MaxClient(settings.bot_token)
        try:
            text = prepare_max_markdown(message)
            if chat_id is not None:
                await client.send_message(text, fmt="markdown", chat_id=chat_id)
            else:
                await client.send_message(text, fmt="markdown", user_id=user_id)
            return True
        except Exception as exc:
            logger.warning("Failed to send MAX cron notification: %s", exc)
            return False
        finally:
            try:
                await client.close()
            except Exception:
                pass

    register_notify_hooks(send_telegram=send_telegram, send_max=send_max)


def _register_profile_lifecycle() -> None:
    from integrations.telegram.admin import DEFAULT_ADMIN_PROFILE

    def find_telegram_users(target_profile: str) -> list[tuple[str, int]]:
        from core.profile import ProfileManager
        from integrations.telegram.user_profiles import load_user_profiles

        name = target_profile.strip()
        if not name:
            return []
        manager = ProfileManager()
        hits: list[tuple[str, int]] = []
        for bot_profile in manager.list_profiles():
            for uid, mapped in load_user_profiles(bot_profile).items():
                if mapped == name:
                    hits.append((bot_profile, int(uid)))
        return hits

    def format_deletion_message(profile: str) -> str:
        from integrations.telegram.markdown import escape_html

        profile_esc = escape_html(profile)
        return "\n".join(
            [
                "⚠️ <b>Профиль Holix удалён</b>",
                "",
                f"Ваш профиль <code>{profile_esc}</code> удалён администратором с сервера.",
                "Данные профиля (память, workspace, настройки) больше недоступны.",
                "",
                "Если нужен новый доступ — отправьте запрос администратору или "
                "используйте /start в боте.",
            ]
        )

    async def notify_deletion(
        bot_profile: str,
        user_id: int,
        deleted_profile: str,
    ) -> None:
        from integrations.telegram.config import load_telegram_settings
        from integrations.telegram.env_store import load_telegram_env_files
        from integrations.telegram.notify import send_user_message

        load_telegram_env_files(bot_profile)
        token = load_telegram_settings(bot_profile).bot_token.strip()
        if not token:
            raise RuntimeError(
                f"TELEGRAM_BOT_TOKEN is not configured for bot profile '{bot_profile}'"
            )
        await send_user_message(
            token,
            int(user_id),
            format_deletion_message(deleted_profile),
        )

    def notify_deletion_sync(
        bot_profile: str,
        user_id: int,
        deleted_profile: str,
    ) -> None:
        from core.asyncio_sync import run_coroutine_sync

        run_coroutine_sync(notify_deletion(bot_profile, user_id, deleted_profile))

    def remove_bindings(target_profile: str) -> int:
        from core.profile import ProfileManager
        from integrations.telegram.user_profiles import load_user_profiles, save_user_profiles

        name = target_profile.strip()
        removed = 0
        manager = ProfileManager()
        for bot_profile in manager.list_profiles():
            mapping = load_user_profiles(bot_profile)
            changed = False
            for uid, mapped in list(mapping.items()):
                if mapped == name:
                    del mapping[uid]
                    removed += 1
                    changed = True
            if changed:
                save_user_profiles(bot_profile, mapping)
        return removed

    register_profile_lifecycle_hooks(
        find_telegram_users=find_telegram_users,
        notify_deletion_sync=notify_deletion_sync,
        remove_bindings=remove_bindings,
        format_deletion_message=format_deletion_message,
        default_admin_profile=DEFAULT_ADMIN_PROFILE,
    )
