"""MAX AgentHost adapter for shared slash commands."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cli.shared.commands.agent_commands import AgentCommands
from cli.shared.rich_text import content_to_plain_text
from cli.shared.slash_input import is_slash_command, normalize_slash_input
from core.i18n import host_locale, t

from integrations.max.client import MaxClient
from integrations.max.commands import help_message_markdown
from integrations.max.event_handler import MaxEventHandler
from integrations.max.interactive import MaxInteractive
from integrations.max.live_presenter import MaxLivePresenter
from integrations.max.markdown import (
    plain_to_max_html,
    prepare_max_markdown,
    split_max_html,
    truncate_max_text,
)
from integrations.max.models import reply_kwargs_for_session

logger = logging.getLogger(__name__)


class MaxHost:
    """Bridges MAX chat state to AgentCommands + agent runs."""

    def __init__(
        self,
        client: MaxClient,
        session: Any,
        *,
        edit_interval_ms: int = 700,
    ) -> None:
        self._client = client
        self._session = session
        self._edit_interval_ms = edit_interval_ms
        self._commands = AgentCommands(self)
        self._interactive = MaxInteractive(self)
        self._run_tasks: set[asyncio.Task] = set()

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
            asyncio.create_task(self._send_text(text))

    def _reply_kwargs(self) -> dict:
        return reply_kwargs_for_session(
            user_id=self._session.user_id,
            reply_user_id=self._session.reply_user_id,
            reply_chat_id=self._session.reply_chat_id,
            chat_type=self._session.chat_type,
        )

    async def _send_text(self, text: str, *, formatted: bool | None = None) -> None:
        use_html = formatted if formatted is not None else True
        if not use_html:
            await self._send_plain_chunks([text])
            return

        html = plain_to_max_html(text)
        chunks = split_max_html(html) or [html]
        for chunk in chunks:
            sent = await self._send_formatted_chunk(chunk, raw_fallback=text)
            if not sent:
                logger.error("MAX _send_text failed for chunk (%d chars)", len(chunk))
            await asyncio.sleep(0.06)

    async def _send_html(self, html: str) -> None:
        chunks = split_max_html(html) or [html]
        for chunk in chunks:
            try:
                await self._client.send_message(
                    chunk,
                    fmt="html",
                    **self._reply_kwargs(),
                )
                await asyncio.sleep(0.06)
            except Exception:
                logger.exception("MAX _send_html failed for chunk (%d chars)", len(chunk))

    async def _send_plain_chunks(self, chunks: list[str]) -> None:
        for chunk in chunks:
            body = truncate_max_text(chunk)
            if not body.strip():
                continue
            try:
                await self._client.send_message(body, **self._reply_kwargs())
                await asyncio.sleep(0.06)
            except Exception:
                logger.exception("MAX send_message plain chunk failed")

    async def _send_formatted_chunk(self, chunk: str, *, raw_fallback: str) -> bool:
        variants: list[tuple[str, str | None]] = [
            (chunk, "html"),
            (prepare_max_markdown(raw_fallback), "markdown"),
            (truncate_max_text(raw_fallback), None),
        ]
        seen: set[str] = set()
        for body, fmt in variants:
            payload = (body or "").strip()
            if not payload or payload in seen:
                continue
            seen.add(payload)
            try:
                await self._client.send_message(
                    payload,
                    fmt=fmt,
                    **self._reply_kwargs(),
                )
                return True
            except Exception:
                continue
        try:
            await self._client.send_message(
                truncate_max_text(raw_fallback),
                **self._reply_kwargs(),
            )
            return True
        except Exception:
            logger.exception("MAX send_message all fallbacks failed")
            return False

    async def _send_text_with_keyboard(self, text: str, keyboard: dict) -> None:
        try:
            await self._client.send_message(
                text,
                attachments=[keyboard],
                **self._reply_kwargs(),
            )
        except Exception:
            logger.exception("MAX keyboard message send failed")
            await self._send_text(text)

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
        self.transcript_write(t("cleared", host_locale(self)))

    def action_help(self) -> None:
        asyncio.create_task(self._send_text(help_message_markdown(host_locale(self))))

    async def action_status(self) -> None:
        await self._interactive.show_status()

    def action_copy_output(self) -> None:
        lang = host_locale(self)
        text = self._session._transcript_store.last_assistant()
        if text:
            self.copy_text(text, label=t("copy_label", lang))
        else:
            self.transcript_write(t("copy_nothing", lang))

    def action_open_transcript(self) -> None:
        lang = host_locale(self)
        body = self._session._transcript_store.format_all()
        self.copy_text(body or t("transcript_empty", lang), label="transcript")

    def copy_text(self, text: str, *, label: str = "copied") -> None:
        lang = host_locale(self)
        if not text or not text.strip():
            self.transcript_write(t("copy_nothing", lang))
            return
        asyncio.create_task(self._send_text(text))

    async def action_cycle_execution_mode(self, just_set: bool = False) -> None:
        if just_set:
            self.transcript_write(f"mode → {self._session.execution_mode}")
            return
        modes = ", ".join(self._execution_modes)
        await self._send_text(f"**Режимы:** {modes}\nТекущий: `{self._session.execution_mode}`")

    def _action_stop_all(self) -> None:
        for task in list(self._run_tasks):
            if not task.done():
                task.cancel()
        self.transcript_write("stopped")

    async def _create_new_session(self) -> None:
        import time

        from integrations.max.models import conversation_id_for_max

        base = conversation_id_for_max(
            self._session.profile,
            self._session.user_id,
            chat_id=self._session.reply_chat_id,
            chat_type=self._session.chat_type,
        )
        self._session.conversation_id = f"{base}_{int(time.time())}"
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
        from integrations.max.profile_visibility import list_visible_profiles

        try:
            return list_visible_profiles(
                self._session.bot_profile,
                self._session.user_id,
                current=self._session.profile,
            )
        except Exception:
            return [self._session.profile or "default"]

    def _mcp_management_allowed(self) -> bool:
        from integrations.max.command_access import is_mcp_management_allowed

        return is_mcp_management_allowed(
            self._session.bot_profile,
            self._session.user_id,
        )

    async def _switch_profile(self, new_profile: str) -> None:
        from integrations.max.agent_setup import create_agent

        self._session.profile = new_profile
        self._session.agent = await create_agent(new_profile)
        self._session.active_model_slot = "main"
        self._session.active_model_label = "main"
        await self._create_new_session()
        await self._send_text(
            f"**Профиль:** `{new_profile}`\n**Модель:** `{self.agent.model if self.agent else '—'}`"
        )

    async def _search_memory(self, query: str) -> None:
        if not self.agent:
            return
        results = await self.agent.search_memory(query, top_k=6)
        if not results:
            self.transcript_write("no memory hits")
            return
        for i, mem in enumerate(results, 1):
            content = (mem.get("content") or "")[:300]
            self.transcript_write(f"{i}. {content}")

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

    async def _mcp_list(self) -> None:
        try:
            from cli.core import get_profile_manager

            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
            if not servers:
                self.transcript_write("No MCP servers. Use `helix mcp install` in terminal.")
                return
            lines = ["**MCP servers:**"]
            for name, data in servers.items():
                trans = data.get("transport", "stdio")
                lines.append(f"• {name} ({trans})")
            self.transcript_write("\n".join(lines))
        except Exception as e:
            self.transcript_write(f"MCP list error: {e}")

    async def _mcp_install(self, what: str = "") -> None:
        if not self._mcp_management_allowed():
            await self._send_text(t("tg.mcp_read_only", host_locale(self)))
            return
        self.transcript_write(
            "Установка MCP через MAX пока не поддерживается. Используйте: `helix mcp install` в терминале."
            + (f" (запрошено: {what})" if what else "")
        )

    def _schedule_dismiss_confirmation_ui(self) -> None:
        from integrations.max.approvals import MaxApprovals

        try:
            asyncio.get_running_loop().create_task(
                MaxApprovals(self._client, self._session).dismiss_confirmation_ui()
            )
        except RuntimeError:
            pass

    def _schedule_dismiss_plan_review_ui(self) -> None:
        from integrations.max.approvals import MaxApprovals

        try:
            asyncio.get_running_loop().create_task(
                MaxApprovals(self._client, self._session).dismiss_plan_review_ui()
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

    async def send_local_file(self, path: str, *, caption: str = "") -> None:
        from pathlib import Path

        from integrations.max.uploads import send_file_message

        target = reply_kwargs_for_session(
            user_id=self._session.user_id,
            reply_user_id=self._session.reply_user_id,
            reply_chat_id=self._session.reply_chat_id,
            chat_type=self._session.chat_type,
        )
        await send_file_message(
            self._client,
            Path(path),
            user_id=target.get("user_id"),
            chat_id=target.get("chat_id"),
            caption=caption,
        )

    async def handle_user_text(self, text: str) -> None:
        message = text.strip()
        if not message:
            return

        from integrations.max.admin_broadcast import try_compose_admin_broadcast

        if await try_compose_admin_broadcast(self, message):
            return

        if self._session.pending_plan_review_id:
            from integrations.max.approvals import MaxApprovals

            approvals = MaxApprovals(self._client, self._session)
            if approvals.resolve_plan_text(message):
                await approvals.dismiss_plan_review_ui()
                await self._send_text("plan response recorded")
            else:
                await self._send_text("could not apply plan response")
            return

        if self._session.pending_files:
            from integrations.max.file_handler import build_agent_prompt

            files = list(self._session.pending_files)
            self._session.pending_files.clear()
            message = build_agent_prompt(message, files)

        if self.agent:
            from core.subagents.interaction import try_route_subagent_reply

            handled, feedback = try_route_subagent_reply(self.agent, message)
            if handled:
                if feedback:
                    await self._send_text(feedback)
                return

        self._session._transcript_store.append("user", message)

        from integrations.max.tool_dispatch import try_direct_tool_dispatch

        handled, tool_text = await try_direct_tool_dispatch(self, message)
        if handled:
            if tool_text:
                await self._send_text(tool_text)
            return

        normalized = normalize_slash_input(message)
        if is_slash_command(normalized) or normalized.startswith("/"):
            if await self._interactive.handle_slash(normalized):
                return
            await self._commands.handle(normalized)
            return

        self._start_agent_run(message)

    async def _send_message(self, message: str) -> None:
        self._start_agent_run(message)

    def _start_agent_run(self, message: str) -> None:
        """Start agent run in background so sub-agents and user replies can overlap."""
        task = asyncio.create_task(self._run_agent(message))
        self._run_tasks.add(task)
        task.add_done_callback(self._run_tasks.discard)

    async def _run_agent(self, user_input: str) -> None:
        if not self.agent:
            await self._send_text("agent not ready")
            return
        async with self._session.run_lock:
            await self._run_agent_locked(user_input)

    async def _run_agent_locked(self, user_input: str) -> None:
        logger.info(
            "MAX agent run start (conversation=%s, preview=%r)",
            self.conversation_id,
            user_input[:80],
        )
        from core.session_models import ensure_session_model

        ensure_session_model(self)

        from integrations.max.approvals import MaxApprovals
        from integrations.max.config import load_max_settings

        max_settings = load_max_settings(self.profile)
        presenter = MaxLivePresenter(
            self._client,
            self._session,
            edit_interval_ms=max_settings.edit_interval_ms,
            heartbeat_interval_s=max_settings.heartbeat_interval_s,
        )
        approvals = MaxApprovals(self._client, self._session)
        handler = MaxEventHandler(presenter, approvals)

        def on_event(event):
            handler.handle(event)

        self.agent.events.subscribe(on_event)

        from core.tools.execution_context import (
            chat_delivery_scope,
            reset_chat_delivery_scope,
        )
        from core.workspace import agent_path_visibility_context

        from integrations.max.admin import is_max_admin
        from integrations.max.delivery_bridge import MaxDeliveryBridge

        target = self._reply_kwargs()
        delivery_bridge = MaxDeliveryBridge(
            self._client,
            user_id=target.get("user_id"),
            chat_id=target.get("chat_id"),
        )
        delivery_token = chat_delivery_scope(delivery_bridge)
        agent_cfg = getattr(self.agent, "config", None)
        visibility_ctx = agent_path_visibility_context(
            is_admin=is_max_admin(self._session.bot_profile, self._session.user_id),
            workspace_jail_enabled=bool(getattr(agent_cfg, "workspace_jail_enabled", False)),
        )

        from integrations.max.typing_indicator import TypingIndicator

        async with TypingIndicator(self._client, self._session.reply_chat_id):
            try:
                await presenter.start()
                mode = self._session.execution_mode
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
                logger.exception("MAX agent run failed")
            finally:
                self.agent.events.unsubscribe(on_event)
                reset_chat_delivery_scope(delivery_token)
                try:
                    await presenter.finish()
                except Exception:
                    logger.exception("MAX presenter finish failed; retrying final delivery")
                    try:
                        await presenter.ensure_final_delivered()
                    except Exception:
                        logger.exception("MAX final delivery retry failed")
                if not presenter.final_delivered:
                    try:
                        await presenter.ensure_final_delivered()
                    except Exception:
                        logger.exception("MAX post-run final delivery failed")
                logger.info(
                    "MAX agent run finished (conversation=%s, final_delivered=%s)",
                    self.conversation_id,
                    presenter.final_delivered,
                )