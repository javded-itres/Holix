"""MAX bot event dispatcher."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.max.agent_setup import create_agent
from integrations.max.approvals import MaxApprovals
from integrations.max.client import MaxClient
from integrations.max.commands import help_message_markdown, register_bot_commands
from integrations.max.config import MaxSettings, load_max_settings
from integrations.max.file_handler import (
    PendingMaxAttachment,
    build_agent_prompt,
    extract_media_attachments,
    format_files_preview_markdown,
    save_max_attachment,
)
from integrations.max.host import MaxHost
from integrations.max.interactive import dispatch_callback
from integrations.max.markdown import plain_to_max_html
from integrations.max.models import (
    callback_from_update,
    callback_id_from_update,
    callback_payload_from_update,
    callback_reply_target,
    chat_type_from_message,
    chat_type_from_update,
    conversation_id_for_max,
    message_from_update,
    message_has_media,
    message_mid_from_message,
    message_text,
    reply_kwargs_for_session,
    reply_target_from_message,
    sender_user_id,
    update_type,
    user_id_from_update,
    user_meta_from_update,
)
from integrations.max.session import MaxChatSession
from integrations.max.user_profiles import resolve_user_profile
from integrations.telegram.file_handler import SavedTelegramFile

logger = logging.getLogger(__name__)


def _seed_admin_profile_background() -> None:
    try:
        from core.profile_admin_seed import ensure_admin_profile_from_default

        ensure_admin_profile_from_default()
    except Exception:
        pass


def _session_key(user_id: int, chat_id: int | None) -> tuple[int, int]:
    return (chat_id or 0, user_id)


class HelixMaxBot:
    def __init__(self, settings: MaxSettings | None = None, *, profile: str = "default") -> None:
        self.settings = settings or load_max_settings(profile)
        self._sessions: dict[tuple[int, int], MaxChatSession] = {}
        self._agent = None

    async def warmup(self) -> None:
        """Eagerly initialize shared Holix agent (memory, tools, MCP) at bot startup."""
        asyncio.create_task(
            asyncio.to_thread(_seed_admin_profile_background),
            name="max-admin-profile-seed",
        )
        if self._agent is not None:
            return
        logger.info("Initializing Holix agent (profile=%s)…", self.settings.profile)
        self._agent = await create_agent(
            self.settings.profile,
            bot_profile=self.settings.profile,
        )
        model = getattr(self._agent, "model", None) or "—"
        logger.info("Holix agent ready (profile=%s, model=%s)", self.settings.profile, model)

    def _allowed(self, user_id: int) -> bool:
        if self.settings.allow_all:
            return True
        from integrations.max.allowlist import load_allowed_user_ids

        uid = int(user_id)
        if uid in load_allowed_user_ids(self.settings.profile):
            return True
        return resolve_user_profile(self.settings.profile, uid) is not None

    async def _handle_unauthorized(
        self,
        client: MaxClient,
        user_id: int,
        *,
        meta: dict[str, Any] | None = None,
        is_start: bool = False,
    ) -> None:
        from integrations.max.access_requests import register_access_request

        meta = meta or {}
        if not self.settings.access_requests:
            await client.send_message(
                plain_to_max_html("Access denied."),
                user_id=user_id,
                fmt="html",
            )
            return

        req, created = register_access_request(
            self.settings.profile,
            user_id=int(user_id),
            username=meta.get("username"),
            first_name=meta.get("first_name"),
            last_name=meta.get("last_name"),
        )
        if is_start:
            if created:
                text = (
                    "👋 <b>Запрос на доступ отправлен</b>\n\n"
                    f"Ваш MAX user id: <code>{user_id}</code>\n\n"
                    "Администратор получит уведомление в MAX.\n"
                    "Ожидайте одобрения доступа."
                )
            else:
                text = (
                    "⏳ <b>Ожидание одобрения</b>\n\n"
                    f"Ваш запрос уже в очереди (ID: <code>{user_id}</code>).\n"
                    "Администратор получит уведомление после проверки."
                )
        else:
            text = (
                "⏳ <b>Доступ ещё не одобрен</b>\n\n"
                f"Ваш MAX user id: <code>{user_id}</code>.\n"
                "Отправьте /start, если вы ещё не подавали запрос."
            )
        await client.send_message(plain_to_max_html(text), user_id=user_id, fmt="html")
        if created:
            asyncio.create_task(
                self._notify_admin_new_request(req),
                name=f"max-admin-notify-{req.user_id}",
            )

    async def _notify_admin_new_request(self, req: Any) -> None:
        try:
            from integrations.max.notify import notify_admin_access_request

            await notify_admin_access_request(self.settings.profile, req)
        except Exception:
            logger.exception("Failed to notify MAX admin about access request")

    def _default_profile_for_user(self, user_id: int) -> str:
        mapped = resolve_user_profile(self.settings.profile, user_id)
        return mapped or self.settings.profile

    async def _switch_session_profile(self, session: MaxChatSession, profile: str) -> None:
        session.profile = profile
        session.conversation_id = conversation_id_for_max(
            self.settings.profile,
            session.user_id,
            chat_id=session.reply_chat_id,
            chat_type=session.chat_type,
        )
        session.agent = await create_agent(
            profile,
            bot_profile=self.settings.profile,
            max_user_id=session.user_id,
        )
        session.pending_files.clear()
        session.pending_plan_review_id = None
        session.pending_confirmation_message_id = None
        session.pending_plan_message_ids.clear()
        session.approval_callback_tokens.clear()
        session.plan_callback_tokens.clear()
        session._recent_tool_results.clear()
        session._memory_search_query = ""
        session._memory_search_results.clear()

    async def _get_session(
        self,
        user_id: int,
        *,
        reply_user_id: int | None,
        reply_chat_id: int | None,
        chat_type: str | None = None,
    ) -> MaxChatSession:
        key = _session_key(user_id, reply_chat_id)
        if key not in self._sessions:
            holix_profile = self._default_profile_for_user(user_id)
            conv = conversation_id_for_max(
                self.settings.profile,
                user_id,
                chat_id=reply_chat_id,
                chat_type=chat_type,
            )
            self._sessions[key] = MaxChatSession(
                user_id=user_id,
                profile=holix_profile,
                conversation_id=conv,
                bot_profile=self.settings.profile,
                reply_user_id=reply_user_id,
                reply_chat_id=reply_chat_id,
                chat_type=chat_type or "",
            )
        session = self._sessions[key]
        session.reply_user_id = reply_user_id
        session.reply_chat_id = reply_chat_id
        if chat_type:
            session.chat_type = chat_type
        if not session.profile_manual_override:
            target = self._default_profile_for_user(user_id)
            if target != session.profile:
                await self._switch_session_profile(session, target)
        if session.agent is None:
            await self._switch_session_profile(session, session.profile)
        return session

    def _restore_session_model(self, session: MaxChatSession) -> None:
        from core.session_models import restore_session_model

        class _Host:
            def __init__(self, s: MaxChatSession) -> None:
                self._session = s

            @property
            def profile(self) -> str:
                return self._session.profile

            @property
            def conversation_id(self) -> str:
                return self._session.conversation_id

            @property
            def agent(self) -> Any:
                return self._session.agent

        restore_session_model(_Host(session))

    async def handle_update(self, client: MaxClient, update: dict[str, Any]) -> None:
        kind = update_type(update)
        if kind == "bot_started":
            await self._handle_bot_started(client, update)
            return
        if kind == "message_created":
            await self._handle_message_created(client, update)
            return
        if kind == "message_callback":
            await self._handle_message_callback(client, update)
            return
        logger.debug("Ignored MAX update: %s", kind)

    async def _handle_bot_started(self, client: MaxClient, update: dict[str, Any]) -> None:
        uid = user_id_from_update(update)
        if uid is None:
            return
        meta = user_meta_from_update(update)
        if not self._allowed(uid):
            await self._handle_unauthorized(client, uid, meta=meta, is_start=True)
            return
        try:
            from integrations.messenger.locale import (
                bootstrap_messenger_locales,
                messenger_locale,
            )
            from integrations.messenger.platforms import MAX_PLATFORM

            asyncio.create_task(
                asyncio.to_thread(
                    bootstrap_messenger_locales,
                    MAX_PLATFORM,
                    self.settings.profile,
                ),
                name="max-locale-bootstrap",
            )
            locale = messenger_locale(self.settings.profile)
            await register_bot_commands(client, locale=locale)
        except Exception:
            logger.exception("Failed to sync MAX command menu on bot_started")
        await client.send_message(
            plain_to_max_html(
                help_message_markdown()
                + "\n\n**Команды:** введите `/` в поле ввода или отправьте `/menu` — панель управления."
            ),
            user_id=uid,
            fmt="html",
        )

    async def _handle_message_created(self, client: MaxClient, update: dict[str, Any]) -> None:
        msg = message_from_update(update)
        if msg is None:
            return
        uid = sender_user_id(msg)
        if uid is None:
            return
        meta = user_meta_from_update(update)
        if not self._allowed(uid):
            text_peek = message_text(msg).strip().lower()
            is_start = text_peek in {"/start", "start"}
            await self._handle_unauthorized(
                client,
                uid,
                meta=meta,
                is_start=is_start,
            )
            return
        text = message_text(msg).strip()
        logger.info("MAX message from user %s: %r", uid, text[:120] if text else "(media)")
        reply_user_id, reply_chat_id = reply_target_from_message(msg)
        if reply_user_id is None and reply_chat_id is None:
            reply_user_id = uid
        incoming_mid = message_mid_from_message(msg)

        if message_has_media(msg):
            await self._handle_message_media(
                client,
                uid,
                reply_user_id=reply_user_id,
                reply_chat_id=reply_chat_id,
                caption=text,
                message=msg,
            )
            return

        if not text:
            return

        chat_type = chat_type_from_update(update)
        if text.lower() in {"ping", "/start", "start"}:
            if text.lower() in {"/start", "start"}:
                await self._handle_bot_started(client, update)
                return
            await client.send_message(
                "pong",
                **reply_kwargs_for_session(
                    user_id=uid,
                    reply_user_id=reply_user_id,
                    reply_chat_id=reply_chat_id,
                    chat_type=chat_type,
                ),
            )
            return

        session = await self._get_session(
            uid,
            reply_user_id=reply_user_id,
            reply_chat_id=reply_chat_id,
            chat_type=chat_type,
        )
        session.incoming_message_id = incoming_mid
        host = MaxHost(client, session)
        await host.handle_user_text(text)

    async def _handle_message_media(
        self,
        client: MaxClient,
        user_id: int,
        *,
        reply_user_id: int | None,
        reply_chat_id: int | None,
        caption: str,
        message: dict,
    ) -> None:
        from config import settings

        chat_type = chat_type_from_message(message)
        reply = reply_kwargs_for_session(
            user_id=user_id,
            reply_user_id=reply_user_id,
            reply_chat_id=reply_chat_id,
            chat_type=chat_type,
        )
        if not settings.max_files_enabled:
            await client.send_message(
                "📎 Приём файлов отключён. Установите HELIX_MAX_FILES_ENABLED=true.",
                **reply,
            )
            return

        attachments = extract_media_attachments(message)
        if not attachments:
            return

        session = await self._get_session(
            user_id,
            reply_user_id=reply_user_id,
            reply_chat_id=reply_chat_id,
            chat_type=chat_type,
        )
        host = MaxHost(client, session)
        saved, errors = await self._save_attachments(
            client,
            attachments,
            profile=self.settings.profile,
            storage_id=reply_chat_id or user_id,
        )

        if not saved and errors:
            await client.send_message(
                plain_to_max_html(f"📎 **Файлы**\n\n❌ {'; '.join(errors)}"),
                fmt="html",
                **reply,
            )
            return

        preview = format_files_preview_markdown(saved, errors=errors)
        if caption:
            await client.send_message(
                plain_to_max_html(preview),
                fmt="html",
                **reply,
            )
            prompt = build_agent_prompt(caption, saved)
            await host.handle_user_text(prompt)
            return

        session.pending_files.extend(saved)
        count = len(saved)
        await client.send_message(
            plain_to_max_html(
                preview
                + f"\n\nСохранено файлов: {count}. Напишите задачу "
                "(можно добавить ещё файлы, затем одно сообщение с инструкцией)."
            ),
            fmt="html",
            **reply,
        )

    async def _save_attachments(
        self,
        client: MaxClient,
        items: list[PendingMaxAttachment],
        *,
        profile: str,
        storage_id: int,
    ) -> tuple[list[SavedTelegramFile], list[str]]:
        saved: list[SavedTelegramFile] = []
        errors: list[str] = []
        for item in items:
            try:
                saved.append(
                    await save_max_attachment(
                        client,
                        item,
                        profile=profile,
                        storage_id=storage_id,
                    )
                )
            except Exception as exc:
                errors.append(f"{item.file_name}: {exc}")
        return saved, errors

    async def _handle_message_callback(self, client: MaxClient, update: dict[str, Any]) -> None:
        uid = user_id_from_update(update)
        if uid is None:
            return

        callback_id = callback_id_from_update(update)
        payload = callback_payload_from_update(update)
        if not callback_id or not payload:
            return

        reply_user_id, reply_chat_id = callback_reply_target(update)
        if reply_user_id is None and reply_chat_id is None:
            reply_user_id = uid

        if payload.startswith("hx:ar"):
            from integrations.max.access_approval import handle_access_admin_callback
            from integrations.max.keyboards import parse_callback

            parsed = parse_callback(payload)
            if not parsed:
                await client.answer_callback(callback_id, notification="?")
                return
            action, value = parsed
            cb_msg = callback_from_update(update)
            message_id = None
            if isinstance(cb_msg, dict):
                message_id = message_mid_from_message(cb_msg)
            try:
                msg = await handle_access_admin_callback(
                    self.settings.profile,
                    actor_user_id=int(uid),
                    action=action,
                    value=value,
                    client=client,
                    message_id=message_id,
                    reply_user_id=reply_user_id,
                )
                await client.answer_callback(callback_id, notification=(msg[:200] if msg else "OK"))
            except ValueError as exc:
                await client.answer_callback(callback_id, notification=str(exc)[:200])
            except Exception as exc:
                await client.answer_callback(callback_id, notification=f"Ошибка: {exc}"[:200])
            return

        if not self._allowed(uid):
            await client.answer_callback(callback_id, notification="Access denied")
            return

        session = await self._get_session(
            uid,
            reply_user_id=reply_user_id,
            reply_chat_id=reply_chat_id,
            chat_type=chat_type_from_update(update),
        )
        host = MaxHost(client, session)
        approvals = MaxApprovals(client, session)
        notification = ""

        if payload.startswith("cfm:"):
            parts = payload.split(":", 2)
            if len(parts) == 3 and approvals.resolve_confirmation_callback(parts[1], parts[2]):
                await approvals.dismiss_confirmation_ui()
                notification = "✓"
            else:
                notification = "?"
        elif payload.startswith("plan:"):
            parts = payload.split(":", 2)
            if len(parts) == 3 and approvals.resolve_plan_callback(parts[1], parts[2]):
                await approvals.dismiss_plan_review_ui()
                notification = "✓"
            else:
                notification = "?"
        else:
            notification = await dispatch_callback(host, payload) or "OK"

        try:
            await client.answer_callback(callback_id, notification=notification or None)
        except Exception:
            logger.exception("Failed to answer MAX callback %s", callback_id)