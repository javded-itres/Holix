"""Interactive pickers and callback handling for Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.i18n import host_locale, t
from integrations.telegram.keyboards import (
    MODE_LABELS,
    mode_picker_html,
    mode_picker_keyboard,
    models_provider_keyboard,
    models_root_keyboard,
    parse_callback,
    profile_picker_keyboard,
    sessions_picker_keyboard,
    skills_picker_keyboard,
    SKILLS_PAGE_SIZE,
    status_menu_keyboard,
    stream_picker_keyboard,
    tools_picker_keyboard,
)
from integrations.telegram.model_switch import (
    MODELS_PAGE_SIZE,
    PROVIDERS_PAGE_SIZE,
    apply_preset_index,
    apply_provider_model_index,
    build_models_menu,
    current_model_label,
)
from integrations.telegram.markdown import escape_html

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

        if is_models_slash(cmd):
            await self.show_models()
            return True

        if is_mode_slash(cmd):
            if len(parts) > 1 and parts[1] in self._host._execution_modes:
                self._host._execution_mode_index = self._host._execution_modes.index(parts[1])
                lang = host_locale(self._host)
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
                    escape_html(t("tg.streaming", host_locale(self._host), state=state))
                )
            else:
                await self.show_stream_picker()
            return True

        if lower.startswith("/profile"):
            if len(parts) >= 2:
                return False
            await self.show_profile_picker()
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

        if lower.startswith("/subagent") or lower == "/subagents":
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
                "Планировщик работает в <code>helix gateway</code>."
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
        assignments = getattr(cfg, "mcp_assignments", {}) if cfg else {}

        text_lines = [f"<b>MCP Servers</b> · профиль <code>{escape_html(profile)}</code>"]

        if not servers:
            text_lines.append("\nНет настроенных MCP серверов.")
            text_lines.append("Используй /mcp install или helix mcp install в терминале.")
        else:
            for name, data in list(servers.items())[:8]:
                src = data.get("_source", "manual")
                trans = data.get("transport", "stdio")
                text_lines.append(f"• <code>{escape_html(name)}</code> ({trans}) [{src}]")

        kb_rows = [
            [
                InlineKeyboardButton(text="📋 List", callback_data="mcp:list"),
                InlineKeyboardButton(text="🛠 Install popular", callback_data="mcp:install-popular"),
            ],
            [
                InlineKeyboardButton(text="➕ Install from git", callback_data="mcp:install-git"),
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
        if action == "m" and value in self._host._execution_modes:
            self._host._execution_mode_index = self._host._execution_modes.index(value)
            await self.show_mode_picker()
            lang = host_locale(self._host)
            return t("tg.mode", lang, mode=value)

        if action == "st":
            self._host.streaming_enabled = value == "1"
            await self.show_stream_picker()
            lang = host_locale(self._host)
            state = "on" if self._host.streaming_enabled else "off"
            return t("tg.streaming", lang, state=state)

        if action == "pi":
            lang = host_locale(self._host)
            profiles = self._session.ui_profiles
            idx = int(value)
            if 0 <= idx < len(profiles):
                name = profiles[idx]
                if name != self._host.profile:
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
                lang = host_locale(self._host)
                model_line = (
                    f"\n{escape_html(t('tg.model', lang, label=restored))}"
                    if restored
                    else ""
                )
                await self._host._send_html(
                    f"{escape_html(t('tg.session', lang, title='', model=''))}"
                    f"<code>{escape_html(title)}</code>{model_line}"
                )
                return t("tg.session_switched", lang)
            return t("tg.session_invalid", host_locale(self._host))

        if action == "sp":
            await self.show_sessions_picker(page=int(value))
            return ""

        if action == "sn":
            await self._host._create_new_session()
            await self.show_sessions_picker()
            return t("tg.new_session", host_locale(self._host))

        if action == "t":
            self._host._show_full_tool_result(int(value))
            return t("tg.tool_result", host_locale(self._host))

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
            return t("tg.model", host_locale(self._host), label=label)

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
                return t("tg.error", host_locale(self._host))
            pi, mi = int(parts[0]), int(parts[1])
            label = await apply_provider_model_index(self._host, pi, mi)
            await self.show_provider_models(pi, page=self._session.ui_models_page)
            return t("tg.model", host_locale(self._host), label=label)

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

        return t("tg.unknown_action", host_locale(self._host))

    async def _refresh(self, kind: str) -> None:
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

    async def show_profile_picker(self) -> None:
        profiles = self._host._get_available_profiles()
        self._session.ui_profiles = profiles

    async def _handle_mcp_callback(self, value: str) -> None:
        """Handle mcp:* callbacks from the MCP menu."""
        host = self._host
        if value == "list" or value == "refresh":
            await host._mcp_list()
            return
        if value == "install-popular":
            await self._show_mcp_popular_picker()
            return
        if value == "install-git":
            await host._send_html(
                "Чтобы установить из git, напиши:\n"
                "<code>/mcp install https://github.com/owner/repo</code>\n\n"
                "Или используй в терминале: <code>helix mcp install &lt;url&gt;</code>"
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
            rows.append([
                InlineKeyboardButton(
                    text=f"{p.display_name} ({p.category})",
                    callback_data=f"mcp:install:{p.key}"
                )
            ])
        rows.append([InlineKeyboardButton(text="« Назад", callback_data="mcp:refresh")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await self._host._send_html_with_keyboard(
            "<b>Популярные MCP серверы</b>\nВыбери для установки (defaults):",
            kb
        )

    async def _show_mcp_assign_picker(self) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
        text += "\n\nИспользуй: <code>/mcp assign &lt;server&gt; main,researcher</code> или helix mcp assign в терминале."
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
            rows.append([
                InlineKeyboardButton(text=f"🗑 {escape_html(s)}", callback_data=f"mcp:remove-confirm:{s}")
            ])
        rows.append([InlineKeyboardButton(text="« Назад", callback_data="mcp:refresh")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await self._host._send_html_with_keyboard(
            "<b>Выберите MCP сервер для удаления:</b>",
            kb
        )
        lines = [
            "<b>Профиль Helix</b>",
            f"Сейчас: <code>{escape_html(self._host.profile)}</code>",
            "",
            "<i>Профиль задаёт модели, память и skills. Смена создаёт новую сессию.</i>",
        ]
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            profile_picker_keyboard(profiles, self._host.profile),
        )

    async def show_sessions_picker(self, *, page: int = 0) -> None:
        if self._host.agent:
            try:
                self._session.ui_sessions = await self._host.agent.list_conversations(
                    limit=24
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
            await self._host._send_plain(t("tg.no_tools", host_locale(self._host)))
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
                "<code>/hub</code> или <code>helix hub install</code>.</i>"
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
            lines.append("\n<b>Нет моделей</b> — <code>helix models setup</code>")
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
        mode = self._session.execution_mode
        stream = "on" if self._host.streaming_enabled else "off"
        mode_title = MODE_LABELS.get(mode, (mode, ""))[0]
        model_line = current_model_label(self._session)
        if self._host.agent:
            model_line = self._host.agent.model
        subagents = "—"
        if self._host.agent:
            cfg = getattr(self._host.agent, "config", None)
            if cfg and getattr(cfg, "enable_subagents", False):
                subagents = "вкл"
            else:
                subagents = "выкл"

        lines = [
            "<b>Helix — статус</b>",
            f"Профиль: <code>{escape_html(self._host.profile)}</code>",
            f"Модель: <code>{escape_html(model_line)}</code>",
            f"Режим: <code>{escape_html(mode)}</code> ({escape_html(mode_title)})",
            f"Стриминг: <code>{stream}</code>",
            f"Субагенты: <code>{subagents}</code>",
            f"Сессия: <code>{escape_html(self._host.conversation_id)}</code>",
        ]
        await self._host._send_html_with_keyboard(
            "\n".join(lines),
            status_menu_keyboard(host_locale(self._host)),
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