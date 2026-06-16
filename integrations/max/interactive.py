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
from integrations.messenger.locale import messenger_host_locale

from integrations.max.keyboards import (
    MODE_LABELS,
    _callback_btn,
    _cb,
    inline_keyboard,
    mode_picker_keyboard,
    mode_picker_text,
    models_provider_keyboard,
    models_root_keyboard,
    parse_callback,
    profile_picker_keyboard,
    sessions_picker_keyboard,
    status_menu_keyboard,
    stream_picker_keyboard,
    tools_picker_keyboard,
)
from integrations.telegram.interactive import profile_model_summary
from integrations.telegram.model_switch import (
    MODELS_PAGE_SIZE,
    PROVIDERS_PAGE_SIZE,
    apply_preset_index,
    apply_provider_model_index,
    build_models_menu,
    current_model_label,
)

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

        if is_models_slash(cmd):
            await self.show_models()
            return True

        if is_mode_slash(cmd):
            if len(parts) > 1 and parts[1] in self._host._execution_modes:
                self._host._execution_mode_index = self._host._execution_modes.index(parts[1])
                await self._host._send_text(t("mode_set", messenger_host_locale(self._host), mode=parts[1]))
            else:
                await self.show_mode_picker()
            return True

        if lower.startswith("/stream"):
            if len(parts) > 1:
                self._host.streaming_enabled = parts[1] in ("on", "true", "1")
                state = "on" if self._host.streaming_enabled else "off"
                await self._host._send_text(t("streaming", messenger_host_locale(self._host), state=state))
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

        if lower.startswith("/subagent") or lower == "/subagents":
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
        if action == "m" and value in self._host._execution_modes:
            self._host._execution_mode_index = self._host._execution_modes.index(value)
            await self.show_mode_picker()
            return t("tg.mode", messenger_host_locale(self._host), mode=value)

        if action == "st":
            self._host.streaming_enabled = value == "1"
            await self.show_stream_picker()
            state = "on" if self._host.streaming_enabled else "off"
            return t("tg.streaming", messenger_host_locale(self._host), state=state)

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
                model_line = f"\n{t('tg.model', messenger_host_locale(self._host), label=restored)}" if restored else ""
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
                self._session.ui_sessions = await self._host.agent.list_conversations(limit=24)
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
                    _callback_btn("Вкл" if not job.enabled else "Выкл", _cb("cr", f"{'e' if not job.enabled else 'd'}:{job.id}")),
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
            detail = (
                f"**{job.name}**\n"
                f"`{job.cron_expression}`\n"
                f"Задача: {job.task[:400]}"
            )
            await host._send_text(detail)
            return

        await self.show_cron_menu()

    async def show_status(self) -> None:
        from core.session_models import ensure_session_model

        ensure_session_model(self._host)
        mode = self._session.execution_mode
        stream = "on" if self._host.streaming_enabled else "off"
        mode_title = MODE_LABELS.get(mode, (mode, ""))[0]
        model_line = current_model_label(self._session)
        if self._host.agent:
            model_line = self._host.agent.model
        subagents = "—"
        if self._host.agent:
            cfg = getattr(self._host.agent, "config", None)
            if cfg and getattr(cfg, "enable_subagents", True):
                subagents = "вкл"
            else:
                subagents = "выкл"

        headline, rows = profile_model_summary(self._host.profile)
        lines = [
            "**Holix — статус**",
            f"Профиль: `{self._host.profile}`",
            f"Модель: `{model_line}`",
            f"Режим: `{mode}` ({mode_title})",
            f"Стриминг: `{stream}`",
            f"Субагенты: `{subagents}`",
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