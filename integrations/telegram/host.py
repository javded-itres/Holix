"""Telegram AgentHost adapter for shared slash commands."""

from __future__ import annotations

import asyncio
from typing import Any

from cli.shared.commands.agent_commands import AgentCommands
from cli.shared.rich_text import content_to_plain_text
from cli.shared.slash_input import is_slash_command, normalize_slash_input
from core.i18n import t
from integrations.messenger.locale import messenger_host_locale

from integrations.telegram.commands import help_message_html, sync_bot_menu
from integrations.telegram.interactive import TelegramInteractive
from integrations.telegram.live_presenter import TelegramLivePresenter
from integrations.telegram.markdown import (
    plain_to_telegram_html,
    split_telegram_html,
)
from integrations.telegram.typing_indicator import TypingIndicator


class TelegramHost:
    """Bridges Telegram chat state to AgentCommands + agent runs."""

    def __init__(self, bot: Any, session: Any, *, edit_interval_ms: int = 500) -> None:
        self._bot = bot
        self._session = session
        self._edit_interval_ms = edit_interval_ms
        self._commands = AgentCommands(self)
        self._interactive = TelegramInteractive(self)
        self._run_tasks: set[asyncio.Task] = set()
        self._event_handler = None
        self._approvals = None

    @property
    def agent(self) -> Any:
        return self._session.agent

    @property
    def conversation_id(self) -> str:
        return self._session.conversation_id

    @property
    def profile(self) -> str:
        return self._session.profile

    @property
    def streaming_enabled(self) -> bool:
        return self._session.streaming_enabled

    @streaming_enabled.setter
    def streaming_enabled(self, value: bool) -> None:
        self._session.streaming_enabled = value

    @property
    def _execution_modes(self) -> list[str]:
        return self._session.execution_modes

    @property
    def _execution_mode_index(self) -> int:
        return self._session.execution_mode_index

    @_execution_mode_index.setter
    def _execution_mode_index(self, value: int) -> None:
        self._session.execution_mode_index = value

    @property
    def _transcript_store(self):
        return self._session._transcript_store

    @property
    def _recent_tool_results(self) -> list[dict]:
        return self._session._recent_tool_results

    @property
    def _memory_search_query(self) -> str:
        return self._session._memory_search_query

    @_memory_search_query.setter
    def _memory_search_query(self, value: str) -> None:
        self._session._memory_search_query = value

    @property
    def _memory_search_results(self) -> list[dict]:
        return self._session._memory_search_results

    @_memory_search_results.setter
    def _memory_search_results(self, value: list[dict]) -> None:
        self._session._memory_search_results = value

    def transcript_write(self, content: Any) -> None:
        text = content_to_plain_text(content)
        if text:
            asyncio.create_task(self._send_plain(text))

    async def _send_plain(self, text: str) -> None:
        try:
            await self._bot.send_message(
                self._session.chat_id,
                plain_to_telegram_html(text[:3900]),
                parse_mode="HTML",
            )
        except Exception:
            pass

    async def _send_split_plain(self, text: str) -> None:
        """Send arbitrary long plain-ish text split into multiple TG messages."""
        try:
            html = plain_to_telegram_html(text)
            chunks = split_telegram_html(html)
            for chunk in chunks:
                await self._bot.send_message(
                    self._session.chat_id,
                    chunk,
                    parse_mode="HTML",
                )
                await asyncio.sleep(0.06)
        except Exception:
            # fallback single truncated
            try:
                await self._bot.send_message(
                    self._session.chat_id,
                    plain_to_telegram_html(text[:3800]),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    def run_worker(self, work: Any, **kwargs: Any) -> None:
        if asyncio.iscoroutine(work):
            asyncio.create_task(work)
        elif callable(work):
            result = work()
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    def _refresh_status_bar(self) -> None:
        pass

    def action_clear_chat(self) -> None:
        self._session._transcript_store.clear()
        self._session._recent_tool_results.clear()
        self.transcript_write(t("cleared", messenger_host_locale(self)))

    def action_help(self) -> None:
        asyncio.create_task(self._send_html(help_message_html(messenger_host_locale(self))))

    async def _sync_telegram_menu(self) -> None:
        try:
            await sync_bot_menu(self.profile)
        except Exception:
            pass

    async def action_status(self) -> None:
        await self._interactive.show_status()

    async def _send_html(self, html: str) -> None:
        await self._bot.send_message(self._session.chat_id, html, parse_mode="HTML")

    async def _send_html_split(self, html: str) -> None:
        """Send long HTML across multiple messages (Telegram 4096 char limit)."""
        chunks = split_telegram_html(html)
        for chunk in chunks:
            if not (chunk or "").strip():
                continue
            await self._bot.send_message(
                self._session.chat_id,
                chunk,
                parse_mode="HTML",
            )
            await asyncio.sleep(0.06)

    async def _send_html_with_keyboard(self, html: str, reply_markup: Any) -> None:
        await self._bot.send_message(
            self._session.chat_id,
            html,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    def action_copy_output(self) -> None:
        lang = messenger_host_locale(self)
        text = self._session._transcript_store.last_assistant()
        if text:
            self.copy_text(text, label=t("copy_label", lang))
        else:
            self.transcript_write(t("copy_nothing", lang))

    def action_open_transcript(self) -> None:
        lang = messenger_host_locale(self)
        body = self._session._transcript_store.format_all()
        self.copy_text(body or t("transcript_empty", lang), label="transcript")

    def copy_text(self, text: str, *, label: str = "copied") -> None:
        lang = messenger_host_locale(self)
        if not text or not text.strip():
            self.transcript_write(t("copy_nothing", lang))
            return
        # Split long content across multiple messages instead of hard truncating.
        if len(text) > 3800:
            asyncio.create_task(self._send_split_plain(text))
        else:
            asyncio.create_task(self._send_plain(text))

    async def action_cycle_execution_mode(self, just_set: bool = False) -> None:
        if just_set:
            self.transcript_write(f"mode → {self._session.execution_mode}")
            return
        await self._interactive.show_mode_picker()

    def _action_stop_all(self) -> None:
        from cli.shared.agent_stop import stop_agent_activity_sync

        stop_agent_activity_sync(self)
        self.transcript_write("stopped")

    async def _create_new_session(self) -> None:
        import time

        self._session.conversation_id = f"tg_{self._session.profile}_{self._session.chat_id}_{int(time.time())}"
        self._session.session_display_name = "new"
        self._session._transcript_store.clear()
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        label = restored or (self.agent.model if self.agent else "—")
        self.transcript_write(f"new session {self._session.conversation_id} · model {label}")

    async def _show_sessions_list(self) -> None:
        if not self.agent:
            return
        try:
            self._session.known_sessions = await self.agent.list_conversations(limit=12)
        except Exception:
            self._session.known_sessions = []
        if not self._session.known_sessions:
            self.transcript_write("no sessions")
            return
        lines = []
        for i, s in enumerate(self._session.known_sessions, 1):
            cid = s.get("conversation_id", "?")
            mark = " *" if cid == self.conversation_id else ""
            lines.append(f"{i}. {cid}{mark}")
        self.transcript_write("\n".join(lines))

    async def _switch_to_session(self, index: int) -> None:
        sessions = self._session.known_sessions
        if not sessions or index < 1 or index > len(sessions):
            self.transcript_write("invalid session")
            return
        self._session.conversation_id = sessions[index - 1]["conversation_id"]
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        label = restored or (self.agent.model if self.agent else "—")
        self.transcript_write(f"switched → {self._session.conversation_id} · model {label}")

    def _rename_current_session(self, name: str) -> None:
        self._session.session_display_name = name.strip()
        self._session.session_names[self.conversation_id] = name.strip()
        self.transcript_write(f"session name: {name.strip()}")

    def _get_available_profiles(self) -> list[str]:
        from integrations.telegram.profile_visibility import list_visible_profiles

        try:
            return list_visible_profiles(
                self._session.bot_profile,
                self._session.user_id,
                current=self._session.profile,
            )
        except Exception:
            return [self._session.profile or "default"]

    async def _switch_profile(self, new_profile: str, *, profile_key: str | None = None) -> None:
        from cli.core import init_profile
        from core.profile_keys import ProfileKeyError, profile_has_access_key

        from integrations.telegram.agent_setup import create_agent

        try:
            init_profile(new_profile, profile_key=profile_key, prompt_key=False)
        except ProfileKeyError as exc:
            await self._send_html(
                f"{exc}<br><br>"
                "Отправьте: <code>/profile имя ключ</code>"
                if profile_has_access_key(new_profile) and not profile_key
                else str(exc)
            )
            return

        self._session.profile_manual_override = True
        self._session.profile = new_profile
        self._session.conversation_id = f"tg_{new_profile}_{self._session.chat_id}"
        self._session.agent = await create_agent(
            new_profile,
            bot_profile=self._session.bot_profile,
            telegram_user_id=self._session.user_id,
        )
        self._session.active_model_slot = "main"
        self._session.active_model_label = "main"
        await self._create_new_session()
        await self._send_html(
            f"Профиль: <code>{new_profile}</code>\n"
            f"Модель: <code>{self.agent.model if self.agent else '—'}</code>"
        )

    async def _search_memory(self, query: str) -> None:
        if not self.agent:
            return
        results = await self.agent.search_memory(query, top_k=6)
        if not results:
            self.transcript_write("no memory hits")
            return
        text = self.agent.format_memory_results(
            results,
            conversation_id=self.conversation_id,
            include_current=True,
        )
        for line in text.split("\n"):
            if line.strip():
                self.transcript_write(line)

    def _show_full_tool_result(self, index_from_end: int = 0) -> None:
        if not self._recent_tool_results:
            self.transcript_write("no tool results")
            return
        try:
            entry = self._recent_tool_results[-(index_from_end + 1)]
            self.copy_text(entry["full_result"], label=entry["name"])
        except IndexError:
            self.transcript_write("invalid index")

    def _list_recent_tools(self) -> None:
        if not self._recent_tool_results:
            self.transcript_write("no tools yet")
            return
        for i, e in enumerate(self._recent_tool_results, 1):
            preview = (e["full_result"] or "").split("\n")[0][:60]
            self.transcript_write(f"{i}. {e['name']} — {preview}")

    def _mcp_management_allowed(self) -> bool:
        from integrations.telegram.command_access import is_mcp_management_allowed

        return is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )

    async def _mcp_list(self) -> None:
        """List MCP servers from current profile config."""
        try:
            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
            assignments = getattr(cfg, "mcp_assignments", {}) or {}
            if not servers:
                self.transcript_write("No MCP servers in this profile.\nUse /mcp install or `holix mcp install` in terminal.")
                return
            lines = ["MCP servers:"]
            for name, data in servers.items():
                src = data.get("_source", "manual")
                trans = data.get("transport", "stdio")
                assigned = ", ".join(k for k, v in assignments.items() if name in (v or [])) or "—"
                lines.append(f"  • {name} ({trans}) [{src}] → {assigned}")
            self.transcript_write("\n".join(lines))
        except Exception as e:
            self.transcript_write(f"MCP list error: {e}")

    async def _mcp_install(self, what: str = "") -> None:
        """Install popular or from git. For interactive use Telegram menus or CLI."""
        if not self._mcp_management_allowed():
            await self._send_html(t("tg.mcp_read_only", messenger_host_locale(self)))
            return
        if not what:
            self.transcript_write("Usage: /mcp install <popular-key|git-url>\nPopular: context7, filesystem, github, ... \nOr use the /mcp menu buttons.")
            return
        try:
            # Direct logic to avoid heavy CLI import side effects
            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)

            if what.startswith(("http", "git@")):
                from core.mcp.installer import install_from_git
                data = install_from_git(what)
                name = what.rstrip("/").split("/")[-1].removesuffix(".git")
                data["_source"] = "git"
                servers = dict(getattr(cfg, "mcp_servers", {}) or {})
                servers[name] = data
                cfg.mcp_servers = servers
                # Auto-assign to main
                assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
                if "main" not in assigns:
                    assigns["main"] = []
                if name not in assigns["main"]:
                    assigns["main"].append(name)
                cfg.mcp_assignments = assigns
                manager.save_profile(self.profile, cfg)
                from integrations.telegram.markdown import escape_html
                await self._send_html(f"Installed from git as <code>{escape_html(name)}</code> (to main). Review with /mcp list")
                if self.agent:
                    try:
                        fresh = getattr(cfg, "mcp_servers", {}) or {}
                        assigns = getattr(cfg, "mcp_assignments", {}) or {}
                        await self.agent.reload_mcp(fresh, assigns)
                    except Exception as e:
                        self.transcript_write(f"[dim]Hot MCP reload: {e}[/dim]")
                if self.agent and hasattr(self.agent, "tools"):
                    mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                    self.transcript_write(f"[dim]MCP tools active: {len(mcp_ts)} ( /mcp tools )[/dim]")
                return

            # Popular
            from core.mcp.popular import get_popular_by_key
            pop = get_popular_by_key(what)
            if not pop:
                self.transcript_write(f"Unknown popular key '{what}'. See /mcp list-popular or use git url.")
                return

            from core.mcp.installer import build_config_from_popular
            data = build_config_from_popular(pop, {})
            if pop.env:
                data["env"] = dict(pop.env)  # user can set later via CLI or edit
            data["_source"] = "popular"

            servers = dict(getattr(cfg, "mcp_servers", {}) or {})
            servers[what] = data
            cfg.mcp_servers = servers
            # Auto-assign to main for hot use
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            if "main" not in assigns:
                assigns["main"] = []
            if what not in assigns["main"]:
                assigns["main"].append(what)
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            from integrations.telegram.markdown import escape_html
            await self._send_html(f"Added popular MCP <code>{escape_html(what)}</code> (auto to main). Use /mcp list or /mcp tools.")
            if self.agent:
                try:
                    fresh = getattr(cfg, "mcp_servers", {}) or {}
                    assigns = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh, assigns)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot MCP reload: {e}[/dim]")
            if self.agent and hasattr(self.agent, "tools"):
                mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                self.transcript_write(f"[dim]MCP tools active: {len(mcp_ts)} ( /mcp tools )[/dim]")
        except Exception as e:
            self.transcript_write(f"MCP install error: {e}")

    async def _mcp_assign(self, rest: str = "") -> None:
        """Basic assign: /mcp assign server main,researcher"""
        if not self._mcp_management_allowed():
            await self._send_html(t("tg.mcp_read_only", messenger_host_locale(self)))
            return
        if not rest:
            self.transcript_write("Usage: /mcp assign <server-name> <role1,role2>\nExample: /mcp assign context7 main")
            return
        try:
            parts = rest.split(None, 1)
            if len(parts) < 2:
                self.transcript_write("Need server and roles.")
                return
            srv, roles_str = parts
            roles = [r.strip() for r in roles_str.replace(",", " ").split() if r.strip()]

            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            assigns[srv] = roles
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            self.transcript_write(f"Assigned {srv} → {', '.join(roles)}")
            if self.agent:
                try:
                    fresh = getattr(cfg, "mcp_servers", {}) or {}
                    assigns = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh, assigns)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot MCP reload: {e}[/dim]")
            if self.agent and hasattr(self.agent, "tools"):
                mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                self.transcript_write(f"[dim]MCP tools active: {len(mcp_ts)} use /mcp tools[/dim]")
        except Exception as e:
            self.transcript_write(f"Assign error: {e}")

    async def _mcp_test(self, name: str = "") -> None:
        if not self._mcp_management_allowed():
            await self._send_html(t("tg.mcp_read_only", messenger_host_locale(self)))
            return
        if not name:
            self.transcript_write("Usage: /mcp test <server-name>")
            return
        try:
            from cli.core import get_profile_manager
            from core.mcp.manager import MCPManager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
            if name not in servers:
                self.transcript_write(f"Server '{name}' not found in profile.")
                return
            data = servers[name]
            m = MCPManager({name: data})
            await m.connect_all()
            tools = m.get_tool_adapters([name])
            await m.disconnect_all()
            self.transcript_write(f"Test OK for {name}: {len(tools)} tools found. Names: {[t.name for t in tools][:5]}")
        except Exception as e:
            self.transcript_write(f"Test failed for {name}: {e}")

    async def _mcp_list_tools(self) -> None:
        try:
            agent = self.agent
            if not agent or not hasattr(agent, "tools"):
                self.transcript_write("Agent not ready.")
                return
            mcp_tools = [n for n in agent.tools.get_tool_names() if str(n).startswith("mcp_")]
            if not mcp_tools:
                self.transcript_write("No MCP tools registered yet. Assign servers with /mcp assign or holix mcp assign.")
            else:
                self.transcript_write("MCP tools:\n" + "\n".join(f"  • {t}" for t in mcp_tools))
        except Exception as e:
            self.transcript_write(f"Error listing MCP tools: {e}")

    async def _mcp_remove(self, name: str = "") -> None:
        if not self._mcp_management_allowed():
            await self._send_html(t("tg.mcp_read_only", messenger_host_locale(self)))
            return
        if not name:
            self.transcript_write("Usage: /mcp remove <server-name>")
            return
        try:
            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = dict(getattr(cfg, "mcp_servers", {}) or {})
            if name not in servers:
                self.transcript_write(f"Server '{name}' not found.")
                return
            del servers[name]
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            for k, lst in list(assigns.items()):
                if name in lst:
                    assigns[k] = [x for x in lst if x != name]
            cfg.mcp_servers = servers
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            self.transcript_write(f"Removed MCP server '{name}'.")
            if self.agent:
                try:
                    fresh = getattr(cfg, "mcp_servers", {}) or {}
                    assigns = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh, assigns)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot MCP reload: {e}[/dim]")
        except Exception as e:
            self.transcript_write(f"Remove error: {e}")

    def _schedule_dismiss_confirmation_ui(self) -> None:
        from integrations.telegram.approvals import TelegramApprovals

        try:
            asyncio.get_running_loop().create_task(
                TelegramApprovals(self._bot, self._session).dismiss_confirmation_ui()
            )
        except RuntimeError:
            pass

    def _schedule_dismiss_plan_review_ui(self) -> None:
        from integrations.telegram.approvals import TelegramApprovals

        try:
            asyncio.get_running_loop().create_task(
                TelegramApprovals(self._bot, self._session).dismiss_plan_review_ui()
            )
        except RuntimeError:
            pass

    def _resolve_confirmation(self, choice: Any) -> None:
        from core.subagents.interaction import resolve_any_confirmation

        if self.agent and resolve_any_confirmation(self.agent, choice):
            self.transcript_write(f"confirmation: {choice.value}")
            self._schedule_dismiss_confirmation_ui()
            return
        self.transcript_write("no pending confirmation")

    def _resolve_plan_review(self, choice: Any, feedback: str = "") -> None:
        from core.plan_review.review_guard import get_plan_review_guard

        rid = self._session.pending_plan_review_id
        if not rid:
            self.transcript_write("no pending plan review")
            return
        guard = get_plan_review_guard()
        if guard.resolve_review(rid, choice, feedback):
            self.transcript_write(f"plan: {choice.value}")
            self._session.pending_plan_review_id = None
            self._schedule_dismiss_plan_review_ui()
        else:
            self.transcript_write("plan review failed")

    async def handle_user_text(self, text: str) -> None:
        message = text.strip()
        if not message:
            return

        from integrations.telegram.admin_broadcast import try_compose_admin_broadcast

        if await try_compose_admin_broadcast(self, message):
            return

        if self._session.pending_plan_review_id:
            from integrations.telegram.approvals import TelegramApprovals

            approvals = TelegramApprovals(self._bot, self._session)
            if approvals.resolve_plan_text(message):
                await approvals.dismiss_plan_review_ui()
                await self._send_plain("plan response recorded")
            else:
                await self._send_plain("could not apply plan response")
            return

        if self.agent:
            from core.subagents.interaction import try_route_subagent_reply

            handled, feedback = try_route_subagent_reply(self.agent, message)
            if handled:
                if feedback:
                    await self._send_plain(feedback)
                return

        normalized = normalize_slash_input(message)
        if is_slash_command(normalized) or normalized.startswith("/"):
            if await self._interactive.handle_slash(normalized):
                return
            await self._commands.handle(normalized)
            return

        from cli.shared.cron_auto_dispatch import try_cron_auto_dispatch

        if await try_cron_auto_dispatch(self, message):
            return

        self._start_agent_run(message)

    async def _send_message(self, message: str) -> None:
        """Run agent with a synthetic user message (slash skills, /init)."""
        self._start_agent_run(message)

    def _start_agent_run(self, message: str) -> None:
        """Start agent run in background so sub-agents and new user messages can overlap."""
        task = asyncio.create_task(self._run_agent(message))
        self._run_tasks.add(task)
        task.add_done_callback(self._run_tasks.discard)

    async def _run_agent(self, user_input: str) -> None:
        if not self.agent:
            await self._send_plain("agent not ready")
            return
        async with self._session.run_lock:
            await self._run_agent_locked(user_input)

    async def _run_agent_locked(self, user_input: str) -> None:
        from core.session_models import ensure_session_model

        ensure_session_model(self)

        from integrations.telegram.approvals import TelegramApprovals
        from integrations.telegram.event_handler import TelegramEventHandler

        presenter = TelegramLivePresenter(
            self._bot,
            self._session,
            edit_interval_ms=self._edit_interval_ms,
        )
        approvals = TelegramApprovals(self._bot, self._session)
        handler = TelegramEventHandler(presenter, approvals)

        def on_event(event):
            handler.handle(event)

        self.agent.events.subscribe(on_event)

        from core.tools.execution_context import (
            agent_emit_scope,
            chat_delivery_scope,
            reset_agent_emit_scope,
            reset_chat_delivery_scope,
        )
        from core.workspace import agent_path_visibility_context

        from integrations.telegram.access_approval import is_telegram_admin
        from integrations.telegram.delivery_bridge import TelegramDeliveryBridge

        delivery_bridge = TelegramDeliveryBridge(self._bot, self._session.chat_id)
        delivery_token = chat_delivery_scope(delivery_bridge)
        emit_token = agent_emit_scope(self.agent.emit)
        agent_cfg = getattr(self.agent, "config", None)
        visibility_ctx = agent_path_visibility_context(
            is_admin=is_telegram_admin(self._session.bot_profile, self._session.user_id),
            workspace_jail_enabled=bool(getattr(agent_cfg, "workspace_jail_enabled", False)),
        )

        async with TypingIndicator(self._bot, self._session.chat_id):
            await presenter.start()

            mode = self._session.execution_mode
            try:
                with visibility_ctx:
                    if self._session.streaming_enabled:
                        from core.runtime.run_consumer import consume_run_holix

                        await consume_run_holix(
                            self.agent,
                            user_input,
                            self.conversation_id,
                            stream=True,
                            execution_mode=mode,
                            emit=self.agent.emit,
                        )
                    else:
                        await self.agent.run(
                            user_input=user_input,
                            conversation_id=self.conversation_id,
                            execution_mode=mode,
                        )
            except asyncio.CancelledError:
                buf = self._session.live_buffer
                if buf:
                    buf.add_note("stopped")
            except TimeoutError:
                buf = self._session.live_buffer
                if buf:
                    buf.mark_error(
                        "Превышено время выполнения. Попробуйте ещё раз или выберите другую модель (/models)."
                    )
            except Exception as exc:
                buf = self._session.live_buffer
                if buf:
                    buf.mark_error(str(exc))
            finally:
                self.agent.events.unsubscribe(on_event)
                reset_chat_delivery_scope(delivery_token)
                reset_agent_emit_scope(emit_token)
                try:
                    await presenter.finish()
                except Exception:
                    try:
                        await presenter.ensure_final_delivered()
                    except Exception:
                        pass