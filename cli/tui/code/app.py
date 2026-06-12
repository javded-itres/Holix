"""
Strict Holix TUI (Claude Code / Grok Build style).

Single-column transcript, compact tool lines, status footer — no sidebar, no command palette.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from core.agent import HolixAgent
from core.agent_events import AgentEvent
from core.plan_review.review_events import PlanReviewRequestEvent
from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent
from rich.panel import Panel
from rich.syntax import Syntax
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, TextArea

from cli.core import HOLIX_HOME, ProfileConfig, ProfileManager, init_profile
from cli.tui.code.handlers import CodeEventHandler, SlashCommandsCore
from cli.tui.code.styles import CODE_TUI_CSS
from cli.tui.code.widgets import (
    CodeContextBar,
    CodePrompt,
    CodeStatusBar,
    CodeTranscript,
    CopySelectionBar,
    SlashCommandSuggestions,
    TranscriptPanel,
)
from cli.tui.modals import ModalStack, TranscriptViewerScreen
from cli.tui.shared.clipboard import copy_text_best_effort
from cli.tui.shared.copy_bar import COPY_BAR_ID, hide_copy_bar, show_copy_bar
from cli.tui.shared.keyboard_layout import (
    code_tui_bindings,
    is_macos,
    is_slash_command,
    normalize_slash_input,
    primary_copy_shortcut_label,
    shortcut_label,
    slash_command_prefix,
    terminal_copy_hint,
)
from cli.tui.shared.slash_suggestions import match_slash_commands
from cli.tui.shared.transcript_store import TranscriptStore, plain_from_rich_write


class HolixCodeApp(App):
    """Code-style strict TUI."""

    ENABLE_MOUSE_SUPPORT = True
    CSS = CODE_TUI_CSS

    BINDINGS = code_tui_bindings()

    def __init__(self, profile: str = "default", config: ProfileConfig | None = None):
        super().__init__()
        self.profile = profile
        self.config = config or init_profile(profile)
        self.profile_manager = ProfileManager()
        self.agent: HolixAgent | None = None
        self._resolved_model = self.config.model
        self.active_model_slot = "main"
        self.active_model_label = ""
        self._model_synced_for: str | None = None

        self._event_handler = CodeEventHandler(self)
        self._slash = SlashCommandsCore(self)
        self._modals = ModalStack(self)

        self.conversation_id = f"tui_{profile}"
        self.session_display_name = "main"
        self.session_names: dict[str, str] = {}
        self.known_sessions: list[dict] = []

        self.streaming_enabled = False
        self._stream_buffer = ""
        self._auto_scroll = True
        self._is_streaming = False
        self._first_delta_seen = False
        self._last_user_message: str | None = None

        self._active_tools: dict[str, str] = {}
        self._recent_tool_results: list[dict] = []
        self._last_tool_call: dict | None = None

        self._memory_search_results: list[dict] = []
        self._memory_search_query = ""

        self._execution_modes = ["react", "plan_and_execute", "hybrid", "auto"]
        self._execution_mode_index = 0
        self._cached_context_display: str | None = None
        self._last_context_refresh: float = 0.0

        self._pending_confirmation: Any | None = None
        self._action_guard_reference: Any | None = None

        self._tab_matches: list[str] = []
        self._tab_index = -1
        self._slash_suggestion_navigated = False
        self._transcript_store = TranscriptStore()
        self._last_assistant_plain: str | None = None

    def compose(self) -> ComposeResult:
        yield TranscriptPanel()
        thinking = Static("", id="thinking-line")
        thinking.display = False
        yield thinking
        yield Static("", id="scroll-hint")
        yield CodeStatusBar()
        yield CodeContextBar()
        yield CopySelectionBar(id=COPY_BAR_ID)
        yield SlashCommandSuggestions()
        yield CodePrompt()

    async def on_mount(self) -> None:
        self.title = "Holix"
        self._load_ui_state()
        self.transcript_write("[bold]Holix[/bold]  [dim]code ui[/dim]")
        hints = (
            "[dim]Enter send · Shift+Enter newline · / — command menu (↑↓ pick) · "
            "/models — switch LLM · /hub — skill catalog · F2 /open — copy window · "
            "click chat then select + Copy"
        )
        if is_macos():
            hints += " · RU: ,help = /help (или Shift+7 → /)"
        term_hint = terminal_copy_hint()
        if term_hint:
            hints += f" · {term_hint}"
        hints += "[/dim]\n"
        self.transcript_write(hints)
        self._refresh_status_bar()
        await self._initialize_agent()
        self._restore_prompt_focus(delay=0.1, force=True)

    async def on_unmount(self) -> None:
        if getattr(self, "agent", None):
            try:
                await self.agent.close()
            except Exception:
                pass

    # --- Transcript API (TuiHost + modals) ---

    def transcript_write(
        self,
        content: Any,
        *,
        store_kind: str | None = None,
        store_plain: str | None = None,
        store_markdown: str | None = None,
        store_title: str | None = None,
    ) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            log.write(content)
            if self._auto_scroll:
                log.scroll_end(animate=False)
            self._update_scroll_hint()
        except Exception:
            pass

        if store_kind:
            plain = store_plain
            markdown = store_markdown
            if plain is None:
                plain, derived_md = plain_from_rich_write(content)
                if markdown is None:
                    markdown = derived_md
            if plain:
                self._transcript_store.append(
                    store_kind,
                    plain,
                    markdown=markdown,
                    title=store_title,
                )
                if store_kind == "assistant":
                    self._last_assistant_plain = markdown or plain

    def _append_to_log(self, content: Any) -> None:
        """Alias for ModalStack / confirmation presenters."""
        self.transcript_write(content)

    def transcript_scroll_bottom(self) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            log.scroll_end(animate=False)
            self._auto_scroll = True
            self._update_scroll_hint()
        except Exception:
            pass

    def set_thinking(self, message: str | None) -> None:
        try:
            line = self.query_one("#thinking-line", Static)
            if message:
                line.update(f"· {message}")
                line.display = True
            else:
                line.update("")
                line.display = False
        except Exception:
            pass

    def set_status_line(self, text: str) -> None:
        try:
            self.query_one("#status-bar", CodeStatusBar).set_line(text)
        except Exception:
            pass

    def _refresh_status_bar(self) -> None:
        cwd = os.path.basename(os.getcwd()) or "."
        mode = self._execution_modes[self._execution_mode_index]
        stream = " stream" if self.streaming_enabled else ""
        ctx = ""
        if self._cached_context_display:
            import re

            ctx = " · " + re.sub(r"\[/?[^\]]+\]", "", self._cached_context_display)
        sess = self.session_display_name or "session"
        model = getattr(self, "_resolved_model", self.config.model)
        from core.i18n import LocaleStore

        lang = LocaleStore(self.profile).get().upper()
        line = f"{self.profile} · {lang} · {model}{stream} · {cwd} · {mode} · {sess}{ctx}"
        self.set_status_line(line)

    # --- Persistence ---

    def _state_path(self) -> Path:
        return HOLIX_HOME / "tui-state.json"

    def _load_ui_state(self) -> None:
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            if cid := data.get("conversation_id"):
                self.conversation_id = cid
            if data.get("streaming_enabled"):
                self.streaming_enabled = True
            modes = self._execution_modes
            if (m := data.get("execution_mode")) in modes:
                self._execution_mode_index = modes.index(m)
        except Exception:
            pass

    def _save_ui_state(self) -> None:
        try:
            self._state_path().parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "conversation_id": self.conversation_id,
                "streaming_enabled": self.streaming_enabled,
                "execution_mode": self._execution_modes[self._execution_mode_index],
            }
            self._state_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    # --- Agent ---

    async def _initialize_agent(self) -> None:
        self.transcript_write("[dim]initializing…[/dim]")
        self.set_status_line("initializing")

        from core.di import resolve_runtime_config
        from core.models.manager import ModelManager
        from core.models.profile_cleanup import MISSING_LLM_HINT, profile_has_llm_config

        if not profile_has_llm_config(self.config):
            self.transcript_write(f"[red]{MISSING_LLM_HINT}[/red]\n")
            self.set_status_line("no llm")
            self.agent = None
            self._resolved_model = "—"
            return

        runtime_config = resolve_runtime_config(self.config)
        try:
            mc = ModelManager(self.config).get_default_model_config()
            if not mc:
                raise ValueError("no model configuration")
            runtime_config = runtime_config.with_overrides(
                model=mc.model,
                base_url=mc.base_url,
                api_key=mc.api_key,
                temperature=mc.temperature,
            )
            self._resolved_model = mc.model
        except Exception as e:
            self.transcript_write(f"[red]model config error: {e}. {MISSING_LLM_HINT}[/red]\n")
            self.set_status_line("no llm")
            self.agent = None
            self._resolved_model = "—"
            return

        self.agent = HolixAgent(config=runtime_config)
        self.agent.events.subscribe(self._on_agent_event)
        await self.agent.initialize()
        await self._load_conversation_history()
        await self._ensure_session_context()
        await self._load_known_sessions()
        self.transcript_write("[dim]ready — type a message or /help[/dim]\n")
        self.set_status_line("ready")
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self.transcript_write(f"[dim]model (session): {restored}[/dim]\n")
        await self._update_context_display_async()
        self._maybe_hub_autoupdate()

    @work(thread=True, group="hub_autoupdate", exclusive=True)
    def _maybe_hub_autoupdate(self) -> None:
        """Background ClawHub updates when profile hub_auto_update is enabled."""
        if not self.config or not getattr(self.config, "hub_auto_update", False):
            return
        try:
            from core.hub import SkillImporter
            from core.hub.autoupdate import run_hub_autoupdate

            importer = SkillImporter(Path(self.config.skills_dir))
            result = run_hub_autoupdate(
                importer,
                enabled=True,
                interval_hours=float(
                    getattr(self.config, "hub_auto_update_interval_hours", 24) or 24
                ),
            )
            if result.ran and result.updated:
                self.call_from_thread(
                    self.transcript_write,
                    f"[dim]hub autoupdate: {', '.join(result.updated[:5])}"
                    + ("…" if len(result.updated) > 5 else "")
                    + "[/dim]",
                )
        except Exception:
            pass

    async def _ensure_session_context(self) -> None:
        """Compress persisted history when usage exceeds threshold (e.g. after restart)."""
        if not self.agent:
            return
        try:
            from core.runtime.context_session import ensure_conversation_context

            if await ensure_conversation_context(self.agent, self.conversation_id):
                self.transcript_write("[dim]· context compressed on load[/dim]")
        except Exception:
            pass

    def _maybe_refresh_context_display(self, *, min_interval_s: float = 2.0) -> None:
        now = time.monotonic()
        if now - self._last_context_refresh < min_interval_s:
            return
        self._last_context_refresh = now
        self.run_worker(self._update_context_display_async())

    async def _load_conversation_history(self) -> None:
        if not self.agent:
            return
        try:
            history = await self.agent.get_conversation_history(self.conversation_id, limit=12)
            if not history:
                return
            self.transcript_write("[dim]--- history ---[/dim]")
            for msg in history:
                role = msg.get("role", "")
                content = str(msg.get("content", ""))[:400]
                if role == "user":
                    self.transcript_write(
                        f"\n[bold]❯[/bold] {content}\n",
                        store_kind="user",
                        store_plain=content,
                    )
                elif role == "assistant":
                    self.transcript_write(
                        f"\n{content}\n",
                        store_kind="assistant",
                        store_plain=content,
                        store_markdown=content,
                    )
            self.transcript_write("[dim]--- end history ---[/dim]\n")
        except Exception:
            pass

    def _on_agent_event(self, event: AgentEvent) -> None:
        self._event_handler.handle(event)

    async def _run_agent_task(self, user_input: str) -> None:
        if not self.agent:
            return
        mode = self._execution_modes[self._execution_mode_index]
        try:
            await self.agent.run(
                user_input=user_input,
                conversation_id=self.conversation_id,
                execution_mode=mode,
            )
        except Exception as exc:
            self.transcript_write(f"[red]agent error: {exc}[/red]")
            self.set_status_line("error")
            self._restore_prompt_focus()

    async def _run_agent_streaming(self, user_input: str) -> None:
        if not self.agent:
            return
        mode = self._execution_modes[self._execution_mode_index]
        try:
            from core.runtime.executor import run_holix

            async for event in run_holix(
                self.agent,
                user_input,
                self.conversation_id,
                stream=True,
                execution_mode=mode,
            ):
                self.agent.emit(event)
        except Exception as exc:
            self.transcript_write(f"[red]stream error: {exc}[/red]")
            self.set_status_line("error")
            self._restore_prompt_focus()

    # --- Input / send ---

    def action_send_message(self) -> None:
        try:
            prompt = self.query_one("#input-area", CodePrompt)
            message = prompt.text.strip()
            if not message:
                return
            prompt.clear()
            self._tab_matches = []
            self._hide_slash_suggestions()
            self.run_worker(self._send_message(message))
            self._restore_prompt_focus(delay=0.05)
        except Exception:
            pass

    async def _send_message(self, message: str) -> None:
        if self._modals.plan_review.is_awaiting:
            self.transcript_write(f"\n[bold]❯[/bold] {message}\n")
            self._modals.plan_review.handle_text_response(message)
            return

        if self.agent and not message.strip().startswith("/"):
            from core.subagents.interaction import try_route_subagent_reply

            handled, feedback = try_route_subagent_reply(self.agent, message)
            if handled:
                self.transcript_write(f"\n[bold]❯[/bold] {message}\n")
                if feedback:
                    self.transcript_write(f"[dim]{feedback}[/dim]")
                return

        message = normalize_slash_input(message)
        if is_slash_command(message):
            await self._slash.handle(message)
            return

        self._last_user_message = message
        self.transcript_write(
            f"\n[bold]❯[/bold] {message}\n",
            store_kind="user",
            store_plain=message,
        )
        self._auto_scroll = True
        self.transcript_scroll_bottom()

        if not self.agent:
            from core.models.profile_cleanup import MISSING_LLM_HINT

            self.transcript_write(f"[red]{MISSING_LLM_HINT}[/red]")
            return

        self.set_status_line("thinking…")
        self._first_delta_seen = False
        self._is_streaming = self.streaming_enabled

        if self.streaming_enabled:
            self.run_worker(self._run_agent_streaming(message), name="agent-stream", exclusive=True)
        else:
            self.run_worker(self._run_agent_task(message), name="agent-run", exclusive=True)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "input-area":
            self._update_slash_suggestions(event.text_area.text)

    def on_text_area_key(self, event: events.Key) -> None:
        if event.key != "enter":
            return
        event.prevent_default()
        event.stop()
        if event.shift:
            try:
                self.query_one("#input-area", CodePrompt).insert("\n")
            except Exception:
                pass
            return
        try:
            suggestions = self.query_one("#command-suggestions", SlashCommandSuggestions)
            if suggestions.is_open and (
                self._slash_suggestion_navigated
                and suggestions.highlighted_child is not None
            ):
                self._insert_selected_slash_command()
                return
            if suggestions.is_open:
                self._hide_slash_suggestions()
        except Exception:
            pass
        self.action_send_message()

    def on_key(self, event: events.Key) -> None:
        if getattr(self.focused, "id", None) != "input-area":
            return

        try:
            suggestions = self.query_one("#command-suggestions", SlashCommandSuggestions)
            if suggestions.is_open:
                if event.key == "up":
                    suggestions.action_cursor_up()
                    self._slash_suggestion_navigated = True
                    event.prevent_default()
                    event.stop()
                    return
                if event.key == "down":
                    suggestions.action_cursor_down()
                    self._slash_suggestion_navigated = True
                    event.prevent_default()
                    event.stop()
                    return
                if event.key == "escape":
                    self._hide_slash_suggestions()
                    event.prevent_default()
                    event.stop()
                    return
        except Exception:
            pass

        if event.key == "tab":
            self._tab_complete_slash()
            event.prevent_default()
            event.stop()

    def _slash_commands_pool(self) -> list[tuple[str, str]]:
        from cli.shared.commands.registry import all_slash_commands

        if self.config and getattr(self.config, "skills_dir", None):
            slot = "main"
            if self.agent and hasattr(self.agent, "agent_slot"):
                slot = self.agent.agent_slot
            assigns = getattr(self.config, "skill_assignments", None)
            return all_slash_commands(
                Path(self.config.skills_dir),
                agent_slot=slot,
                skill_assignments=assigns,
            )
        from cli.tui.code.handlers.slash import SLASH_COMMANDS

        return SLASH_COMMANDS

    def _update_slash_suggestions(self, text: str) -> None:
        try:
            suggestions = self.query_one("#command-suggestions", SlashCommandSuggestions)
            lines = text.splitlines()
            current_line = lines[-1] if lines else ""
            matches = match_slash_commands(current_line, self._slash_commands_pool())
            if not matches:
                self._hide_slash_suggestions()
                return
            suggestions.set_matches(matches)
            suggestions.show_dropdown()
            self._slash_suggestion_navigated = False
        except Exception:
            pass

    def _hide_slash_suggestions(self) -> None:
        try:
            self.query_one("#command-suggestions", SlashCommandSuggestions).hide_dropdown()
            self._slash_suggestion_navigated = False
        except Exception:
            pass

    def _insert_selected_slash_command(self) -> None:
        try:
            suggestions = self.query_one("#command-suggestions", SlashCommandSuggestions)
            if not suggestions.is_open or not suggestions.matches:
                return

            highlighted = suggestions.highlighted_child
            if highlighted is not None:
                index = suggestions.children.index(highlighted)
                cmd = suggestions.matches[index][0]
            else:
                cmd = suggestions.matches[0][0]

            prompt = self.query_one("#input-area", CodePrompt)
            lines = prompt.text.splitlines()
            if lines:
                lines[-1] = cmd + " "
                prompt.text = "\n".join(lines)
            else:
                prompt.text = cmd + " "
            row = len(prompt.text.splitlines()) - 1
            prompt.cursor_location = (row, len(cmd) + 1)
            self._hide_slash_suggestions()
            prompt.focus()
        except Exception:
            pass

    def _tab_complete_slash(self) -> None:
        try:
            prompt = self.query_one("#input-area", CodePrompt)
            line = prompt.text.splitlines()[-1] if prompt.text else ""
            prefix = slash_command_prefix(line)
            if not prefix:
                return
            from cli.tui.shared.slash_suggestions import match_slash_commands as _match

            line = prompt.text.splitlines()[-1] if prompt.text else ""
            pool = self._slash_commands_pool()
            matches = [c for c, _ in _match(line, commands=pool, limit=20)]
            if not matches:
                matches = [c for c, _ in pool if c.startswith(prefix)]
            if not matches:
                return
            if self._tab_matches != matches:
                self._tab_matches = matches
                self._tab_index = 0
            else:
                self._tab_index = (self._tab_index + 1) % len(matches)
            prefix = "\n".join(prompt.text.splitlines()[:-1])
            new_line = matches[self._tab_index] + " "
            prompt.text = (prefix + "\n" + new_line).strip() if prefix else new_line
        except Exception:
            pass

    # --- Actions ---

    def _copy_selection_only(self) -> bool:
        """Copy current screen selection; return True if anything was copied."""
        try:
            selected = self.screen.get_selected_text()
            if selected and selected.strip():
                copy_text_best_effort(self, selected.strip())
                self._clipboard_notify("copied")
                self.screen.clear_selection()
                hide_copy_bar(self)
                return True
        except Exception:
            pass
        return False

    @on(TranscriptPanel.SelectionActive)
    def _on_transcript_selection_active(self) -> None:
        show_copy_bar(self)

    @on(TranscriptPanel.SelectionCleared)
    def _on_transcript_selection_cleared(self) -> None:
        hide_copy_bar(self)

    @on(TextArea.SelectionChanged, "#input-area")
    def _on_prompt_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        if event.text_area.selected_text.strip():
            show_copy_bar(self)
        else:
            hide_copy_bar(self)

    @on(CopySelectionBar.Pressed, f"#{COPY_BAR_ID}")
    def _on_copy_selection_bar_pressed(self) -> None:
        if not self._copy_selection_only():
            self._clipboard_notify("select text in chat, or F2 /open for full transcript")

    def action_clear_chat(self) -> None:
        try:
            hide_copy_bar(self)
            self.query_one("#transcript", CodeTranscript).clear()
            self._transcript_store.clear()
            self._last_assistant_plain = None
            self._recent_tool_results.clear()
            self._active_tools.clear()
            self._stream_buffer = ""
            self.transcript_write("[dim]cleared[/dim]\n")
            self._auto_scroll = True
            self._restore_prompt_focus()
        except Exception:
            pass

    def get_key_display(self, binding: Binding) -> str:
        if not is_macos():
            return super().get_key_display(binding)
        if binding.key_display:
            return binding.key_display
        return shortcut_label(binding.key)

    def action_help(self) -> None:
        from core.i18n import LocaleStore, t

        lang = LocaleStore(self.profile).get()
        clr = shortcut_label("ctrl+l")
        end = shortcut_label("ctrl+end")
        copy_k = primary_copy_shortcut_label()
        quit_k = shortcut_label("ctrl+q") if is_macos() else shortcut_label("ctrl+c")
        lines = [
            f"[bold]{t('tui.help.title', lang)}[/bold]",
            t("tui.help.keys1", lang),
            t("tui.help.keys2", lang, quit=quit_k, clear=clr, end=end),
            t("tui.help.keys3", lang, copy=copy_k),
            t("tui.help.keys4", lang),
        ]
        if is_macos():
            lines.extend(
                [
                    t("tui.help.macos_scroll", lang),
                    t("tui.help.macos_ru_kb", lang),
                ]
            )
        lines.extend(["", t("tui.help.slash", lang)])
        self.transcript_write("\n".join(lines) + "\n")

    def _transcript_scroll(self, *, lines: int = 0, page: bool = False, home: bool = False) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            if home:
                log.scroll_home(animate=False)
            elif page:
                log.scroll_page_up() if lines < 0 else log.scroll_page_down()
            elif lines:
                if lines < 0:
                    log.scroll_up()
                else:
                    log.scroll_down()
            self._auto_scroll = False
            self._update_scroll_hint()
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        self._transcript_scroll(lines=-1)

    def action_scroll_down(self) -> None:
        self._transcript_scroll(lines=1)

    def action_scroll_page_up(self) -> None:
        self._transcript_scroll(page=True, lines=-1)

    def action_scroll_page_down(self) -> None:
        self._transcript_scroll(page=True, lines=1)

    def action_scroll_top(self) -> None:
        self._transcript_scroll(home=True)

    def action_scroll_half_up(self) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            log.scroll_relative(y=-15)
            self._auto_scroll = False
            self._update_scroll_hint()
        except Exception:
            pass

    def action_scroll_half_down(self) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            log.scroll_relative(y=15)
            self._update_scroll_hint()
        except Exception:
            pass

    def _is_transcript_focused(self) -> bool:
        try:
            return getattr(self.focused, "id", None) == "transcript"
        except Exception:
            return False

    def action_focus_transcript(self) -> None:
        try:
            self.query_one("#transcript", CodeTranscript).focus()
        except Exception:
            pass

    def _clipboard_notify(self, message: str) -> None:
        self.transcript_write(f"[dim]{message}[/dim]")

    def action_copy_output(self) -> None:
        """Copy Textual selection, else last assistant, else last tool."""
        try:
            selected = self.screen.get_selected_text()
            if selected and selected.strip():
                copy_text_best_effort(self, selected.strip())
                self._clipboard_notify("selection copied")
                return
        except Exception:
            pass

        text = self._transcript_store.last_assistant()
        if text:
            copy_text_best_effort(self, text)
            self._clipboard_notify("last assistant response copied")
            return

        tool = self._transcript_store.last_tool()
        if tool:
            copy_text_best_effort(self, tool)
            self._clipboard_notify("last tool output copied")
            return

        if self._recent_tool_results:
            copy_text_best_effort(self, self._recent_tool_results[-1]["full_result"])
            self._clipboard_notify("last tool output copied")
            return

        self._clipboard_notify("nothing to copy — try /open or /copy all")

    def action_open_transcript(self) -> None:
        body = self._transcript_store.format_all()
        if not body.strip():
            self._clipboard_notify("transcript empty")
            return
        self.push_screen(TranscriptViewerScreen(body, title="Holix transcript"))

    def copy_text(self, text: str, *, label: str = "copied") -> None:
        if not text or not text.strip():
            self._clipboard_notify("nothing to copy")
            return
        if copy_text_best_effort(self, text):
            self._clipboard_notify(label)
        else:
            self.transcript_write("[red]clipboard failed[/red]")

    def action_scroll_bottom(self) -> None:
        self.transcript_scroll_bottom()

    async def action_cycle_execution_mode(self, just_set: bool = False) -> None:
        if not just_set:
            self._execution_mode_index = (self._execution_mode_index + 1) % len(self._execution_modes)
        mode = self._execution_modes[self._execution_mode_index]
        from config import settings

        settings.execution_mode = mode
        self.transcript_write(f"[dim]mode → {mode}[/dim]")
        self._save_ui_state()
        self._refresh_status_bar()

    def _action_stop_all(self) -> None:
        try:
            self.workers.cancel_all()
        except Exception:
            pass
        self._stream_buffer = ""
        self._is_streaming = False
        self.set_thinking(None)
        self.transcript_write("[dim]stopped[/dim]")
        self.set_status_line("ready")
        self._restore_prompt_focus()

    # --- Context ---

    def _update_context_bar_widget(
        self,
        percent: float | None,
        color: str | None,
        usage: dict[str, Any] | None,
    ) -> None:
        try:
            bar = self.query_one("#context-bar", CodeContextBar)
        except Exception:
            return
        try:
            if percent is None or color is None or usage is None:
                bar.set_placeholder()
                return
            bar.set_usage(percent, color, usage)
        except Exception:
            bar.set_placeholder()

    async def _update_context_display_async(self) -> None:
        try:
            agent = self.agent
            if not agent or not getattr(agent, "context_manager", None):
                self._cached_context_display = None
                self._update_context_bar_widget(None, None, None)
                self._refresh_status_bar()
                return

            try:
                messages = await agent.memory.get_conversation(
                    self.conversation_id, limit=200
                )
            except Exception:
                messages = []

            from core.context.token_counter import TokenCounter

            color_map = {"green": "green", "yellow": "yellow", "red": "red"}

            if not messages:
                total = agent.context_manager.context_window
                total_str = TokenCounter.format_token_count(total)
                self._cached_context_display = f"[green]0/{total_str}[/green]"
                self._update_context_bar_widget(
                    0.0, "green", {"used": 0, "total": total, "percent": 0.0}
                )
            else:
                usage = agent.context_manager.get_usage(messages)
                level = agent.context_manager.get_usage_level(messages)
                color = color_map.get(level, "white")
                used_str = TokenCounter.format_token_count(usage["used"])
                total_str = TokenCounter.format_token_count(usage["total"])
                self._cached_context_display = (
                    f"[{color}]{used_str}/{total_str}[/{color}]"
                )
                self._update_context_bar_widget(usage["percent"], color, usage)

            self._refresh_status_bar()
        except Exception:
            self._cached_context_display = None
            self._update_context_bar_widget(None, None, None)
            self._refresh_status_bar()

    # --- Tools memory ---

    def _store_tool_result(self, name: str, full: str, duration_s: float | None) -> None:
        entry = {"name": name, "full_result": full}
        if duration_s is not None:
            entry["duration_ms"] = duration_s * 1000
        self._recent_tool_results.append(entry)
        if len(self._recent_tool_results) > 20:
            self._recent_tool_results.pop(0)

    def _show_full_tool_result(self, index_from_end: int = 0) -> None:
        if not self._recent_tool_results:
            self.transcript_write("[yellow]no tool results yet[/yellow]")
            return
        try:
            entry = self._recent_tool_results[-(index_from_end + 1)]
            full = entry["full_result"]
            name = entry["name"]
            display = full
            if full.strip().startswith(("{", "[")):
                try:
                    display = Syntax(
                        json.dumps(json.loads(full), indent=2, ensure_ascii=False),
                        "json",
                        word_wrap=True,
                    )
                except Exception:
                    pass
            self.transcript_write(Panel(display, title=name, border_style="dim"))
        except IndexError:
            self.transcript_write("[red]invalid index — /tools[/red]")

    def _list_recent_tools(self) -> None:
        if not self._recent_tool_results:
            self.transcript_write("[dim]no tools yet[/dim]")
            return
        for i, e in enumerate(self._recent_tool_results, 1):
            preview = (e["full_result"] or "").split("\n")[0][:60]
            self.transcript_write(f"  {i}. {e['name']} — {preview}")

    async def _mcp_list(self) -> None:
        try:
            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
            if not servers:
                self.transcript_write("[dim]No MCP servers. Use terminal: holix mcp install[/dim]")
                return
            lines = ["MCP servers:"]
            for name, data in servers.items():
                src = data.get("_source", "manual")
                lines.append(f"  • {name} ({data.get('transport','stdio')}) [{src}]")
            self.transcript_write("\n".join(lines))
        except Exception as e:
            self.transcript_write(f"[red]MCP list error: {e}[/red]")

    async def _mcp_install(self, what: str = "") -> None:
        if not what:
            self.transcript_write("Usage: /mcp install <key|git-url>\nKeys: compass, context7, filesystem, github...\nOr use terminal `holix mcp install` for full interactive.")
            return
        self.transcript_write(f"[dim]Installing '{what}'... (using core logic)[/dim]")
        try:
            from core.mcp.installer import build_config_from_popular, install_from_git
            from core.mcp.popular import get_popular_by_key

            from cli.core import get_profile_manager

            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)

            if what.startswith(("http", "git@")):
                data = install_from_git(what)
                name = what.rstrip("/").split("/")[-1].removesuffix(".git")
                data["_source"] = "git"
                servers = dict(getattr(cfg, "mcp_servers", {}) or {})
                servers[name] = data
                cfg.mcp_servers = servers
                # Auto-assign
                assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
                if "main" not in assigns:
                    assigns["main"] = []
                if name not in assigns["main"]:
                    assigns["main"].append(name)
                cfg.mcp_assignments = assigns
                manager.save_profile(self.profile, cfg)
                self.transcript_write(f"Installed from git as {name} (auto to main). Use /mcp list.")
                # Hot reload
                if getattr(self, "agent", None):
                    try:
                        fresh_servers = getattr(cfg, "mcp_servers", {}) or {}
                        fresh_assign = getattr(cfg, "mcp_assignments", {}) or {}
                        await self.agent.reload_mcp(fresh_servers, fresh_assign)
                    except Exception as e:
                        self.transcript_write(f"[dim]Hot-reload note: {e}[/dim]")
                # Show active
                if getattr(self, "agent", None) and hasattr(self.agent, "tools"):
                    mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                    if mcp_ts:
                        self.transcript_write(f"[dim]MCP tools now active ({len(mcp_ts)}): use /mcp tools[/dim]")
                return

            pop = get_popular_by_key(what)
            if not pop:
                self.transcript_write(f"Unknown key '{what}'. See terminal `holix mcp list-popular`.")
                return

            data = build_config_from_popular(pop, {})
            if pop.env:
                data["env"] = dict(pop.env)
            data["_source"] = "popular"

            servers = dict(getattr(cfg, "mcp_servers", {}) or {})
            servers[what] = data
            cfg.mcp_servers = servers
            # Auto-assign new server to "main" for hot visibility
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            if "main" not in assigns:
                assigns["main"] = []
            if what not in assigns["main"]:
                assigns["main"].append(what)
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            self.transcript_write(f"Added popular MCP '{what}' (auto-assigned to main). Use /mcp list or /mcp tools.")
            # Hot-reload into live agent
            if getattr(self, "agent", None):
                try:
                    fresh_servers = getattr(cfg, "mcp_servers", {}) or {}
                    fresh_assign = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh_servers, fresh_assign)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot-reload note: {e}[/dim]")
            # Show active
            if getattr(self, "agent", None) and hasattr(self.agent, "tools"):
                mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                if mcp_ts:
                    self.transcript_write(f"[dim]MCP tools now active ({len(mcp_ts)}): use /mcp tools[/dim]")
        except Exception as e:
            self.transcript_write(f"Install error: {e}. Fall back to terminal: holix mcp install {what}")

    async def _mcp_assign(self, rest: str = "") -> None:
        if not rest:
            self.transcript_write("Usage: /mcp assign <server> <roles...>\nExample: /mcp assign context7 main")
            return
        try:
            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            parts = rest.split(None, 1)
            if len(parts) < 2:
                self.transcript_write("Need server and roles")
                return
            srv, roles_str = parts
            roles = [r.strip() for r in roles_str.replace(",", " ").split() if r.strip()]
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            assigns[srv] = roles
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            self.transcript_write(f"Assigned {srv} → {roles}")
            if getattr(self, "agent", None):
                try:
                    fresh_servers = getattr(cfg, "mcp_servers", {}) or {}
                    fresh_assign = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh_servers, fresh_assign)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot-reload note: {e}[/dim]")
        except Exception as e:
            self.transcript_write(f"Assign error: {e}")

    async def _mcp_test(self, name: str = "") -> None:
        if not name:
            self.transcript_write("Usage: /mcp test <name>")
            return
        self.transcript_write(f"[dim]Testing {name}...[/dim]")
        try:
            from core.mcp.manager import MCPManager

            from cli.core import get_profile_manager
            manager = get_profile_manager()
            cfg = manager.load_profile(self.profile)
            servers = getattr(cfg, "mcp_servers", {}) or {}
            if name not in servers:
                self.transcript_write(f"Server {name} not configured.")
                return
            m = MCPManager({name: servers[name]})
            await m.connect_all()
            try:
                await m.wait_ready([name], timeout=12.0)
            except Exception:
                pass
            tools = m.get_tool_adapters([name])
            await m.disconnect_all()
            self.transcript_write(f"Test {name}: {len(tools)} tools. {[tt.name for tt in tools][:4]}")
            if not tools:
                errs = getattr(m, "_last_errors", {})
                if name in errs:
                    self.transcript_write(f"[red]Error: {errs[name]}[/red]")
        except Exception as e:
            self.transcript_write(f"Test error: {e}")

    async def _mcp_list_tools(self) -> None:
        try:
            if not self.agent or not hasattr(self.agent, "tools"):
                self.transcript_write("[dim]Agent not ready[/dim]")
                return
            mcp_tools = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
            if mcp_tools:
                self.transcript_write("MCP tools available:\n" + "\n".join(f"  • {t}" for t in mcp_tools))
            else:
                self.transcript_write("[dim]No MCP tools registered (use /mcp assign)[/dim]")
        except Exception as e:
            self.transcript_write(f"Error: {e}")

    async def _mcp_remove(self, name: str = "") -> None:
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
            # also clean assignments
            assigns = dict(getattr(cfg, "mcp_assignments", {}) or {})
            for k, lst in list(assigns.items()):
                if name in lst:
                    assigns[k] = [x for x in lst if x != name]
            cfg.mcp_servers = servers
            cfg.mcp_assignments = assigns
            manager.save_profile(self.profile, cfg)
            self.transcript_write(f"Removed MCP server '{name}'.")
            # Hot-reload (remove tools from live agent)
            if getattr(self, "agent", None):
                try:
                    fresh_servers = getattr(cfg, "mcp_servers", {}) or {}
                    fresh_assign = getattr(cfg, "mcp_assignments", {}) or {}
                    await self.agent.reload_mcp(fresh_servers, fresh_assign)
                except Exception as e:
                    self.transcript_write(f"[dim]Hot-reload note: {e}[/dim]")
            # Show remaining
            if getattr(self, "agent", None) and hasattr(self.agent, "tools"):
                mcp_ts = [n for n in self.agent.tools.get_tool_names() if str(n).startswith("mcp_")]
                self.transcript_write(f"[dim]MCP tools now: {len(mcp_ts)} ( /mcp tools )[/dim]")
        except Exception as e:
            self.transcript_write(f"Remove error: {e}")

    async def _search_memory(self, query: str) -> None:
        if not self.agent:
            return
        self.transcript_write(f"[dim]memory: {query}[/dim]")
        try:
            results = await self.agent.search_memory(query, top_k=6)
            if not results:
                self.transcript_write("[dim]no hits[/dim]")
                return
            text = self.agent.format_memory_results(
                results,
                conversation_id=self.conversation_id,
                include_current=True,
            )
            for line in text.split("\n"):
                if line.strip():
                    self.transcript_write(f"  {line}")
        except Exception as e:
            self.transcript_write(f"[red]{e}[/red]")

    # --- Sessions ---

    async def _load_known_sessions(self) -> None:
        if not self.agent:
            return
        try:
            self.known_sessions = await self.agent.list_conversations(limit=12)
        except Exception:
            self.known_sessions = []

    async def _show_sessions_list(self) -> None:
        await self._load_known_sessions()
        if not self.known_sessions:
            self.transcript_write("[dim]no sessions[/dim]")
            return
        from core.cron.session_sync import cron_session_label

        for i, s in enumerate(self.known_sessions, 1):
            cid = s.get("conversation_id", "?")
            label = cron_session_label(cid)
            mark = " *" if cid == self.conversation_id else ""
            self.transcript_write(f"  {i}. {label}{mark}")
            if label != cid:
                self.transcript_write(f"      [dim]{cid}[/dim]")
        self.transcript_write("[dim]/switch N[/dim]")

    async def _create_new_session(self) -> None:
        new_id = f"tui_{self.profile}_{int(time.time())}"
        self.conversation_id = new_id
        self.session_display_name = self._short_name(new_id)
        self._recent_tool_results.clear()
        self._active_tools.clear()
        self._transcript_store.clear()
        self._last_assistant_plain = None
        self.transcript_write(f"\n[bold]session {self.session_display_name}[/bold]\n")
        self._save_ui_state()
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self.transcript_write(f"[dim]model (session): {restored}[/dim]\n")
        await self._load_known_sessions()
        await self._update_context_display_async()
        self._restore_prompt_focus(force=True)

    async def _switch_to_session(self, index: int) -> None:
        if not self.known_sessions or index < 1 or index > len(self.known_sessions):
            self.transcript_write("[yellow]invalid session[/yellow]")
            return
        new_id = self.known_sessions[index - 1]["conversation_id"]
        if new_id == self.conversation_id:
            return
        self.conversation_id = new_id
        self.session_display_name = self._short_name(new_id)
        self.query_one("#transcript", CodeTranscript).clear()
        self._transcript_store.clear()
        self._last_assistant_plain = None
        self._recent_tool_results.clear()
        self.transcript_write(f"[dim]switched → {new_id}[/dim]\n")
        await self._load_conversation_history()
        await self._ensure_session_context()
        self._save_ui_state()
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self.transcript_write(f"[dim]model (session): {restored}[/dim]\n")
        await self._update_context_display_async()
        self._restore_prompt_focus(force=True)

    def _short_name(self, conv_id: str) -> str:
        if conv_id in self.session_names:
            return self.session_names[conv_id]
        if "_" in conv_id:
            return conv_id.split("_")[-1][:8]
        return conv_id[:10]

    def _rename_current_session(self, name: str) -> None:
        self.session_names[self.conversation_id] = name.strip()
        self.session_display_name = name.strip()
        self.transcript_write(f"[dim]session name: {name.strip()}[/dim]")
        self._refresh_status_bar()

    # --- Profiles ---

    def _get_available_profiles(self) -> list[str]:
        try:
            return self.profile_manager.list_profiles()
        except Exception:
            return ["default"]

    async def _switch_profile(self, new_profile: str, *, profile_key: str | None = None) -> None:
        from core.profile_keys import ProfileKeyError, profile_has_access_key

        if new_profile == self.profile:
            self.transcript_write(f"[dim]already on {new_profile}[/dim]")
            return
        self.transcript_write(f"[dim]profile → {new_profile}[/dim]")
        try:
            new_config = init_profile(new_profile, profile_key=profile_key, prompt_key=False)
            from core.di import resolve_runtime_config

            runtime_config = resolve_runtime_config(new_config)
            try:
                from core.models.manager import ModelManager

                mc = ModelManager(new_config).get_default_model_config()
                if mc:
                    runtime_config = runtime_config.with_overrides(
                        model=mc.model,
                        base_url=mc.base_url,
                        api_key=mc.api_key,
                        temperature=mc.temperature,
                    )
                    self._resolved_model = mc.model
            except Exception:
                pass

            new_agent = HolixAgent(config=runtime_config)
            await new_agent.initialize()
            self.agent = new_agent
            self.profile = new_profile
            self.config = new_config
            self.agent.events.subscribe(self._on_agent_event)
            await self._create_new_session()
            self.transcript_write(f"[dim]profile {new_profile} active[/dim]")
        except ProfileKeyError as exc:
            self.transcript_write(f"[red]{exc}[/red]")
            if profile_has_access_key(new_profile) and not profile_key:
                self.transcript_write("[dim]/profile <name> <access-key>[/dim]")
        except Exception as e:
            self.transcript_write(f"[red]{e}[/red]")

    # --- Confirmations / plan review ---

    def _handle_confirmation_request(self, event: ConfirmationRequestEvent) -> None:
        self._modals.confirmation.show(event)

    def _resolve_confirmation(self, choice: ConfirmationChoice) -> None:
        self._modals.confirmation.resolve(choice)

    def _handle_plan_review_request(self, event: PlanReviewRequestEvent) -> None:
        self._modals.plan_review.show(event)

    def _resolve_plan_review(self, choice, feedback: str = "") -> None:
        self._modals.plan_review.resolve(choice, feedback)

    # --- Scroll / focus ---

    def _update_scroll_hint(self) -> None:
        try:
            log = self.query_one("#transcript", CodeTranscript)
            hint = self.query_one("#scroll-hint", Static)
            at_bottom = log.scroll_offset.y >= max(0, log.virtual_size.height - log.size.height - 2)
            if at_bottom:
                hint.remove_class("visible")
                self._auto_scroll = True
            else:
                hint.update("↓ new messages — Ctrl+End")
                hint.add_class("visible")
                self._auto_scroll = False
        except Exception:
            pass

    def _restore_prompt_focus(self, delay: float = 0.04, *, force: bool = False) -> None:
        if not force and self._is_transcript_focused():
            return

        def _focus():
            try:
                self.query_one("#input-area", CodePrompt).focus()
            except Exception:
                pass

        if delay > 0:
            self.set_timer(delay, _focus)
        else:
            _focus()

    def on_mouse_scroll_down(self, event) -> None:
        try:
            self.query_one("#transcript", CodeTranscript).scroll_down()
            self._update_scroll_hint()
        except Exception:
            pass

    def on_mouse_scroll_up(self, event) -> None:
        try:
            self.query_one("#transcript", CodeTranscript).scroll_up()
            self._update_scroll_hint()
        except Exception:
            pass


def run_tui(profile: str = "default") -> None:
    """Launch strict code-style TUI (default for holix tui)."""
    import os

    if os.environ.get("HOLIX_TUI_LEGACY", "").strip() in ("1", "true", "yes"):
        from cli.tui.legacy.app import run_tui_legacy

        run_tui_legacy(profile=profile)
        return

    config = init_profile(profile)
    HolixCodeApp(profile=profile, config=config).run()


if __name__ == "__main__":
    run_tui()