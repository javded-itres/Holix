"""Interactive pickers and callback handling for Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.i18n import t

from integrations.messenger.locale import messenger_host_locale
from integrations.telegram.keyboards import (
    MODE_LABELS,
    SKILLS_PAGE_SIZE,
    mode_picker_html,
    mode_picker_keyboard,
    models_provider_keyboard,
    models_root_keyboard,
    parse_callback,
    pipeline_picker_keyboard,
    profile_picker_keyboard,
    reflexion_picker_keyboard,
    sessions_picker_keyboard,
    skills_picker_keyboard,
    status_menu_keyboard,
    stream_picker_keyboard,
    subagents_picker_keyboard,
    tools_picker_keyboard,
)
from integrations.telegram.markdown import escape_html
from integrations.telegram.model_switch import (
    MODELS_PAGE_SIZE,
    PROVIDERS_PAGE_SIZE,
    apply_preset_index,
    apply_provider_model_index,
    build_models_menu,
    current_model_label,
)

if TYPE_CHECKING:
    from integrations.telegram.host import TelegramHost


def profile_model_summary(profile: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Return (default line, agent rows name/provider/model)."""
    from cli.core import ProfileManager

    try:
        cfg = ProfileManager().load_profile(profile)
    except Exception:
        return "—", []

    rows: list[tuple[str, str, str]] = []
    default_model = cfg.model
    default_provider = cfg.default_provider or "legacy"
    if cfg.default_provider and cfg.providers:
        pdata = cfg.providers.get(cfg.default_provider) or {}
        default_model = pdata.get("default_model") or cfg.model
        default_provider = cfg.default_provider

    rows.append(("main", default_provider, default_model))

    for name, raw in (cfg.agent_models or {}).items():
        if isinstance(raw, dict):
            provider = raw.get("provider", default_provider)
            model = raw.get("model", "?")
        else:
            provider = default_provider
            model = str(raw)
        rows.append((name, provider, model))

    headline = f"{default_provider} / {default_model}"
    return headline, rows


class TelegramInteractive:
    def __init__(self, host: TelegramHost) -> None:
        self._host = host

    @property
    def _session(self) -> Any:
        return self._host._session

    async def _deny_menu_command(self, command_token: str) -> bool:
        from integrations.telegram.command_access import is_command_allowed

        if is_command_allowed(
            command_token,
            self._session.bot_profile,
            self._session.user_id,
        ):
            return False
        lang = messenger_host_locale(self._host)
        await self._host._send_html(escape_html(t("tg.menu_unavailable", lang)))
        return True

    async def handle_slash(self, command: str) -> bool:
        """Return True if handled (skip AgentCommands)."""
        from cli.shared.slash_input import (
            is_mode_slash,
            is_models_slash,
            normalize_slash_input,
            slash_command_token,
        )

        cmd = normalize_slash_input(command.strip())
        lower = cmd.lower()
        parts = lower.split()
        cmd_token = slash_command_token(cmd)

        if await self._deny_menu_command(cmd_token.lstrip("/").split()[0]):
            return True

        if is_models_slash(cmd):
            await self.show_models()
            return True

        if is_mode_slash(cmd):
            if len(parts) > 1 and parts[1] in self._host._execution_modes:
                self._host._execution_mode_index = self._host._execution_modes.index(parts[1])
                lang = messenger_host_locale(self._host)
                await self._host._send_html(
                    f"{escape_html(t('tg.mode', lang, mode=''))}<code>{escape_html(parts[1])}</code>"
                )
            else:
                await self.show_mode_picker()
            return True

        if lower.startswith("/stream"):
            if len(parts) > 1:
                self._host.streaming_enabled = parts[1] in ("on", "true", "1")
                state = "on" if self._host.streaming_enabled else "off"
                await self._host._send_html(
                    escape_html(t("tg.streaming", messenger_host_locale(self._host), state=state))
                )
            else:
                await self.show_stream_picker()
            return True

        if lower.startswith("/profile"):
            if len(parts) >= 2:
                return False
            await self.show_profile_picker()
            return True

        if lower.startswith("/message"):
            from integrations.telegram.admin_broadcast import handle_admin_message_command

            await handle_admin_message_command(self._host, cmd)
            return True

        if lower in ("/sessions",):
            await self.show_sessions_picker()
            return True

        if lower.startswith("/switch"):
            if len(parts) >= 2 and parts[1].isdigit():
                return False
            await self.show_sessions_picker()
            return True

        if lower == "/tools":
            await self.show_tools_picker()
            return True

        if cmd_token == "/skills":
            from cli.shared.commands.skills_commands import run_skills_command

            await run_skills_command(self._host, cmd)
            return True

        if lower in ("/subagents", "/subagent-list") or lower == "/subagent list":
            await self.show_subagent_live_list()
            return True
        if lower.startswith("/subagent"):
            from cli.shared.commands.subagent_commands import run_subagents_command

            await run_subagents_command(self._host, cmd)
            return True

        if lower in ("/status",):
            await self.show_status()
            return True

        if lower in ("/menu",):
            await self.show_status()
            return True

        if lower.startswith("/mcp"):
            await self.show_mcp_menu(cmd)
            return True

        if lower.startswith("/cron"):
            if len(parts) > 1 and parts[1] == "add":
                return False
            await self.show_cron_menu()
            return True

        return False

    async def show_cron_menu(self) -> None:
        """Cron jobs list with enable/disable/delete buttons."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from cli.shared.commands.cron_commands import format_jobs_message
        from core.cron.store import CronStore

        from integrations.telegram.keyboards import _cb

        host = self._host
        profile = host.profile
        store = CronStore(profile)
        jobs = store.list_jobs()

        text = format_jobs_message(profile, html=True)
        rows: list[list[InlineKeyboardButton]] = []

        for job in jobs[:8]:
            flag = "✓" if job.enabled else "○"
            short = (job.name or job.task[:20]).replace("\n", " ")
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{flag} {short[:18]}",
                        callback_data=_cb("cr", f"v:{job.id}"),
                    ),
                    InlineKeyboardButton(
                        text="Вкл" if not job.enabled else "Выкл",
                        callback_data=_cb("cr", f"{'e' if not job.enabled else 'd'}:{job.id}"),
                    ),
                    InlineKeyboardButton(
                        text="🗑",
                        callback_data=_cb("cr", f"x:{job.id}"),
                    ),
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(text="↻ Обновить", callback_data=_cb("cr", "list")),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Как добавить",
                    callback_data=_cb("cr", "help"),
                ),
            ]
        )

        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await host._send_html_with_keyboard(text, kb)

    async def _handle_cron_callback(self, value: str) -> None:
        from cli.shared.commands.cron_commands import resolve_job_id
        from core.cron.store import CronStore

        host = self._host
        store = CronStore(host.profile)

        if value in ("list", "refresh"):
            await self.show_cron_menu()
            return

        if value == "help":
            await host._send_html(
                "<b>Добавить cron</b>\n"
                "<code>/cron add every day at 9 :: текст задачи</code>\n"
                "<code>/cron add 0 9 * * * :: текст задачи</code>\n\n"
                "Планировщик работает в <code>holix gateway</code>."
            )
            return

        if ":" not in value:
            await self.show_cron_menu()
            return

        action, job_token = value.split(":", 1)
        try:
            job = resolve_job_id(store, job_token)
        except Exception as e:
            await host._send_html(f"Ошибка: <code>{escape_html(str(e))}</code>")
            return

        if action == "e":
            store.set_enabled(job.id, True)
            await host._send_html(f"Включено: <code>{escape_html(job.id)}</code>")
            await self.show_cron_menu()
            return
        if action == "d":
            store.set_enabled(job.id, False)
            await host._send_html(f"Выключено: <code>{escape_html(job.id)}</code>")
            await self.show_cron_menu()
            return
        if action == "x":
            store.remove(job.id)
            await host._send_html(f"Удалено: <code>{escape_html(job.id)}</code>")
            await self.show_cron_menu()
            return
        if action == "v":
            detail = (
                f"<b>{escape_html(job.name)}</b>\n"
                f"<code>{escape_html(job.cron_expression)}</code>\n"
                f"Задача: {escape_html(job.task[:400])}"
            )
            await host._send_html(detail)
            return

        await self.show_cron_menu()

    async def show_mcp_menu(self, command: str = "/mcp") -> None:
        """Show MCP management menu with inline keyboard."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from integrations.telegram.markdown import escape_html

        cmd = command.lower()
        parts = cmd.split()

        host = self._host
        profile = host.profile
        try:
            from cli.core import get_profile_manager

            manager = get_profile_manager()
            cfg = manager.load_profile(profile)
        except Exception:
            cfg = None

        servers = getattr(cfg, "mcp_servers", {}) if cfg else {}
        getattr(cfg, "mcp_assignments", {}) if cfg else {}

        text_lines = [f"<b>MCP Servers</b> · профиль <code>{escape_html(profile)}</code>"]

        if not servers:
            text_lines.append("\nНет настроенных MCP серверов.")
            text_lines.append("Используй /mcp install или holix mcp install в терминале.")
        else:
            for name, data in list(servers.items())[:8]:
                src = data.get("_source", "manual")
                trans = data.get("transport", "stdio")
                text_lines.append(f"• <code>{escape_html(name)}</code> ({trans}) [{src}]")

        from integrations.telegram.command_access import is_mcp_management_allowed

        can_manage_mcp = is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )
        kb_rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(text="📋 List", callback_data="mcp:list"),
                InlineKeyboardButton(text="🔧 Tools", callback_data="mcp:tools"),
            ],
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="mcp:refresh"),
            ],
        ]
        if can_manage_mcp:
            kb_rows = [
                [
                    InlineKeyboardButton(text="📋 List", callback_data="mcp:list"),
                    InlineKeyboardButton(
                        text="🛠 Install popular", callback_data="mcp:install-popular"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="➕ Install from git", callback_data="mcp:install-git"
                    ),
                    InlineKeyboardButton(text="🔗 Assign to agents", callback_data="mcp:assign"),
                ],
                [
                    InlineKeyboardButton(text="🧪 Test server", callback_data="mcp:test"),
                    InlineKeyboardButton(text="🗑 Remove server", callback_data="mcp:remove"),
                ],
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="mcp:refresh"),
                ],
            ]
        elif not servers:
            text_lines.append(
                f"\n<i>{escape_html(t('tg.mcp_read_only_empty', messenger_host_locale(host)))}</i>"
            )

        # If specific subcommand, handle simply
        if len(parts) > 1:
            sub = parts[1]
            if sub == "list":
                await host._mcp_list()
                return
            if sub == "tools":
                if hasattr(host, "_mcp_list_tools"):
                    await host._mcp_list_tools()
                else:
                    await host._mcp_list_tools()
                return
            if sub in ("install", "add", "assign", "remove", "rm", "delete", "test"):
                if not can_manage_mcp:
                    await self._host._send_html(
                        escape_html(t("tg.mcp_read_only", messenger_host_locale(host)))
                    )
                    return
            if sub in ("install", "add"):
                arg = " ".join(parts[2:]) if len(parts) > 2 else ""
                host.run_worker(host._mcp_install(arg))
                return
            if sub in ("remove", "rm", "delete"):
                name = parts[2] if len(parts) > 2 else ""
                host.run_worker(host._mcp_remove(name))
                return

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await host._send_html_with_keyboard("\n".join(text_lines), kb)

    async def apply_callback(self, action: str, value: str) -> str:
        """Apply UI callback; return short answer for query.answer()."""
        if action == "ps":
            from core.runtime.background_process import get_background_process_registry

            from integrations.telegram.approvals import _lookup_callback_token

            process_id = _lookup_callback_token(
                self._session.process_callback_tokens,
                value,
            )
            registry = get_background_process_registry()
            record = await registry.stop(process_id)
            if record is None:
                return "Процесс не найден"
            buf = self._session.live_buffer
            if buf is not None:
                buf.clear_background_process()
                buf.add_note(f"⏹ Process stopped: {record.label}")
                if self._session.live_message_id is not None:
                    from integrations.telegram.render import buffer_to_telegram_html

                    try:
                        await self._host._bot.edit_message_text(
                            buffer_to_telegram_html(buf),
                            chat_id=self._session.chat_id,
                            message_id=self._session.live_message_id,
                            parse_mode="HTML",
                            reply_markup=None,
                        )
                    except Exception:
                        pass
            # Update/unpin dedicated process notice (survives after agent run).
            from integrations.telegram.live_presenter import TelegramLivePresenter

            presenter = TelegramLivePresenter(self._host._bot, self._session)
            await presenter.unpin_background_process_notice(
                process_id,
                label=record.label or process_id,
                status="stopped",
            )
            if getattr(self._session, "process_log_watch_id", None) == process_id:
                await self._edit_process_log_watch_message()
            return f"Остановлен: {record.label}"

        if action == "m" and value in self._host._execution_modes:
            self._host._execution_mode_index = self._host._execution_modes.index(value)
            await self.show_mode_picker()
            lang = messenger_host_locale(self._host)
            return t("tg.mode", lang, mode=value)

        if action == "st":
            self._host.streaming_enabled = value == "1"
            await self.show_stream_picker()
            lang = messenger_host_locale(self._host)
            state = "on" if self._host.streaming_enabled else "off"
            return t("tg.streaming", lang, state=state)

        if action == "pl":
            from integrations.telegram.approvals import _lookup_callback_token

            process_id = _lookup_callback_token(
                self._session.process_callback_tokens,
                value,
            )
            return await self.start_process_log_watch(process_id)

        if action == "pe":
            await self.exit_process_log_watch()
            return t("tg.process.watch_closed", messenger_host_locale(self._host))

        if action == "sr":
            from integrations.messenger.subagent_reply import apply_reply_button
            from integrations.messenger.subagent_watch import resolve_job_token

            job_id = resolve_job_token(self._session.subagent_reply_tokens, value)
            routed = apply_reply_button(self._host.agent, self._session, job_id)
            return await self.present_subagent_reply_route(routed)

        if action == "sw":
            from integrations.messenger.subagent_watch import resolve_job_token

            job_id = resolve_job_token(self._session.subagent_callback_tokens, value)
            toast = await self.start_subagent_watch(job_id)
            return toast

        if action == "ss":
            return await self.stop_watched_subagent()

        if action == "se":
            await self.exit_subagent_watch()
            lang = messenger_host_locale(self._host)
            return t("tg.subagent_watch.closed", lang)

        if action == "sa":
            from integrations.messenger.subagents_settings import set_subagents_enabled_for_host

            lang = messenger_host_locale(self._host)
            try:
                enabled = set_subagents_enabled_for_host(self._host, value == "1")
            except Exception as exc:
                return f"{t('tg.error', lang)}: {exc}"
            await self.show_subagents_picker()
            state = "on" if enabled else "off"
            return t("tg.subagents", lang, state=state)

        if action == "rf":
            from integrations.messenger.reflexion_settings import set_reflexion_enabled_for_host

            lang = messenger_host_locale(self._host)
            try:
                enabled = set_reflexion_enabled_for_host(self._host, value == "1")
            except Exception as exc:
                return f"{t('tg.error', lang)}: {exc}"
            await self.show_reflexion_picker()
            state = "on" if enabled else "off"
            return t("tg.reflexion", lang, state=state)

        if action == "pl":
            from integrations.messenger.pipeline_settings import set_pipeline_for_host

            lang = messenger_host_locale(self._host)
            try:
                mode = set_pipeline_for_host(self._host, value)
            except Exception as exc:
                return f"{t('tg.error', lang)}: {exc}"
            await self.show_pipeline_picker()
            return t("tg.pipeline", lang, mode=mode)

        if action == "pi":
            lang = messenger_host_locale(self._host)
            profiles = self._session.ui_profiles
            idx = int(value)
            if 0 <= idx < len(profiles):
                name = profiles[idx]
                if name != self._host.profile:
                    from integrations.telegram.plugin_api import (
                        resolve_plugin_visible_profiles,
                    )
                    from integrations.telegram.profile_visibility import is_profile_list_hidden

                    plugin = resolve_plugin_visible_profiles(
                        user_id=self._session.user_id,
                        current=self._host.profile,
                        bot_profile=self._session.bot_profile,
                    )
                    if (
                        is_profile_list_hidden(
                            self._session.bot_profile,
                            self._session.user_id,
                        )
                        and plugin is None
                    ):
                        return t("tg.profile_switch_by_key", lang)
                    await self._host._switch_profile(name)
                    return t("tg.profile", lang, name=name)
                return t("tg.profile_same", lang, name=name)
            return t("tg.profile_invalid", lang)

        if action == "s":
            sessions = self._session.ui_sessions
            idx = int(value)
            if 0 <= idx < len(sessions):
                cid = sessions[idx].get("conversation_id", "")
                self._host._session.conversation_id = cid
                from core.session_models import restore_session_model

                restored = restore_session_model(self._host)
                title = sessions[idx].get("title") or cid
                lang = messenger_host_locale(self._host)
                model_line = (
                    f"\n{escape_html(t('tg.model', lang, label=restored))}" if restored else ""
                )
                await self._host._send_html(
                    f"{escape_html(t('tg.session', lang, title='', model=''))}"
                    f"<code>{escape_html(title)}</code>{model_line}"
                )
                return t("tg.session_switched", lang)
            return t("tg.session_invalid", messenger_host_locale(self._host))

        if action == "sp":
            await self.show_sessions_picker(page=int(value))
            return ""

        if action == "sn":
            await self._host._create_new_session()
            await self.show_sessions_picker()
            return t("tg.new_session", messenger_host_locale(self._host))

        if action == "t":
            self._host._show_full_tool_result(int(value))
            return t("tg.tool_result", messenger_host_locale(self._host))

        if action == "sk":
            names = self._session.ui_skills
            idx = int(value)
            if 0 <= idx < len(names):
                from cli.shared.commands.skills_commands import _load_skills

                mgr, slot, _ = _load_skills(self._host)
                name = names[idx]
                skill = mgr.all_skills.get(name, {})
                desc = escape_html((skill.get("description") or "—")[:500])
                src = skill.get("_source", "")
                body = (skill.get("content") or skill.get("body") or "").strip()
                text = f"<b>{escape_html(name)}</b>"
                if src:
                    text += f" · <i>{escape_html(src)}</i>"
                text += f"\n<i>agent: {escape_html(slot)}</i>\n\n{desc}"
                if body:
                    preview = escape_html(body[:900])
                    if len(body) > 900:
                        preview += "…"
                    text += f"\n\n<code>{preview}</code>"
                await self._host._send_html(text)
                return name[:40]
            return "invalid skill"

        if action == "skp":
            await self.show_skills_picker(page=int(value))
            return ""

        if action == "mp":
            label = await apply_preset_index(self._host, int(value))
            idx = self._session.ui_models_provider_idx
            if idx is not None:
                await self.show_provider_models(idx, page=self._session.ui_models_page)
            else:
                await self.show_models(page=self._session.ui_providers_page)
            return t("tg.model", messenger_host_locale(self._host), label=label)

        if action == "mg":
            await self.show_provider_models(int(value), page=0)
            return ""

        if action == "mgp":
            await self.show_models(provider_page=int(value))
            return ""

        if action == "mv":
            parts = value.split(":", 1)
            if len(parts) == 2:
                await self.show_provider_models(int(parts[0]), page=int(parts[1]))
            return ""

        if action == "mm":
            parts = value.split(":", 1)
            if len(parts) != 2:
                return t("tg.error", messenger_host_locale(self._host))
            pi, mi = int(parts[0]), int(parts[1])
            label = await apply_provider_model_index(self._host, pi, mi)
            await self.show_provider_models(pi, page=self._session.ui_models_page)
            return t("tg.model", messenger_host_locale(self._host), label=label)

        if action == "mb":
            await self.show_models()
            return ""

        if action == "r":
            await self._refresh(value)
            return ""

        if action == "mcp":
            await self._handle_mcp_callback(value)
            return ""

        if action == "cr":
            await self._handle_cron_callback(value)
            return ""

        return t("tg.unknown_action", messenger_host_locale(self._host))

    async def _refresh(self, kind: str) -> None:
        from integrations.telegram.command_access import is_menu_action_allowed

        if not is_menu_action_allowed(
            kind,
            self._session.bot_profile,
            self._session.user_id,
        ):
            lang = messenger_host_locale(self._host)
            await self._host._send_html(escape_html(t("tg.menu_unavailable", lang)))
            return

        if kind == "compress":
            from cli.shared.commands.context_compress import run_context_compress

            await run_context_compress(self._host)
            return

        dispatch = {
            "mode": self.show_mode_picker,
            "profile": self.show_profile_picker,
            "sessions": self.show_sessions_picker,
            "stream": self.show_stream_picker,
            "subagents": self.show_subagents_picker,
            "reflexion": self.show_reflexion_picker,
            "pipeline": self.show_pipeline_picker,
            "models": self.show_models,
            "tools": self.show_tools_picker,
            "skills": self.show_skills_picker,
            "status": self.show_status,
            "mcp": self.show_mcp_menu,
            "cron": self.show_cron_menu,
        }
        fn = dispatch.get(kind)
        if fn:
            await fn()

    async def show_mode_picker(self) -> None:
        current = self._session.execution_mode
        await self._host._send_html_with_keyboard(
            mode_picker_html(current),
            mode_picker_keyboard(self._host._execution_modes, current),
        )

    async def show_stream_picker(self) -> None:
        on = self._host.streaming_enabled
        text = (
            "<b>Стриминг ответа</b>\n"
            f"Сейчас: <code>{'on' if on else 'off'}</code>\n\n"
            "<i>При включении ответ обновляется в одном сообщении по мере генерации.</i>"
        )
        await self._host._send_html_with_keyboard(text, stream_picker_keyboard(on))

    def _cancel_subagent_watch_task(self) -> None:
        from integrations.messenger.subagent_watch import cancel_session_watch

        cancel_session_watch(self._session)

    async def present_subagent_reply_route(self, routed: Any) -> str:
        lang = messenger_host_locale(self._host)
        kind = getattr(routed, "kind", "")
        name = getattr(routed, "job_id", "") or "sub-agent"
        if kind == "delivered":
            msg = t("tg.subagent_q.sent", lang, name=name)
            await self._host._send_plain(msg)
            return msg
        if kind == "gone":
            msg = t("tg.subagent_q.gone", lang)
            await self._host._send_plain(msg)
            return msg
        if kind == "awaiting":
            msg = t("tg.subagent_q.awaiting", lang, name=name)
            await self._host._send_plain(msg)
            return msg
        if kind == "need_target":
            await self.show_subagent_reply_picker(with_text=True)
            return t("tg.subagent_q.pick_with_text", lang)
        feedback = str(getattr(routed, "feedback", "") or "").strip()
        if feedback:
            await self._host._send_plain(feedback)
        return feedback or "OK"

    async def show_subagent_reply_picker(self, *, with_text: bool = False) -> None:
        from integrations.messenger.subagent_reply import pending_job_ids, tokens_for_jobs
        from integrations.telegram.keyboards import subagent_reply_keyboard

        lang = messenger_host_locale(self._host)
        jobs = pending_job_ids(self._host.agent)
        if not jobs:
            await self._host._send_plain(t("tg.subagent_q.gone", lang))
            return
        tokens = tokens_for_jobs(self._session.subagent_reply_tokens, jobs)
        key = "tg.subagent_q.pick_with_text" if with_text else "tg.subagent_q.pick"
        html = escape_html(t(key, lang))
        kb = subagent_reply_keyboard(tokens, lang)
        if kb is None:
            await self._host._send_html(html)
            return
        await self._host._send_html_with_keyboard(html, kb)

    async def show_subagent_live_list(self) -> None:
        from integrations.messenger.subagent_watch import (
            format_list_text,
            list_watchable_jobs,
            map_job_tokens,
        )
        from integrations.telegram.keyboards import subagent_list_keyboard

        lang = messenger_host_locale(self._host)
        jobs = list_watchable_jobs(self._session.profile, self._host.agent)
        html = format_list_text(jobs, html=True, locale=lang)
        tokens: dict[str, str] = {}
        labels: dict[str, str] = {}
        ids: list[str] = []
        for job in jobs:
            jid = str(job.get("id") or job.get("name") or "")
            if not jid:
                continue
            ids.append(jid)
            status = str(job.get("status") or "")
            name = str(job.get("name") or jid)
            labels[jid] = f"{name} · {status}"[:40]
        if ids:
            tokens = map_job_tokens(self._session.subagent_callback_tokens, ids)
        kb = subagent_list_keyboard(tokens, labels) if tokens else None
        if kb is None:
            await self._host._send_html(html)
            return
        await self._host._send_html_with_keyboard(html, kb)

    async def start_subagent_watch(self, job_id: str) -> str:
        import asyncio

        from integrations.messenger.subagent_watch import format_watch_text, load_watch_job
        from integrations.telegram.keyboards import subagent_watch_keyboard

        lang = messenger_host_locale(self._host)
        jid = (job_id or "").strip()
        job = load_watch_job(self._session.profile, jid, self._host.agent)
        if not job:
            return t("tg.subagent_watch.gone", lang)

        switched = bool(
            self._session.subagent_watch_job_id and self._session.subagent_watch_job_id != jid
        )
        if self._session.subagent_watch_job_id:
            await self.exit_subagent_watch(silent=True)

        running = bool(job.get("running"))
        html = format_watch_text(job, html=True, locale=lang)
        kb = subagent_watch_keyboard(running=running, locale=lang)
        msg = await self._host._bot.send_message(
            self._session.chat_id,
            html,
            parse_mode="HTML",
            reply_markup=kb,
        )
        mid = int(getattr(msg, "message_id", 0) or 0)
        self._session.subagent_watch_job_id = jid
        self._session.subagent_watch_message_id = mid or None
        if running and mid:
            self._session.subagent_watch_task = asyncio.create_task(
                self._subagent_watch_loop(),
                name=f"tg-sa-watch-{jid[:24]}",
            )
        if switched:
            return t("tg.subagent_watch.busy", lang)
        return str(job.get("name") or jid)

    async def _subagent_watch_loop(self) -> None:
        import asyncio

        from integrations.messenger.subagent_watch import WATCH_INTERVAL_S

        try:
            while True:
                await asyncio.sleep(WATCH_INTERVAL_S)
                if not self._session.subagent_watch_job_id:
                    return
                still = await self._edit_subagent_watch_message()
                if not still:
                    return
        except asyncio.CancelledError:
            return

    async def _edit_subagent_watch_message(self) -> bool:
        from integrations.messenger.subagent_watch import format_watch_text, load_watch_job
        from integrations.telegram.keyboards import subagent_watch_keyboard
        from integrations.telegram.live_presenter import _is_not_modified

        lang = messenger_host_locale(self._host)
        jid = self._session.subagent_watch_job_id
        mid = self._session.subagent_watch_message_id
        if not jid or not mid:
            return False
        job = load_watch_job(self._session.profile, jid, self._host.agent)
        html = format_watch_text(job, html=True, locale=lang)
        running = bool(job and job.get("running"))
        kb = subagent_watch_keyboard(running=running, locale=lang)
        try:
            await self._host._bot.edit_message_text(
                html,
                chat_id=self._session.chat_id,
                message_id=mid,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as exc:
            if not _is_not_modified(exc):
                return False
        return running

    async def stop_watched_subagent(self) -> str:
        from integrations.messenger.subagent_watch import terminate_watch_job

        lang = messenger_host_locale(self._host)
        jid = self._session.subagent_watch_job_id
        if not jid:
            return t("tg.subagent_watch.gone", lang)
        await terminate_watch_job(self._host.agent, jid, profile=self._session.profile)
        await self._edit_subagent_watch_message()
        return t("tg.subagent_watch.stopped", lang)

    async def exit_subagent_watch(self, *, silent: bool = False) -> None:
        from integrations.messenger.subagent_watch import format_watch_text, load_watch_job
        from integrations.telegram.live_presenter import _is_not_modified

        lang = messenger_host_locale(self._host)
        jid = self._session.subagent_watch_job_id
        mid = self._session.subagent_watch_message_id
        self._cancel_subagent_watch_task()
        self._session.subagent_watch_job_id = None
        self._session.subagent_watch_message_id = None
        if silent or not mid:
            return
        job = load_watch_job(self._session.profile, jid or "", self._host.agent) if jid else None
        closed = t("tg.subagent_watch.closed", lang)
        if job:
            html = (
                format_watch_text(job, html=True, locale=lang) + f"\n\n<i>{escape_html(closed)}</i>"
            )
        else:
            html = f"<i>{escape_html(closed)}</i>"
        try:
            await self._host._bot.edit_message_text(
                html,
                chat_id=self._session.chat_id,
                message_id=mid,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as exc:
            if not _is_not_modified(exc):
                pass

    def _cancel_process_log_watch_task(self) -> None:
        from integrations.messenger.process_log_watch import cancel_process_log_watch

        cancel_process_log_watch(self._session)

    def _process_watch_token(self, process_id: str) -> str:
        from integrations.telegram.approvals import _register_callback_token

        mapping = self._session.process_callback_tokens
        for token, stored in mapping.items():
            if stored == process_id:
                return token
        return _register_callback_token(mapping, process_id)

    async def start_process_log_watch(self, process_id: str) -> str:
        import asyncio

        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )
        from integrations.telegram.keyboards import process_log_watch_keyboard

        lang = messenger_host_locale(self._host)
        pid = (process_id or "").strip()
        rec = load_process_record(pid)
        if rec is None:
            return t("tg.process.watch_gone", lang)

        switched = bool(
            self._session.process_log_watch_id and self._session.process_log_watch_id != pid
        )
        if self._session.process_log_watch_id:
            await self.exit_process_log_watch(silent=True)

        token = self._process_watch_token(pid)
        running = rec.is_running()
        html = format_process_log_watch(rec, html=True, locale=lang)
        kb = process_log_watch_keyboard(token, running=running, locale=lang)
        msg = await self._host._bot.send_message(
            self._session.chat_id,
            html,
            parse_mode="HTML",
            reply_markup=kb,
        )
        mid = int(getattr(msg, "message_id", 0) or 0)
        self._session.process_log_watch_id = pid
        self._session.process_log_watch_message_id = mid or None
        if running and mid:
            self._session.process_log_watch_task = asyncio.create_task(
                self._process_log_watch_loop(),
                name=f"tg-proc-log-{pid[:24]}",
            )
        if switched:
            return t("tg.process.watch_busy", lang)
        return rec.label or pid

    async def _process_log_watch_loop(self) -> None:
        import asyncio

        from integrations.messenger.process_log_watch import WATCH_INTERVAL_S

        try:
            while True:
                await asyncio.sleep(WATCH_INTERVAL_S)
                if not self._session.process_log_watch_id:
                    return
                still = await self._edit_process_log_watch_message()
                if not still:
                    return
        except asyncio.CancelledError:
            return

    async def _edit_process_log_watch_message(self) -> bool:
        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )
        from integrations.telegram.keyboards import process_log_watch_keyboard
        from integrations.telegram.live_presenter import _is_not_modified

        lang = messenger_host_locale(self._host)
        pid = self._session.process_log_watch_id
        mid = self._session.process_log_watch_message_id
        if not pid or not mid:
            return False
        rec = load_process_record(pid)
        html = format_process_log_watch(rec, html=True, locale=lang)
        running = bool(rec and rec.is_running())
        kb = process_log_watch_keyboard(
            self._process_watch_token(pid),
            running=running,
            locale=lang,
        )
        try:
            await self._host._bot.edit_message_text(
                html,
                chat_id=self._session.chat_id,
                message_id=mid,
                parse_mode="HTML",
                reply_markup=kb if rec is not None else None,
            )
        except Exception as exc:
            if not _is_not_modified(exc):
                return False
        return running

    async def exit_process_log_watch(self, *, silent: bool = False) -> None:
        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )
        from integrations.telegram.live_presenter import _is_not_modified

        lang = messenger_host_locale(self._host)
        pid = self._session.process_log_watch_id
        mid = self._session.process_log_watch_message_id
        self._cancel_process_log_watch_task()
        if silent or not mid:
            return
        rec = load_process_record(pid or "") if pid else None
        closed = t("tg.process.watch_closed", lang)
        if rec:
            html = (
                format_process_log_watch(rec, html=True, locale=lang)
                + f"\n\n<i>{escape_html(closed)}</i>"
            )
        else:
            html = f"<i>{escape_html(closed)}</i>"
        try:
            await self._host._bot.edit_message_text(
                html,
                chat_id=self._session.chat_id,
                message_id=mid,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as exc:
            if not _is_not_modified(exc):
                pass

    async def show_subagents_picker(self) -> None:
        from integrations.messenger.subagents_settings import is_subagents_enabled_for_host

        lang = messenger_host_locale(self._host)
        on = is_subagents_enabled_for_host(self._host)
        state = "on" if on else "off"
        text = (
            f"<b>{escape_html(t('tg.subagents_picker_title', lang))}</b>\n"
            f"{escape_html(t('tg.subagents', lang, state=state))}\n\n"
            f"<i>{escape_html(t('tg.subagents_picker_body', lang))}</i>"
        )
        await self._host._send_html_with_keyboard(
            text,
            subagents_picker_keyboard(on, lang),
        )

    async def show_reflexion_picker(self) -> None:
        from integrations.messenger.reflexion_settings import is_reflexion_enabled_for_host

        lang = messenger_host_locale(self._host)
        on = is_reflexion_enabled_for_host(self._host)
        state = "on" if on else "off"
        text = (
            f"<b>{escape_html(t('tg.reflexion_picker_title', lang))}</b>\n"
            f"{escape_html(t('tg.reflexion', lang, state=state))}\n\n"
            f"<i>{escape_html(t('tg.reflexion_picker_body', lang))}</i>"
        )
        await self._host._send_html_with_keyboard(
            text,
            reflexion_picker_keyboard(on, lang),
        )

    async def show_pipeline_picker(self) -> None:
        from integrations.messenger.pipeline_settings import is_pipeline_for_host

        lang = messenger_host_locale(self._host)
        mode = is_pipeline_for_host(self._host)
        text = (
            f"<b>{escape_html(t('tg.pipeline_picker_title', lang))}</b>\n"
            f"{escape_html(t('tg.pipeline', lang, mode=mode))}\n\n"
            f"<i>{escape_html(t('tg.pipeline_picker_body', lang))}</i>"
        )
        await self._host._send_html_with_keyboard(
            text,
            pipeline_picker_keyboard(mode, lang),
        )

    async def show_profile_picker(self) -> None:
        from integrations.telegram.plugin_api import resolve_plugin_visible_profiles
        from integrations.telegram.profile_visibility import is_profile_list_hidden

        profiles = self._host._get_available_profiles()
        self._session.ui_profiles = profiles
        lang = messenger_host_locale(self._host)
        current = self._host.profile
        plugin = resolve_plugin_visible_profiles(
            user_id=self._session.user_id,
            current=current,
            bot_profile=self._session.bot_profile,
        )

        if (
            is_profile_list_hidden(self._session.bot_profile, self._session.user_id)
            and plugin is None
        ):
            await self._host._send_html(
                f"<b>{escape_html(t('profiles_title', lang))}</b>\n"
                f"{escape_html(t('tg.profile_current', lang, name=current))}\n\n"
                f"<i>{escape_html(t('tg.profile_switch_by_key', lang))}</i>"
            )
            return

        lines = [
            f"<b>{escape_html(t('profiles_title', lang))}</b>",
            escape_html(t("tg.profile_current", lang, name=current)),
            "",
        ]
        for name in profiles[:12]:
            mark = " ✓" if name == current else ""
            lines.append(f"• <code>{escape_html(name)}</code>{mark}")
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            profile_picker_keyboard(profiles, current),
        )

    async def _deny_mcp_management(self) -> None:
        lang = messenger_host_locale(self._host)
        await self._host._send_html(escape_html(t("tg.mcp_read_only", lang)))

    async def _handle_mcp_callback(self, value: str) -> None:
        """Handle mcp:* callbacks from the MCP menu."""
        from integrations.telegram.command_access import is_mcp_management_allowed

        host = self._host
        can_manage = is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )
        if value == "list" or value == "refresh":
            await host._mcp_list()
            return
        if value == "tools":
            await host._mcp_list_tools()
            return
        if not can_manage:
            await self._deny_mcp_management()
            return
        if value == "install-popular":
            await self._show_mcp_popular_picker()
            return
        if value == "install-git":
            await host._send_html(
                "Чтобы установить из git, напиши:\n"
                "<code>/mcp install https://github.com/owner/repo</code>\n\n"
                "Или используй в терминале: <code>holix mcp install &lt;url&gt;</code>"
            )
            return
        if value == "assign":
            await self._show_mcp_assign_picker()
            return
        if value == "test":
            await host._send_html(
                "Тест сервера: <code>/mcp test &lt;name&gt;</code>\n"
                "Например: <code>/mcp test context7</code>"
            )
            return
        if value == "remove":
            await self._show_mcp_remove_picker()
            return
        if value.startswith("remove-confirm:"):
            name = value.split(":", 1)[1]
            await host._mcp_remove(name)
            await self._show_mcp_remove_picker()
            return
        if value.startswith("install:"):
            key = value.split(":", 1)[1]
            await host._mcp_install(key)
            return
        if value.startswith("assign:"):
            # value = "assign:server:role1,role2" or just start picker
            await self._show_mcp_assign_picker()
            return

    async def _show_mcp_popular_picker(self) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from core.mcp.popular import get_popular_list

        popular = get_popular_list()
        rows = []
        for p in popular[:6]:  # limit buttons
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{p.display_name} ({p.category})",
                        callback_data=f"mcp:install:{p.key}",
                    )
                ]
            )
        rows.append([InlineKeyboardButton(text="« Назад", callback_data="mcp:refresh")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await self._host._send_html_with_keyboard(
            "<b>Популярные MCP серверы</b>\nВыбери для установки (defaults):", kb
        )

    async def _show_mcp_assign_picker(self) -> None:
        from cli.core import get_profile_manager

        try:
            manager = get_profile_manager()
            cfg = manager.load_profile(self._host.profile)
            servers = list((getattr(cfg, "mcp_servers", {}) or {}).keys())
        except Exception:
            servers = []

        if not servers:
            await self._host._send_html("Нет MCP серверов. Сначала установи через /mcp install.")
            return

        # Simple: send list and instruct to use /mcp assign or CLI
        text = "MCP серверы для назначения:\n" + "\n".join(f"• {s}" for s in servers)
        text += "\n\nИспользуй: <code>/mcp assign &lt;server&gt; main,researcher</code> или holix mcp assign в терминале."
        await self._host._send_html(text)

    async def _show_mcp_remove_picker(self) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from cli.core import get_profile_manager

        from integrations.telegram.markdown import escape_html

        try:
            manager = get_profile_manager()
            cfg = manager.load_profile(self._host.profile)
            servers = list((getattr(cfg, "mcp_servers", {}) or {}).keys())
        except Exception:
            servers = []

        if not servers:
            await self._host._send_html("Нет MCP серверов для удаления.")
            return

        rows = []
        for s in servers[:6]:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑 {escape_html(s)}", callback_data=f"mcp:remove-confirm:{s}"
                    )
                ]
            )
        rows.append([InlineKeyboardButton(text="« Назад", callback_data="mcp:refresh")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await self._host._send_html_with_keyboard("<b>Выберите MCP сервер для удаления:</b>", kb)

    async def show_sessions_picker(self, *, page: int = 0) -> None:
        if self._host.agent:
            try:
                from core.cron.delivery import without_internal_cron_sessions

                self._session.ui_sessions = without_internal_cron_sessions(
                    await self._host.agent.list_conversations(limit=24)
                )
            except Exception:
                self._session.ui_sessions = []
        sessions = self._session.ui_sessions
        if not sessions:
            await self._host._send_html_with_keyboard(
                "<b>Сессии</b>\nНет сохранённых сессий.\n\n"
                "<i>Отправьте сообщение или создайте новую</i>",
                sessions_picker_keyboard([], self._host.conversation_id),
            )
            return

        self._session.ui_sessions_page = page
        lines = [
            "<b>Сессии</b>",
            f"Текущая: <code>{escape_html(self._host.conversation_id)}</code>",
            "",
            "<i>Выберите сессию или создайте новую</i>",
        ]
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            sessions_picker_keyboard(
                sessions,
                self._host.conversation_id,
                page=page,
            ),
        )

    async def show_tools_picker(self) -> None:
        tools = self._host._recent_tool_results
        if not tools:
            await self._host._send_plain(t("tg.no_tools", messenger_host_locale(self._host)))
            return
        lines = ["<b>Последние tools</b>", "<i>Нажмите, чтобы получить полный вывод</i>"]
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            tools_picker_keyboard(tools),
        )

    async def show_skills_picker(self, *, page: int = 0) -> None:
        from cli.shared.commands.skills_commands import _load_skills

        mgr, slot, config = _load_skills(self._host)
        names = mgr.list_skill_names_for_agent(slot)
        self._session.ui_skills = names
        self._session.ui_skills_page = page

        skills_dir = getattr(config, "skills_dir", "") or mgr.skills_dir
        if not names:
            await self._host._send_html(
                "<b>Skills</b>\n\n"
                "<i>Нет skills в профиле. Установите через "
                "<code>/hub</code> или <code>holix hub install</code>.</i>"
            )
            return

        start = page * SKILLS_PAGE_SIZE
        chunk = names[start : start + SKILLS_PAGE_SIZE]
        total_pages = max(1, (len(names) + SKILLS_PAGE_SIZE - 1) // SKILLS_PAGE_SIZE)

        lines = [
            "<b>Skills</b>",
            f"Профиль: <code>{escape_html(self._host.profile)}</code>",
            f"Агент: <code>{escape_html(slot)}</code> · всего {len(names)}",
            f"dir: <code>{escape_html(str(skills_dir))}</code>",
            "",
            f"<i>Стр. {page + 1}/{total_pages} — нажмите skill для описания</i>",
            "",
        ]
        for name in chunk:
            skill = mgr.all_skills.get(name, {})
            desc = escape_html((skill.get("description") or "")[:56])
            src = skill.get("_source", "")
            tag = f" <i>[{escape_html(src)}]</i>" if src else ""
            lines.append(f"• <code>{escape_html(name)}</code>{tag}")
            if desc:
                lines.append(f"  {desc}")

        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            skills_picker_keyboard(names, page=page),
        )

    def _load_models_menu(self) -> None:
        state = build_models_menu(self._host.profile)
        self._session.ui_model_presets = list(state.presets)
        self._session.ui_providers = list(state.providers)

    async def show_models(self, *, provider_page: int = 0) -> None:
        self._load_models_menu()
        self._session.ui_models_provider_idx = None
        self._session.ui_providers_page = provider_page

        presets = self._session.ui_model_presets
        providers = self._session.ui_providers
        active = self._host.agent.model if self._host.agent else current_model_label(self._session)

        lines = [
            "<b>Модель для чата</b>",
            f"Профиль: <code>{escape_html(self._host.profile)}</code>",
            f"Сейчас: <code>{escape_html(active)}</code>",
            "",
            "<b>Пресеты</b> — main, agent_models",
            "<b>Провайдеры</b> — список моделей без префикса",
        ]
        if not presets and not providers:
            lines.append("\n<b>Нет моделей</b> — <code>holix models setup</code>")
            await self._host._send_html("\n".join(lines))
            return

        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            models_root_keyboard(
                presets,
                providers,
                self._session.active_model_slot,
                provider_page=provider_page,
                page_size=PROVIDERS_PAGE_SIZE,
            ),
        )

    async def show_provider_models(self, provider_idx: int, *, page: int = 0) -> None:
        if not self._session.ui_providers:
            self._load_models_menu()
        providers = self._session.ui_providers
        if provider_idx < 0 or provider_idx >= len(providers):
            await self.show_models()
            return

        prov = providers[provider_idx]
        self._session.ui_models_provider_idx = provider_idx
        self._session.ui_models_page = page

        active = self._host.agent.model if self._host.agent else "—"
        total = len(prov.models)
        pages = max(1, (total + MODELS_PAGE_SIZE - 1) // MODELS_PAGE_SIZE)

        lines = [
            f"<b>Провайдер</b> <code>{escape_html(prov.name)}</code>",
            f"Сейчас в чате: <code>{escape_html(active)}</code>",
            f"Моделей: {total}",
        ]
        if pages > 1:
            lines.append(f"Страница {page + 1} / {pages}")
        lines.append("")
        lines.append("<i>Выберите модель (имя без префикса провайдера)</i>")

        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            models_provider_keyboard(
                prov.name,
                list(prov.models),
                self._session.active_model_slot,
                provider_idx,
                page=page,
                page_size=MODELS_PAGE_SIZE,
            ),
        )

    async def show_status(self) -> None:
        from integrations.messenger.pipeline_settings import is_pipeline_for_host
        from integrations.messenger.reflexion_settings import is_reflexion_enabled_for_host
        from integrations.messenger.subagents_settings import is_subagents_enabled_for_host

        mode = self._session.execution_mode
        stream = "on" if self._host.streaming_enabled else "off"
        mode_title = MODE_LABELS.get(mode, (mode, ""))[0]
        model_line = current_model_label(self._session)
        if self._host.agent:
            model_line = self._host.agent.model
        subagents = "on" if is_subagents_enabled_for_host(self._host) else "off"
        reflexion = "on" if is_reflexion_enabled_for_host(self._host) else "off"
        pipeline = is_pipeline_for_host(self._host)

        lines = [
            "<b>Holix — статус</b>",
            f"Профиль: <code>{escape_html(self._host.profile)}</code>",
            f"Модель: <code>{escape_html(model_line)}</code>",
            f"Режим: <code>{escape_html(mode)}</code> ({escape_html(mode_title)})",
            f"Pipeline: <code>{escape_html(pipeline)}</code>",
            f"Стриминг: <code>{stream}</code>",
            f"Субагенты: <code>{subagents}</code>",
            f"Reflexion: <code>{reflexion}</code>",
            f"Сессия: <code>{escape_html(self._host.conversation_id)}</code>",
        ]
        from integrations.telegram.access_approval import is_telegram_admin

        is_admin = is_telegram_admin(self._session.bot_profile, self._session.user_id)
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            status_menu_keyboard(messenger_host_locale(self._host), is_admin=is_admin),
        )


async def dispatch_callback(
    host: TelegramHost,
    data: str,
) -> str:
    parsed = parse_callback(data)
    if not parsed:
        return "Invalid"
    action, value = parsed
    return await TelegramInteractive(host).apply_callback(action, value)
