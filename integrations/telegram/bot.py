"""Aiogram bot wiring for Holix."""

from __future__ import annotations

import asyncio
from typing import Any

from integrations.telegram.approvals import TelegramApprovals
from integrations.telegram.commands import (
    command_specs,
    enable_chat_menu,
    help_message_html,
    hide_chat_menu,
    register_bot_commands,
)
from integrations.telegram.config import TelegramSettings, load_telegram_settings
from integrations.telegram.host import TelegramHost
from integrations.telegram.interactive import dispatch_callback
from integrations.telegram.media_group import MediaGroupBuffer, PendingAttachment
from integrations.telegram.session import ChatSession
from integrations.telegram.user_profiles import resolve_user_profile


class HolixTelegramBot:
    def __init__(self, settings: TelegramSettings | None = None, *, profile: str = "default") -> None:
        self.settings = settings or load_telegram_settings(profile)
        self._sessions: dict[int, ChatSession] = {}
        self._dp: Any = None
        self._bot: Any = None
        from config import settings as app_settings

        delay = max(200, int(app_settings.telegram_media_group_delay_ms or 800)) / 1000.0
        self._media_groups = MediaGroupBuffer(delay_sec=delay)
        self._menu_enabled_chats: set[int] = set()

    def _allowed(self, user_id: int) -> bool:
        """Check access with hot reload so CLI approve works without bot restart."""
        if self.settings.allow_all:
            return True
        from integrations.telegram.allowlist import load_allowed_user_ids

        uid = int(user_id)
        if uid in load_allowed_user_ids(self.settings.profile):
            return True
        return resolve_user_profile(self.settings.profile, uid) is not None

    async def _handle_unauthorized(
        self,
        bot: Any,
        message: Any,
        *,
        is_start: bool = False,
    ) -> None:
        from integrations.telegram.access_requests import register_access_request

        user = message.from_user
        if user is None:
            await message.answer("Access denied.")
            return

        if not self.settings.access_requests:
            await message.answer("Access denied.")
            return

        req, created = register_access_request(
            self.settings.profile,
            user_id=int(user.id),
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        )
        if is_start:
            if created:
                text = (
                    "👋 <b>Запрос на доступ отправлен</b>\n\n"
                    f"Ваш Telegram ID: <code>{user.id}</code>\n\n"
                    "Администратор получит уведомление в Telegram.\n"
                    "Ожидайте одобрения доступа."
                )
            else:
                text = (
                    "⏳ <b>Ожидание одобрения</b>\n\n"
                    f"Ваш запрос уже в очереди (ID: <code>{user.id}</code>).\n"
                    "Администратор получит уведомление после проверки."
                )
        else:
            text = (
                "⏳ <b>Доступ ещё не одобрен</b>\n\n"
                f"Ваш Telegram ID: <code>{user.id}</code>.\n"
                "Отправьте /start, если вы ещё не подавали запрос."
            )
        await message.answer(text, parse_mode="HTML")
        if not self.settings.allow_all:
            await hide_chat_menu(bot, message.chat.id)
            self._menu_enabled_chats.discard(message.chat.id)
        if created:
            asyncio.create_task(
                self._notify_admin_new_request(req),
                name=f"tg-admin-notify-{req.user_id}",
            )

    async def _notify_admin_new_request(self, req: Any) -> None:
        try:
            from integrations.telegram.notify import notify_admin_access_request

            await notify_admin_access_request(self.settings.profile, req)
        except Exception:
            pass

    async def _ensure_authorized_menu(self, bot: Any, chat_id: int) -> None:
        if self.settings.allow_all or chat_id in self._menu_enabled_chats:
            return
        from core.i18n import LocaleStore

        locale = LocaleStore(self.settings.profile).get()
        await enable_chat_menu(bot, chat_id, locale=locale)
        self._menu_enabled_chats.add(chat_id)

    def _default_profile_for_user(self, user_id: int) -> str:
        mapped = resolve_user_profile(self.settings.profile, user_id)
        return mapped or self.settings.profile

    async def _switch_session_profile(self, session: ChatSession, profile: str) -> None:
        from integrations.telegram.agent_setup import create_agent

        session.profile = profile
        session.conversation_id = f"tg_{profile}_{session.chat_id}"
        session.agent = await create_agent(profile)
        session.pending_files.clear()
        session.pending_plan_review_id = None
        session.pending_confirmation_message_id = None
        session.pending_plan_message_ids.clear()
        session._recent_tool_results.clear()
        session._memory_search_query = ""
        session._memory_search_results.clear()

    async def _get_session(self, chat_id: int, user_id: int) -> ChatSession:
        if chat_id not in self._sessions:
            profile = self._default_profile_for_user(user_id)
            self._sessions[chat_id] = ChatSession(
                chat_id=chat_id,
                user_id=user_id,
                profile=profile,
                conversation_id=f"tg_{profile}_{chat_id}",
            )
        session = self._sessions[chat_id]
        if not session.profile_manual_override:
            target = self._default_profile_for_user(user_id)
            if target != session.profile:
                await self._switch_session_profile(session, target)
        if session.agent is None:
            await self._switch_session_profile(session, session.profile)
        return session

    async def _handle_transcribed_audio(
        self,
        bot: Any,
        message: Any,
        *,
        file_id: str,
        suffix: str,
        settings: TelegramSettings,
    ) -> None:
        from aiogram.enums import ChatAction

        from config import settings as app_settings
        from integrations.telegram.markdown import escape_html
        from integrations.telegram.voice_handler import (
            format_transcription_preview,
            process_voice_message,
        )

        if not app_settings.telegram_voice_enabled:
            await message.answer(
                "🎙️ Распознавание голоса отключено. "
                "Установите HOLIX_TELEGRAM_VOICE_ENABLED=true в .env.",
            )
            return

        await bot.send_chat_action(message.chat.id, action=ChatAction.TYPING)

        session = await self._get_session(message.chat.id, message.from_user.id)
        try:
            transcribed = await process_voice_message(
                bot,
                file_id,
                suffix=suffix,
                profile=session.profile,
            )
        except RuntimeError as exc:
            await message.answer(
                f"🎙️ <b>Голосовое сообщение</b>\n\n"
                f"❌ Не удалось распознать: {escape_html(str(exc))}",
                parse_mode="HTML",
            )
            return
        except Exception as exc:
            await message.answer(
                f"🎙️ <b>Голосовое сообщение</b>\n\n"
                f"❌ Ошибка распознавания: {escape_html(str(exc))}",
                parse_mode="HTML",
            )
            return

        if not transcribed:
            await message.answer(
                "🎙️ <b>Голосовое сообщение</b>\n\n"
                "❌ Не удалось распознать речь. Попробуйте ещё раз.",
                parse_mode="HTML",
            )
            return

        preview = format_transcription_preview(transcribed)
        await message.answer(
            f"🎙️ <b>Распознано:</b>\n\n<i>{preview}</i>",
            parse_mode="HTML",
        )

        host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
        await host.handle_user_text(transcribed)

    async def _enqueue_file_attachment(
        self,
        bot: Any,
        message: Any,
        *,
        attachment: PendingAttachment,
        settings: TelegramSettings,
    ) -> None:
        from config import settings as app_settings

        if not app_settings.telegram_files_enabled:
            await message.answer(
                "📎 Приём файлов отключён. Установите HOLIX_TELEGRAM_FILES_ENABLED=true.",
            )
            return

        caption = (getattr(message, "caption", None) or "").strip()
        media_group_id = getattr(message, "media_group_id", None)

        if not media_group_id:
            await self._finalize_attachments(
                bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                items=[attachment],
                caption=caption,
                settings=settings,
            )
            return

        async def _flush(batch) -> None:
            await self._finalize_attachments(
                bot,
                chat_id=batch.chat_id,
                user_id=batch.user_id,
                items=list(batch.items),
                caption=batch.caption,
                settings=settings,
            )

        await self._media_groups.add(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            media_group_id=str(media_group_id),
            item=attachment,
            caption=caption,
            on_flush=_flush,
        )

    async def _finalize_attachments(
        self,
        bot: Any,
        *,
        chat_id: int,
        user_id: int,
        items: list[PendingAttachment],
        caption: str,
        settings: TelegramSettings,
    ) -> None:
        from aiogram.enums import ChatAction

        from integrations.telegram.file_handler import (
            SavedTelegramFile,
            build_agent_prompt,
            format_files_preview,
            save_telegram_attachment,
        )
        from integrations.telegram.markdown import escape_html

        await bot.send_chat_action(chat_id, action=ChatAction.TYPING)

        session = await self._get_session(chat_id, user_id)
        saved_files: list[SavedTelegramFile] = []
        errors: list[str] = []

        for item in items:
            try:
                saved = await save_telegram_attachment(
                    bot,
                    item.file_id,
                    profile=session.profile,
                    chat_id=chat_id,
                    file_name=item.file_name,
                    mime_type=item.mime_type,
                    file_size=item.file_size,
                )
                saved_files.append(saved)
            except Exception as exc:
                errors.append(f"{item.file_name}: {exc}")

        if not saved_files and errors:
            await bot.send_message(
                chat_id,
                f"📎 <b>Файлы</b>\n\n❌ {escape_html('; '.join(errors))}",
                parse_mode="HTML",
            )
            return

        host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
        preview = format_files_preview(saved_files, errors=errors)

        if caption:
            await bot.send_message(chat_id, preview, parse_mode="HTML")
            prompt = build_agent_prompt(caption, saved_files)
            await host.handle_user_text(prompt)
            return

        session.pending_files.extend(saved_files)
        count = len(saved_files)
        await bot.send_message(
            chat_id,
            preview
            + f"\n\nСохранено файлов: {count}. Напишите задачу "
            "(можно добавить ещё файлы, затем одно сообщение с инструкцией).",
            parse_mode="HTML",
        )

    async def _flush_pending_files(
        self,
        bot: Any,
        message: Any,
        *,
        user_text: str,
        settings: TelegramSettings,
    ) -> bool:
        session = await self._get_session(message.chat.id, message.from_user.id)
        if not session.pending_files:
            return False

        from integrations.telegram.file_handler import build_agent_prompt

        files = list(session.pending_files)
        session.pending_files.clear()
        host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
        prompt = build_agent_prompt(user_text, files)
        await host.handle_user_text(prompt)
        return True

    def build(self) -> tuple[Any, Any]:
        try:
            from aiogram import Bot, Dispatcher, F
            from aiogram.filters import Command, CommandStart
            from aiogram.types import CallbackQuery, Message
        except ImportError as e:
            raise ImportError(
                "Telegram support requires aiogram: uv sync --extra telegram"
            ) from e

        from integrations.telegram.voice_handler import suffix_for_audio

        bot = Bot(token=self.settings.bot_token)
        dp = Dispatcher()
        settings = self.settings
        menu_commands = [spec.command for spec in command_specs()]

        @dp.startup()
        async def _on_startup() -> None:
            from core.i18n import LocaleStore

            locale = LocaleStore(settings.profile).get()
            registered = await register_bot_commands(
                bot,
                locale=locale,
                bot_profile=settings.profile,
            )
            if registered:
                print(f"Telegram menu: {len(registered)} commands", flush=True)
            elif not settings.allow_all:
                print("Telegram menu: hidden until users are approved", flush=True)
            from integrations.telegram.voice_handler import warm_local_whisper_model_async

            asyncio.create_task(
                warm_local_whisper_model_async(profile=settings.profile),
                name="whisper-model-download",
            )

        @dp.message(CommandStart())
        async def cmd_start(message: Message) -> None:
            if message.from_user is None:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message, is_start=True)
                return
            await self._ensure_authorized_menu(bot, message.chat.id)
            await message.answer(help_message_html(), parse_mode="HTML")

        @dp.message(Command(*menu_commands))
        async def on_menu_command(message: Message) -> None:
            if message.from_user is None or not message.text:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            await self._ensure_authorized_menu(bot, message.chat.id)
            session = await self._get_session(message.chat.id, message.from_user.id)
            host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
            await host.handle_user_text(message.text.strip())

        @dp.message(F.text)
        async def on_text(message: Message) -> None:
            if message.from_user is None or message.text is None:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            await self._ensure_authorized_menu(bot, message.chat.id)
            if message.text.strip().startswith("/"):
                return
            if await self._flush_pending_files(
                bot,
                message,
                user_text=message.text,
                settings=settings,
            ):
                return
            session = await self._get_session(message.chat.id, message.from_user.id)
            host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
            await host.handle_user_text(message.text)

        @dp.message(F.voice)
        async def on_voice(message: Message) -> None:
            """Handle voice notes: download → Whisper → process as text."""
            if message.from_user is None or message.voice is None:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            await self._handle_transcribed_audio(
                bot,
                message,
                file_id=message.voice.file_id,
                suffix=".ogg",
                settings=settings,
            )

        @dp.message(F.audio)
        async def on_audio(message: Message) -> None:
            """Handle audio attachments (mp3/m4a) the same way as voice notes."""
            if message.from_user is None or message.audio is None:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            suffix = suffix_for_audio(mime_type=message.audio.mime_type)
            await self._handle_transcribed_audio(
                bot,
                message,
                file_id=message.audio.file_id,
                suffix=suffix,
                settings=settings,
            )

        @dp.message(F.photo)
        async def on_photo(message: Message) -> None:
            if message.from_user is None or not message.photo:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            photo = message.photo[-1]
            await self._enqueue_file_attachment(
                bot,
                message,
                attachment=PendingAttachment(
                    file_id=photo.file_id,
                    file_name=f"photo_{photo.file_unique_id}.jpg",
                    mime_type="image/jpeg",
                    file_size=int(photo.file_size or 0),
                ),
                settings=settings,
            )

        @dp.message(F.document)
        async def on_document(message: Message) -> None:
            if message.from_user is None or message.document is None:
                return
            if not self._allowed(message.from_user.id):
                await self._handle_unauthorized(bot, message)
                return
            doc = message.document
            file_name = doc.file_name or f"document_{doc.file_unique_id}"
            await self._enqueue_file_attachment(
                bot,
                message,
                attachment=PendingAttachment(
                    file_id=doc.file_id,
                    file_name=file_name,
                    mime_type=str(doc.mime_type or ""),
                    file_size=int(doc.file_size or 0),
                ),
                settings=settings,
            )

        @dp.callback_query(F.data.startswith("cfm:"))
        async def on_confirm_cb(query: CallbackQuery) -> None:
            if query.from_user is None or not query.data:
                return
            if not self._allowed(query.from_user.id):
                await query.answer("Access pending approval.", show_alert=True)
                return
            parts = query.data.split(":")
            if len(parts) != 3:
                await query.answer("Invalid.", show_alert=True)
                return
            _, cid, code = parts
            session = await self._get_session(query.message.chat.id, query.from_user.id)
            approvals = TelegramApprovals(bot, session)
            if approvals.resolve_confirmation_callback(cid, code):
                await approvals.dismiss_confirmation_ui()
                await query.answer("Applied.")
            else:
                await query.answer("Failed or expired.", show_alert=True)

        @dp.callback_query(F.data.startswith("mcp:"))
        async def on_mcp_cb(query: CallbackQuery) -> None:
            if query.from_user is None or not query.data or query.message is None:
                return
            if not self._allowed(query.from_user.id):
                await query.answer("Access denied.", show_alert=True)
                return
            session = await self._get_session(query.message.chat.id, query.from_user.id)
            host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
            value = query.data.split(":", 1)[1] if ":" in query.data else ""
            try:
                from integrations.telegram.interactive import TelegramInteractive

                await TelegramInteractive(host)._handle_mcp_callback(value)
                await query.answer("OK")
            except Exception as exc:
                await query.answer(f"Error: {exc}"[:200], show_alert=True)

        @dp.callback_query(F.data.startswith("hx:"))
        async def on_holix_ui_cb(query: CallbackQuery) -> None:
            if query.from_user is None or not query.data or query.message is None:
                return
            if not self._allowed(query.from_user.id):
                await query.answer("Access denied.", show_alert=True)
                return
            session = await self._get_session(query.message.chat.id, query.from_user.id)
            host = TelegramHost(bot, session, edit_interval_ms=settings.edit_interval_ms)
            try:
                msg = await dispatch_callback(host, query.data)
                await query.answer(msg[:200] if msg else "OK")
            except Exception as exc:
                await query.answer(f"Error: {exc}"[:200], show_alert=True)

        @dp.callback_query(F.data.startswith("plan:"))
        async def on_plan_cb(query: CallbackQuery) -> None:
            if query.from_user is None or not query.data:
                return
            if not self._allowed(query.from_user.id):
                await query.answer("Access denied.", show_alert=True)
                return
            parts = query.data.split(":")
            if len(parts) != 3:
                await query.answer("Invalid.", show_alert=True)
                return
            _, rid, action = parts
            session = await self._get_session(query.message.chat.id, query.from_user.id)
            approvals = TelegramApprovals(bot, session)
            if approvals.resolve_plan_callback(rid, action):
                await approvals.dismiss_plan_review_ui()
                await query.answer("Plan updated.")
            else:
                await query.answer("Failed or expired.", show_alert=True)

        self._bot = bot
        self._dp = dp
        return bot, dp

    async def run_polling(self) -> None:
        from config import settings

        if (
            not self.settings.allow_all
            and not self.settings.allowed_ids()
            and not self.settings.can_start_without_allowlist()
        ):
            if settings.is_production and settings.telegram_require_allowlist_in_production:
                raise RuntimeError(
                    "HOLIX_TELEGRAM_ALLOWED_USERS is required when HOLIX_ENV=production "
                    "(or enable HOLIX_TELEGRAM_ACCESS_REQUESTS=true)"
                )
            raise RuntimeError(
                "HOLIX_TELEGRAM_ALLOWED_USERS is required "
                "(or HOLIX_TELEGRAM_ACCESS_REQUESTS=true / HOLIX_TELEGRAM_ALLOW_ALL=true)"
            )
        if not self.settings.bot_token:
            raise RuntimeError("Set TELEGRAM_BOT_TOKEN in environment or .env")
        bot, dp = self.build()
        await dp.start_polling(bot)