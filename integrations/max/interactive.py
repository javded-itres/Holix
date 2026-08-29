"""Interactive pickers and callback handling for MAX."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cli.shared.slash_input import (
    is_mode_slash,
    is_models_slash,
    normalize_slash_input,
    slash_command_token,
)
from core.i18n import t

from integrations.max.keyboards import (
    MODE_LABELS,
    _callback_btn,
    _cb,
    callback_rows_keyboard,
    help_guide_keyboard,
    inline_keyboard,
    mode_picker_keyboard,
    mode_picker_text,
    models_provider_keyboard,
    models_root_keyboard,
    parse_callback,
    pipeline_picker_keyboard,
    profile_picker_keyboard,
    reflexion_picker_keyboard,
    sessions_picker_keyboard,
    status_menu_keyboard,
    stream_picker_keyboard,
    tools_picker_keyboard,
)
from integrations.messenger.locale import messenger_host_locale
from integrations.telegram.interactive import profile_model_summary
from integrations.telegram.model_switch import (
    MODELS_PAGE_SIZE,
    PROVIDERS_PAGE_SIZE,
    apply_preset_index,
    apply_provider_model_index,
    build_models_menu,
    current_model_label,
)


def _html_to_md(html: str) -> str:
    import re
    from html import unescape

    text = html.replace("<b>", "**").replace("</b>", "**")
    text = text.replace("<i>", "_").replace("</i>", "_")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = text.replace("<pre>", "```\n").replace("</pre>", "\n```")
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text)


if TYPE_CHECKING:
    from integrations.max.host import MaxHost


class MaxInteractive:
    def __init__(self, host: MaxHost) -> None:
        self._host = host

    @property
    def _session(self) -> Any:
        return self._host._session

    async def _deny_menu_command(self, command_token: str) -> bool:
        from integrations.max.command_access import is_command_allowed

        if is_command_allowed(
            command_token,
            self._session.bot_profile,
            self._session.user_id,
        ):
            return False
        await self._host._send_text(t("tg.menu_unavailable", messenger_host_locale(self._host)))
        return True

    async def handle_slash(self, command: str) -> bool:
        cmd = normalize_slash_input(command.strip())
        lower = cmd.lower()
        parts = lower.split()
        cmd_token = slash_command_token(cmd)

        if await self._deny_menu_command(cmd_token.lstrip("/").split()[0]):
            return True

        if cmd_token in ("/help", "/h", "/?") or lower.startswith("/help "):
            from core.host.help_guide import resolve_help_topic

            arg = " ".join(parts[1:]) if len(parts) > 1 else ""
            await self.show_help_guide(resolve_help_topic(arg))
            return True

        if is_models_slash(cmd):
            await self.show_models()
            return True

        if is_mode_slash(cmd):
            if len(parts) > 1 and parts[1] in self._host._execution_modes:
                self._host._execution_mode_index = self._host._execution_modes.index(parts[1])
                await self._host._send_text(
                    t("mode_set", messenger_host_locale(self._host), mode=parts[1])
                )
            else:
                await self.show_mode_picker()
            return True

        if lower.startswith("/stream"):
            if len(parts) > 1:
                self._host.streaming_enabled = parts[1] in ("on", "true", "1")
                state = "on" if self._host.streaming_enabled else "off"
                await self._host._send_text(
                    t("streaming", messenger_host_locale(self._host), state=state)
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
            from integrations.max.admin_broadcast import handle_admin_message_command

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

        if lower == "/skills" or lower.startswith("/skills "):
            from cli.shared.commands.skills_commands import run_skills_command

            await run_skills_command(self._host, cmd)
            return True

        if lower in ("/subagent-types", "/subagent types", "/code-mode"):
            await self.show_subagents_picker()
            return True
        if lower in ("/subagents", "/subagent-list") or lower == "/subagent list":
            await self.show_subagent_live_list()
            return True
        if lower.startswith("/subagent"):
            from cli.shared.commands.subagent_commands import run_subagents_command

            await run_subagents_command(self._host, cmd)
            return True

        if lower in ("/status", "/menu"):
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

    async def apply_callback(self, action: str, value: str) -> str:
        if action == "ps":
            from core.runtime.background_process import get_background_process_registry

            from integrations.max.approvals import _lookup_callback_token

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
                message_id = self._session.live_message_id
                if message_id:
                    from integrations.max.render import buffer_to_max_html

                    try:
                        await self._host._client.edit_message(
                            message_id,
                            buffer_to_max_html(buf),
                            fmt="html",
                            attachments=None,
                        )
                    except Exception:
                        pass
            from integrations.max.live_presenter import MaxLivePresenter

            presenter = MaxLivePresenter(self._host._client, self._session)
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
            return t("tg.mode", messenger_host_locale(self._host), mode=value)

        if action == "st":
            self._host.streaming_enabled = value == "1"
            await self.show_stream_picker()
            state = "on" if self._host.streaming_enabled else "off"
            return t("tg.streaming", messenger_host_locale(self._host), state=state)

        if action == "pl":
            from integrations.max.approvals import _lookup_callback_token

            process_id = _lookup_callback_token(
                self._session.process_callback_tokens,
                value,
            )
            return await self.start_process_log_watch(process_id)

        if action == "pe":
            await self.exit_process_log_watch()
            return t("tg.process.watch_closed", messenger_host_locale(self._host))

        if action == "qo":
            from integrations.messenger.subagent_reply import apply_ask_option

            ok = apply_ask_option(self._host.agent, self._session, value)
            lang = messenger_host_locale(self._host)
            return "OK" if ok else t("tg.error", lang)

        if action == "sr":
            from integrations.messenger.subagent_reply import apply_reply_button
            from integrations.messenger.subagent_watch import resolve_job_token

            job_id = resolve_job_token(self._session.subagent_reply_tokens, value)
            routed = apply_reply_button(self._host.agent, self._session, job_id)
            return await self.present_subagent_reply_route(routed)

        if action == "sw":
            from integrations.messenger.subagent_watch import resolve_job_token

            job_id = resolve_job_token(self._session.subagent_callback_tokens, value)
            return await self.start_subagent_watch(job_id)

        if action == "ss":
            return await self.stop_watched_subagent()

        if action == "se":
            await self.exit_subagent_watch()
            return t("tg.subagent_watch.closed", messenger_host_locale(self._host))

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

        from integrations.messenger.subagent_types_ui import TYPE_ACTIONS

        if action in TYPE_ACTIONS:
            from integrations.messenger.subagent_types_ui import handle_subagent_types_action

            toast = await handle_subagent_types_action(self._host, action, value)
            await self.show_subagents_picker()
            if action in ("sc", "swp", "ds") and toast:
                await self._host._send_text(toast)
            return toast or "OK"

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
                    from integrations.max.profile_visibility import is_profile_list_hidden

                    if is_profile_list_hidden(
                        self._session.bot_profile,
                        self._session.user_id,
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
                model_line = (
                    f"\n{t('tg.model', messenger_host_locale(self._host), label=restored)}"
                    if restored
                    else ""
                )
                await self._host._send_text(f"**Сессия:** `{title}`{model_line}")
                return t("tg.session_switched", messenger_host_locale(self._host))
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

        if action == "hp":
            await self.show_help_guide(value or "home")
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
        from integrations.max.command_access import is_menu_action_allowed

        if not is_menu_action_allowed(
            kind,
            self._session.bot_profile,
            self._session.user_id,
        ):
            await self._host._send_text(t("tg.menu_unavailable", messenger_host_locale(self._host)))
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
            "status": self.show_status,
            "mcp": self.show_mcp_menu,
            "cron": self.show_cron_menu,
        }
        fn = dispatch.get(kind)
        if fn:
            await fn()

    async def show_mode_picker(self) -> None:
        current = self._session.execution_mode
        await self._host._send_text_with_keyboard(
            mode_picker_text(current),
            mode_picker_keyboard(self._host._execution_modes, current),
        )

    async def show_stream_picker(self) -> None:
        on = self._host.streaming_enabled
        text = (
            "**Стриминг ответа**\n"
            f"Сейчас: `{'on' if on else 'off'}`\n\n"
            "_При включении ответ обновляется в одном сообщении по мере генерации._"
        )
        await self._host._send_text_with_keyboard(text, stream_picker_keyboard(on))

    def _cancel_subagent_watch_task(self) -> None:
        from integrations.messenger.subagent_watch import cancel_session_watch

        cancel_session_watch(self._session)

    async def present_subagent_reply_route(self, routed: Any) -> str:
        lang = messenger_host_locale(self._host)
        kind = getattr(routed, "kind", "")
        name = getattr(routed, "job_id", "") or "sub-agent"
        if kind == "delivered":
            msg = t("tg.subagent_q.sent", lang, name=name)
            await self._host._send_text(msg)
            return msg
        if kind == "gone":
            msg = t("tg.subagent_q.gone", lang)
            await self._host._send_text(msg)
            return msg
        if kind == "awaiting":
            msg = t("tg.subagent_q.awaiting", lang, name=name)
            await self._host._send_text(msg)
            return msg
        if kind == "need_target":
            await self.show_subagent_reply_picker(with_text=True)
            return t("tg.subagent_q.pick_with_text", lang)
        feedback = str(getattr(routed, "feedback", "") or "").strip()
        if feedback:
            await self._host._send_text(feedback)
        return feedback or "OK"

    async def show_subagent_reply_picker(self, *, with_text: bool = False) -> None:
        from integrations.max.keyboards import subagent_reply_keyboard
        from integrations.messenger.subagent_reply import pending_job_ids, tokens_for_jobs

        lang = messenger_host_locale(self._host)
        jobs = pending_job_ids(self._host.agent)
        if not jobs:
            await self._host._send_text(t("tg.subagent_q.gone", lang))
            return
        tokens = tokens_for_jobs(self._session.subagent_reply_tokens, jobs)
        key = "tg.subagent_q.pick_with_text" if with_text else "tg.subagent_q.pick"
        text = t(key, lang)
        kb = subagent_reply_keyboard(tokens, lang)
        if kb is None:
            await self._host._send_text(text)
            return
        await self._host._send_text_with_keyboard(text, kb)

    async def show_subagent_live_list(self) -> None:
        from integrations.max.keyboards import subagent_list_keyboard
        from integrations.messenger.subagent_watch import (
            format_list_text,
            list_watchable_jobs,
            map_job_tokens,
        )

        lang = messenger_host_locale(self._host)
        jobs = list_watchable_jobs(self._session.profile, self._host.agent)
        html = format_list_text(jobs, html=True, locale=lang)
        ids: list[str] = []
        labels: dict[str, str] = {}
        for job in jobs:
            jid = str(job.get("id") or job.get("name") or "")
            if not jid:
                continue
            ids.append(jid)
            labels[jid] = f"{job.get('name') or jid} · {job.get('status') or ''}"[:40]
        tokens = map_job_tokens(self._session.subagent_callback_tokens, ids) if ids else {}
        kb = subagent_list_keyboard(tokens, labels) if tokens else None
        if kb is None:
            await self._host._send_html(html)
            return
        try:
            await self._host._client.send_message(
                html,
                fmt="html",
                attachments=[kb],
                **self._host._reply_kwargs(),
            )
        except Exception:
            await self._host._send_text_with_keyboard(html, kb)

    async def start_subagent_watch(self, job_id: str) -> str:
        import asyncio

        from integrations.max.keyboards import subagent_watch_keyboard
        from integrations.max.models import message_id_from_response
        from integrations.messenger.subagent_watch import format_watch_text, load_watch_job

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
        payload = await self._host._client.send_message(
            html,
            fmt="html",
            attachments=[kb],
            **self._host._reply_kwargs(),
        )
        mid = message_id_from_response(payload)
        self._session.subagent_watch_job_id = jid
        self._session.subagent_watch_message_id = mid
        if running and mid:
            self._session.subagent_watch_task = asyncio.create_task(
                self._subagent_watch_loop(),
                name=f"max-sa-watch-{jid[:24]}",
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
        from integrations.max.keyboards import subagent_watch_keyboard
        from integrations.messenger.subagent_watch import format_watch_text, load_watch_job

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
            await self._host._client.edit_message(mid, html, fmt="html", attachments=[kb])
        except Exception:
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
            html = format_watch_text(job, html=True, locale=lang) + f"\n\n<i>{closed}</i>"
        else:
            html = f"<i>{closed}</i>"
        try:
            await self._host._client.edit_message(mid, html, fmt="html", attachments=None)
        except Exception:
            pass

    def _cancel_process_log_watch_task(self) -> None:
        from integrations.messenger.process_log_watch import cancel_process_log_watch

        cancel_process_log_watch(self._session)

    def _process_watch_token(self, process_id: str) -> str:
        from integrations.max.approvals import _register_callback_token

        mapping = self._session.process_callback_tokens
        for token, stored in mapping.items():
            if stored == process_id:
                return token
        return _register_callback_token(mapping, process_id)

    async def start_process_log_watch(self, process_id: str) -> str:
        import asyncio

        from integrations.max.keyboards import process_log_watch_keyboard
        from integrations.max.models import message_id_from_response
        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )

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
        payload = await self._host._client.send_message(
            html,
            fmt="html",
            attachments=[kb],
            **self._host._reply_kwargs(),
        )
        mid = message_id_from_response(payload)
        self._session.process_log_watch_id = pid
        self._session.process_log_watch_message_id = mid
        if running and mid:
            self._session.process_log_watch_task = asyncio.create_task(
                self._process_log_watch_loop(),
                name=f"max-proc-log-{pid[:24]}",
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
        from integrations.max.keyboards import process_log_watch_keyboard
        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )

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
            await self._host._client.edit_message(
                mid,
                html,
                fmt="html",
                attachments=[kb] if rec is not None else None,
            )
        except Exception:
            return False
        return running

    async def exit_process_log_watch(self, *, silent: bool = False) -> None:
        from integrations.messenger.process_log_watch import (
            format_process_log_watch,
            load_process_record,
        )

        lang = messenger_host_locale(self._host)
        pid = self._session.process_log_watch_id
        mid = self._session.process_log_watch_message_id
        self._cancel_process_log_watch_task()
        if silent or not mid:
            return
        rec = load_process_record(pid or "") if pid else None
        closed = t("tg.process.watch_closed", lang)
        if rec:
            html = format_process_log_watch(rec, html=True, locale=lang) + f"\n\n<i>{closed}</i>"
        else:
            html = f"<i>{closed}</i>"
        try:
            await self._host._client.edit_message(mid, html, fmt="html", attachments=None)
        except Exception:
            pass

    async def show_subagents_picker(self) -> None:
        from integrations.messenger.subagent_types_ui import (
            detail_keyboard_rows,
            format_detail_text,
            format_list_text,
            format_tools_text,
            is_tools_view,
            is_type_detail_view,
            list_keyboard_rows,
            tools_keyboard_rows,
        )

        if is_tools_view(self._host):
            text = _html_to_md(format_tools_text(self._host))
            rows = tools_keyboard_rows(self._host)
        elif is_type_detail_view(self._host):
            text = _html_to_md(format_detail_text(self._host))
            rows = detail_keyboard_rows(self._host)
        else:
            text = _html_to_md(format_list_text(self._host))
            rows = list_keyboard_rows(self._host)
        await self._host._send_text_with_keyboard(text, callback_rows_keyboard(rows))

    async def show_reflexion_picker(self) -> None:
        from integrations.messenger.reflexion_settings import is_reflexion_enabled_for_host

        lang = messenger_host_locale(self._host)
        on = is_reflexion_enabled_for_host(self._host)
        state = "on" if on else "off"
        text = (
            f"**{t('tg.reflexion_picker_title', lang)}**\n"
            f"{t('tg.reflexion', lang, state=state)}\n\n"
            f"_{t('tg.reflexion_picker_body', lang)}_"
        )
        await self._host._send_text_with_keyboard(
            text,
            reflexion_picker_keyboard(on, lang),
        )

    async def show_pipeline_picker(self) -> None:
        from integrations.messenger.pipeline_settings import is_pipeline_for_host

        lang = messenger_host_locale(self._host)
        mode = is_pipeline_for_host(self._host)
        text = (
            f"**{t('tg.pipeline_picker_title', lang)}**\n"
            f"{t('tg.pipeline', lang, mode=mode)}\n\n"
            f"_{t('tg.pipeline_picker_body', lang)}_"
        )
        await self._host._send_text_with_keyboard(
            text,
            pipeline_picker_keyboard(mode, lang),
        )

    async def show_profile_picker(self) -> None:
        from integrations.max.profile_visibility import is_profile_list_hidden

        profiles = self._host._get_available_profiles()
        self._session.ui_profiles = profiles
        lang = messenger_host_locale(self._host)
        current = self._host.profile

        if is_profile_list_hidden(self._session.bot_profile, self._session.user_id):
            await self._host._send_text(
                f"**{t('profiles_title', lang)}**\n"
                f"{t('tg.profile_current', lang, name=current)}\n\n"
                f"_{t('tg.profile_switch_by_key', lang)}_"
            )
            return

        lines = [
            f"**{t('profiles_title', lang)}**",
            t("tg.profile_current", lang, name=current),
            "",
            "_Профиль задаёт модели, память и skills. Смена создаёт новую сессию._",
        ]
        await self._host._send_text_with_keyboard(
            "\n".join(lines),
            profile_picker_keyboard(profiles, current),
        )

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
            await self._host._send_text_with_keyboard(
                "**Сессии**\nНет сохранённых сессий.\n\n_Отправьте сообщение или создайте новую_",
                sessions_picker_keyboard([], self._host.conversation_id),
            )
            return

        self._session.ui_sessions_page = page
        lines = [
            "**Сессии**",
            f"Текущая: `{self._host.conversation_id}`",
            "",
            "_Выберите сессию или создайте новую_",
        ]
        await self._host._send_text_with_keyboard(
            "\n".join(lines),
            sessions_picker_keyboard(sessions, self._host.conversation_id, page=page),
        )

    async def show_tools_picker(self) -> None:
        tools = self._host._recent_tool_results
        if not tools:
            await self._host._send_text(t("tg.no_tools", messenger_host_locale(self._host)))
            return
        lines = ["**Последние tools**", "_Нажмите, чтобы получить полный вывод_"]
        await self._host._send_text_with_keyboard(
            "\n".join(lines),
            tools_picker_keyboard(tools),
        )

    def _load_models_menu(self) -> None:
        state = build_models_menu(self._host.profile)
        self._session.ui_model_presets = list(state.presets)
        self._session.ui_providers = list(state.providers)

    async def show_models(self, *, provider_page: int = 0) -> None:
        from core.session_models import ensure_session_model

        ensure_session_model(self._host)
        self._load_models_menu()
        self._session.ui_models_provider_idx = None
        self._session.ui_providers_page = provider_page

        presets = self._session.ui_model_presets
        providers = self._session.ui_providers
        active = self._host.agent.model if self._host.agent else current_model_label(self._session)

        lines = [
            "**Модель для чата**",
            f"Профиль: `{self._host.profile}`",
            f"Сейчас: `{active}`",
            "",
            "**Пресеты** — main, agent_models",
            "**Провайдеры** — список моделей без префикса",
        ]
        if not presets and not providers:
            lines.append("\n**Нет моделей** — `helix models setup`")
            await self._host._send_text("\n".join(lines))
            return

        await self._host._send_text_with_keyboard(
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
            f"**Провайдер** `{prov.name}`",
            f"Сейчас в чате: `{active}`",
            f"Моделей: {total}",
        ]
        if pages > 1:
            lines.append(f"Страница {page + 1} / {pages}")
        lines.append("")
        lines.append("_Выберите модель (имя без префикса провайдера)_")

        await self._host._send_text_with_keyboard(
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

    async def show_mcp_menu(self, command: str = "/mcp") -> None:
        from integrations.max.command_access import is_mcp_management_allowed

        host = self._host
        cmd = command.lower()
        parts = cmd.split()
        profile = host.profile

        try:
            from cli.core import get_profile_manager

            cfg = get_profile_manager().load_profile(profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
        except Exception:
            servers = {}

        text_lines = [f"**MCP Servers** · профиль `{profile}`"]
        if not servers:
            text_lines.append("\nНет настроенных MCP серверов.")
            text_lines.append("Используй /mcp install или holix mcp install в терминале.")
        else:
            for name, data in list(servers.items())[:8]:
                src = data.get("_source", "manual")
                trans = data.get("transport", "stdio")
                text_lines.append(f"• `{name}` ({trans}) [{src}]")

        can_manage_mcp = is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )
        if can_manage_mcp:
            rows: list[list[dict[str, str]]] = [
                [
                    _callback_btn("📋 List", _cb("mcp", "list")),
                    _callback_btn("🛠 Install popular", _cb("mcp", "install-popular")),
                ],
                [
                    _callback_btn("➕ Install from git", _cb("mcp", "install-git")),
                    _callback_btn("🔗 Assign to agents", _cb("mcp", "assign")),
                ],
                [
                    _callback_btn("🧪 Test server", _cb("mcp", "test")),
                    _callback_btn("🗑 Remove server", _cb("mcp", "remove")),
                ],
                [
                    _callback_btn("🔄 Refresh", _cb("mcp", "refresh")),
                ],
            ]
        else:
            rows = [
                [
                    _callback_btn("📋 List", _cb("mcp", "list")),
                    _callback_btn("🔧 Tools", _cb("mcp", "tools")),
                ],
                [
                    _callback_btn("🔄 Refresh", _cb("mcp", "refresh")),
                ],
            ]
            if not servers:
                text_lines.append(f"\n_{t('tg.mcp_read_only_empty', messenger_host_locale(host))}_")

        if len(parts) > 1:
            sub = parts[1]
            if sub == "list":
                await host._mcp_list()
                return
            if sub == "tools":
                if hasattr(host, "_mcp_list_tools"):
                    await host._mcp_list_tools()
                return
            if sub in ("install", "add", "assign", "remove", "rm", "delete", "test"):
                if not can_manage_mcp:
                    await host._send_text(t("tg.mcp_read_only", messenger_host_locale(host)))
                    return
            if sub in ("install", "add"):
                arg = " ".join(parts[2:]) if len(parts) > 2 else ""
                host.run_worker(host._mcp_install(arg))
                return
            if sub in ("remove", "rm", "delete"):
                name = parts[2] if len(parts) > 2 else ""
                host.run_worker(host._mcp_remove(name))
                return

        await host._send_text_with_keyboard("\n".join(text_lines), inline_keyboard(rows))

    async def _deny_mcp_management(self) -> None:
        await self._host._send_text(t("tg.mcp_read_only", messenger_host_locale(self._host)))

    async def _handle_mcp_callback(self, value: str) -> None:
        from integrations.max.command_access import is_mcp_management_allowed

        host = self._host
        can_manage = is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )
        if value in ("list", "refresh"):
            await host._mcp_list()
            return
        if value == "tools":
            if hasattr(host, "_mcp_list_tools"):
                await host._mcp_list_tools()
            return
        if not can_manage:
            await self._deny_mcp_management()
            return
        if value == "install-popular":
            await host._send_text(
                "Чтобы установить popular MCP, напиши:\n"
                "`/mcp install context7`\n\n"
                "Или используй в терминале: `holix mcp install`"
            )
            return
        if value == "install-git":
            await host._send_text(
                "Чтобы установить из git, напиши:\n"
                "`/mcp install https://github.com/owner/repo`\n\n"
                "Или используй в терминале: `holix mcp install <url>`"
            )
            return

    async def show_help_guide(self, topic: str = "home") -> None:
        from core.host.help_guide import render_help_page

        loc = messenger_host_locale(self._host)
        command_lines = None
        if topic in ("cmds", "commands"):
            from integrations.max.command_access import commands_for_user

            specs = commands_for_user(
                self._session.bot_profile,
                int(self._session.user_id),
                locale=loc,
            )
            command_lines = [(spec.command, spec.description) for spec in specs]
        text, rows = render_help_page(topic, loc, html=False, command_lines=command_lines)
        await self._host._send_text_with_keyboard(text, help_guide_keyboard(rows))

    async def show_cron_menu(self) -> None:
        from cli.shared.commands.cron_commands import format_jobs_message
        from core.cron.store import CronStore

        host = self._host
        profile = host.profile
        store = CronStore(profile)
        jobs = store.list_jobs()

        text = format_jobs_message(profile, html=False).replace("<b>", "**").replace("</b>", "**")
        rows: list[list[dict[str, str]]] = []

        for job in jobs[:8]:
            flag = "✓" if job.enabled else "○"
            short = (job.name or job.task[:20]).replace("\n", " ")
            rows.append(
                [
                    _callback_btn(f"{flag} {short[:18]}", _cb("cr", f"v:{job.id}")),
                    _callback_btn(
                        "Вкл" if not job.enabled else "Выкл",
                        _cb("cr", f"{'e' if not job.enabled else 'd'}:{job.id}"),
                    ),
                    _callback_btn("🗑", _cb("cr", f"x:{job.id}")),
                ]
            )

        rows.append([_callback_btn("↻ Обновить", _cb("cr", "list"))])
        rows.append([_callback_btn("Как добавить", _cb("cr", "help"))])
        await host._send_text_with_keyboard(text, inline_keyboard(rows))

    async def _handle_cron_callback(self, value: str) -> None:
        from cli.shared.commands.cron_commands import resolve_job_id
        from core.cron.store import CronStore

        host = self._host
        store = CronStore(host.profile)

        if value in ("list", "refresh"):
            await self.show_cron_menu()
            return

        if value == "help":
            await host._send_text(
                "**Добавить cron**\n"
                "`/cron add every day at 9 :: текст задачи`\n"
                "`/cron add 0 9 * * * :: текст задачи`\n\n"
                "Планировщик работает в `holix gateway`."
            )
            return

        if ":" not in value:
            await self.show_cron_menu()
            return

        action, job_token = value.split(":", 1)
        try:
            job = resolve_job_id(store, job_token)
        except Exception as e:
            await host._send_text(f"Ошибка: `{e}`")
            return

        if action == "e":
            store.set_enabled(job.id, True)
            await host._send_text(f"Включено: `{job.id}`")
            await self.show_cron_menu()
            return
        if action == "d":
            store.set_enabled(job.id, False)
            await host._send_text(f"Выключено: `{job.id}`")
            await self.show_cron_menu()
            return
        if action == "x":
            store.remove(job.id)
            await host._send_text(f"Удалено: `{job.id}`")
            await self.show_cron_menu()
            return
        if action == "v":
            detail = f"**{job.name}**\n`{job.cron_expression}`\nЗадача: {job.task[:400]}"
            await host._send_text(detail)
            return

        await self.show_cron_menu()

    async def show_status(self) -> None:
        from core.session_models import ensure_session_model

        ensure_session_model(self._host)
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

        headline, rows = profile_model_summary(self._host.profile)
        lines = [
            "**Holix — статус**",
            f"Профиль: `{self._host.profile}`",
            f"Модель: `{model_line}`",
            f"Режим: `{mode}` ({mode_title})",
            f"Pipeline: `{pipeline}`",
            f"Стриминг: `{stream}`",
            f"Субагенты: `{subagents}`",
            f"Reflexion: `{reflexion}`",
            f"Сессия: `{self._host.conversation_id}`",
        ]
        if rows:
            lines.append("")
            lines.append("**Агенты:**")
            for name, provider, mdl in rows:
                lines.append(f"• `{name}` — {provider} / {mdl}")
        from integrations.max.admin import is_max_admin

        is_admin = is_max_admin(self._session.bot_profile, self._session.user_id)
        await self._host._send_text_with_keyboard(
            "\n".join(lines),
            status_menu_keyboard(messenger_host_locale(self._host), is_admin=is_admin),
        )


async def dispatch_callback(host: MaxHost, payload: str) -> str:
    if payload.startswith("cfm:"):
        return ""
    if payload.startswith("plan:"):
        return ""
    parsed = parse_callback(payload)
    if parsed is None:
        return ""
    action, value = parsed
    return await MaxInteractive(host).apply_callback(action, value)
