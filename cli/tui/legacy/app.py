"""
Minimal Textual TUI for Holix (Phase 1 PoC + Phase 2 polish)

Command: holix tui

Essential widgets:
- Header + status
- RichLog (chat history with streaming, tool panels, Markdown)
- TextArea (multiline input with Shift+Enter support)
- Sidebar with Collapsible sections (Tools, Memory, Sessions, Skills, Profiles)
- Command Palette (Ctrl+P) with categories + dynamic contextual actions
- Density modes + persistence (~/.holix/tui-state.json)

Keyboard-first, macOS-friendly scroll/focus, full power-user features via / and Ctrl+P.
Integrates with HolixAgent + AgentEvent system (single source of truth in core/agent_execution.py).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC
from pathlib import Path
from typing import Any

from cli.core import HOLIX_HOME, ProfileConfig, ProfileManager, init_profile
from cli.tui.legacy.handlers import AgentEventHandler, SlashCommandHandler
from cli.tui.legacy.widgets import HOLIX_TUI_CSS, HolixChatLog, HolixMainContent, HolixSidebar
from cli.tui.modals import ModalStack
from core.agent import HolixAgent
from core.agent_events import AgentEvent
from core.plan_review.review_events import PlanReviewRequestEvent
from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent
from rich.panel import Panel
from rich.syntax import Syntax
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Command as PaletteCommandOption
from textual.command import (
    CommandInput,  # for UX polish in palette highlight
    CommandPalette,
    Hit,
    Hits,
    Provider,
)
from textual.message import Message
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    OptionList,
    RichLog,
    Static,
    TextArea,
)


class ExecutePaletteCommand(Message):
    """Posted by palette callbacks so execution happens cleanly after the palette is dismissed,
    making both mouse and Enter work reliably regardless of Textual version internals.
    """
    def __init__(self, command: Callable[[], None]) -> None:
        self.command = command
        super().__init__()


class HolixCommandProvider(Provider):
    """Provides commands for the Holix TUI command palette (Phase 2).

    Commands are organized into logical categories using ▸ prefixes for easy
    discovery (Session, Memory, Tools, Profile, Navigation, Customize, System).

    Also includes many dynamic contextual hits that appear based on current
    session state (recent memories, tool results, sessions, skills, profiles).
    """

    def __init__(self, screen, match_style) -> None:
        # Textual's CommandPalette instantiates providers as:
        #   ProviderClass(screen, match_style)
        # We must match this signature.
        super().__init__(screen, match_style)

    @property
    def app(self) -> HolixTUI:
        """Convenience property so the rest of the provider can keep using self.app."""
        return self.screen.app  # type: ignore[attr-defined]

    # Mapping from simple action id -> method name on the app (used for reliable palette commands)
    _PALETTE_ACTION_MAP: dict[str, str] = {
        "new_session": "action_new_session",
        "list_sessions": "action_show_sessions",
        "search_memory": "action_search_memory",
        "clear_memory_search": "action_clear_memory_search",
        "insert_last_memory": "action_insert_last_memory",
        "rerun_last_tool": "action_rerun_last_tool",
        "show_last_tool_result": "action_show_last_tool_result",
        "list_recent_tools": "_list_recent_tools",
        "browse_skills": "action_show_skills",
        "switch_profile": "action_switch_profile",
        "toggle_sidebar": "action_toggle_sidebar",
        "jump_to_bottom": "action_jump_to_bottom",
        "density_compact": "action_set_density_compact",
        "density_normal": "action_set_density_normal",
        "density_comfort": "action_set_density_comfort",
        "reset_ui": "action_reset_ui_state",
        "clear_chat": "action_clear_chat",
        "show_metrics": "action_show_metrics",
        "toggle_streaming": "action_toggle_streaming",
        "help": "action_help",
        "copy_last_assistant": "action_copy_last_assistant",
        "copy_last_tool": "action_copy_last_tool_result",
        "insert_last_assistant": "action_insert_last_assistant",
        "show_session_info": "action_show_session_info",
        "regenerate_last": "action_regenerate_last_response",
        "edit_last_message": "action_edit_last_message",
        "debug_show_context": "action_debug_show_context",
        "debug_show_tools": "action_debug_show_tools",
        "debug_show_skills": "action_debug_show_skills",
    }

    def _wrap_callback(self, func):
        """Minimal wrapper for direct call path (mouse click in current Textual).

        For keyboard Enter we no longer rely on this being called.
        We primarily drive execution from OptionHighlighted + Closed.
        """
        app = self.app

        def _safe() -> None:
            try:
                app._append_to_log("[dim]→ Direct command path (usually mouse)[/dim]")
            except Exception:
                pass
            try:
                if callable(func):
                    func()
            except Exception as e:
                try:
                    app._append_to_log(f"[red]Palette direct error: {e}[/red]")
                except Exception:
                    pass

        return _safe

    async def search(self, query: str) -> Hits:
        """Return matching commands."""
        matcher = self.matcher(query)

        # Static commands - using direct bound methods + wrapper (this version at least made mouse work before)
        commands = [
            # Session management
            ("Session ▸ New Session", self.app.action_new_session, "Start a completely fresh conversation"),
            ("Session ▸ List Sessions", self.app.action_show_sessions, "Show all recent sessions"),

            # Context & Memory
            ("Memory ▸ Search Memory", self.app.action_search_memory, "Semantic search in long-term memory"),
            ("Memory ▸ Clear Search Results", self.app.action_clear_memory_search, "Return Memory sidebar from search results back to recent messages"),
            ("Memory ▸ Insert Last Memory", self.app.action_insert_last_memory, "Insert most recent memory entry as context"),

            # Tools & Skills
            ("Tools ▸ Re-run Last Tool", self.app.action_rerun_last_tool, "Repeat the last tool call with the same arguments"),
            ("Tools ▸ Show Last Tool Result", self.app.action_show_last_tool_result, "Display full output of the last tool call"),
            ("Tools ▸ Copy Last Tool Result", self.app.action_copy_last_tool_result, "Copy full last tool output to clipboard (works in most terminals)"),
            ("Tools ▸ List Recent Tools", self.app._list_recent_tools, "List recent tool calls with previews"),
            ("Tools ▸ Copy Last Assistant Response", self.app.action_copy_last_assistant, "Copy the most recent Holix reply to clipboard"),
            ("Context ▸ Insert Last Assistant Response", self.app.action_insert_last_assistant, "Insert the last Holix reply into input as context (great for follow-ups)"),
            ("Skills ▸ Browse Skills", self.app.action_show_skills, "Show available agent skills"),

            # Profile & Navigation
            ("Profile ▸ Switch Profile", self.app.action_switch_profile, "Change active Holix profile"),
            ("Navigation ▸ Toggle Sidebar", self.app.action_toggle_sidebar, "Show or hide the sidebar"),
            ("Navigation ▸ Jump to Bottom", self.app.action_jump_to_bottom, "Scroll chat to bottom and re-enable auto-scroll"),

            # Customization
            ("Customize ▸ Density: Compact", self.app.action_set_density_compact, "Make interface more compact"),
            ("Customize ▸ Density: Normal", self.app.action_set_density_normal, "Default interface density"),
            ("Customize ▸ Density: Comfort", self.app.action_set_density_comfort, "More spacious interface"),
            ("Customize ▸ Reset UI Preferences", self.app.action_reset_ui_state, "Clear saved density, sidebar sections collapsed state, and sidebar open/closed"),

            # System
            ("System ▸ Clear Chat", self.app.action_clear_chat, "Clear the current chat log"),
            ("System ▸ Show Metrics", self.app.action_show_metrics, "Display agent metrics"),
            ("System ▸ Toggle Streaming", self.app.action_toggle_streaming, "Turn token streaming on/off"),
            ("System ▸ Help", self.app.action_help, "Show help and keybindings"),

            # Debug (light Phase 3 / B)
            ("Debug ▸ Show Conversation Context", self.app.action_debug_show_context, "View recent messages in current conversation"),
            ("Debug ▸ Show Loaded Tools", self.app.action_debug_show_tools, "List all registered tools with details"),
            ("Debug ▸ Show Loaded Skills", self.app.action_debug_show_skills, "List all available skills"),
            ("Navigation ▸ Focus Input", self.app.action_focus_input, "Move cursor back to the chat input field"),
            ("Navigation ▸ Scroll to Top", self.app.action_scroll_chat_top, "Jump to the very top of the chat history"),
            ("Session ▸ Rename Current Session", self.app.action_rename_current_session, "Give the current session a human name"),
            ("Session ▸ Show Current Info", self.app.action_show_session_info, "Quick stats for the active session (messages, tools)"),
            ("Session ▸ Regenerate Last Response", self.app.action_regenerate_last_response, "Re-run the agent on your last message (fresh answer)"),
            ("Session ▸ Edit Last Message", self.app.action_edit_last_message, "Load your last message into the input for editing and resending"),
            ("Tip: Type to filter results quickly", None, "Start typing to narrow down commands"),
        ]

        for name, callback, help_text in commands:
            if (match := matcher.match(name)) or (match := matcher.match(help_text)):
                safe_callback = self._wrap_callback(callback)
                yield Hit(
                    match,
                    name,
                    safe_callback,
                    text=name,
                    help=help_text,
                )

        # Phase 2 enhancement: dynamic hits from current session state (recent memories + tools)
        # These appear when user types something memory/tool related or the palette is opened.
        qlower = (query or "").lower()

        # Dynamic "Insert recent memory N" actions (from sidebar _recent_memories)
        memories = getattr(self.app, "_recent_memories", []) or []
        for i, mem in enumerate(memories[:3]):
            short = mem.get("short", "")[:28]
            role = mem.get("role", "?")
            label = f"Insert memory [{i+1}] ({role}): {short}"
            help_text = f"Insert recent memory #{i+1} as context (from current conversation)"
            # Yield if fuzzy matches the label/help or query hints at memory/insert/recent
            match = matcher.match(label) or matcher.match(help_text)
            if not match:
                if any(k in qlower for k in ("mem", "insert", "recent", "context")):
                    match = 65  # decent visible score for contextual actions
            if match:
                cb = self._wrap_callback(self._make_memory_insert_cb(i))
                yield Hit(match, label, cb, text=label, help=help_text)

        # Dynamic actions for recent tool results (last 3) — high value for follow-ups
        tools = getattr(self.app, "_recent_tool_results", None) or []
        for i in range(min(3, len(tools))):
            entry = tools[-(i+1)]
            short_name = entry.get("name", "tool")[:25]
            label = f"Insert tool result [{i+1}] as context: {short_name}"
            help_text = f"Insert result of recent tool call #{i+1} into the input"
            match = matcher.match(label) or matcher.match("tool") or matcher.match("insert")
            if not match:
                if any(k in qlower for k in ("tool", "insert", "context", "result", "last")):
                    match = 50 + (3 - i) * 5   # higher score for more recent
            if match:
                cb = self._wrap_callback(self._make_insert_tool_result_cb(i))
                yield Hit(match, label, cb, text=label, help=help_text)

        # Dynamic "Insert last assistant response as context" (pairs with the new copy action)
        if getattr(self.app, "_recent_memories", None):
            # Check if there's at least one assistant message
            has_assistant = any(m.get("role") == "assistant" for m in self.app._recent_memories)
            if has_assistant:
                label = "Insert last Holix response as context"
                help_text = "Insert the most recent assistant reply into the input for follow-up"
                match = matcher.match(label) or matcher.match("assistant") or matcher.match("holix")
                if not match and any(k in qlower for k in ("insert", "last", "context", "assistant", "holix", "response")):
                    match = 58
                if match:
                    cb = self._wrap_callback(self._make_insert_last_assistant_cb())
                    yield Hit(match, label, cb, text=label, help=help_text)

        # Dynamic "Regenerate last response" (high value power-user action)
        if getattr(self.app, "_last_user_message", None):
            label = "Regenerate last response"
            help_text = "Re-send your last message to get a new answer from the agent"
            match = matcher.match(label) or matcher.match("regen") or matcher.match("retry")
            if not match and any(k in qlower for k in ("regen", "retry", "again", "new answer", "try again")):
                match = 65
            if match:
                cb = self._wrap_callback(self._make_regenerate_cb())
                yield Hit(match, label, cb, text=label, help=help_text)

        # Dynamic "Edit last message" (pairs beautifully with Regenerate)
        if getattr(self.app, "_last_user_message", None):
            label = "Edit last message"
            help_text = "Load your previous message into the input field for easy editing and resend"
            match = matcher.match(label) or matcher.match("edit")
            if not match and any(k in qlower for k in ("edit", "modify", "change", "fix", "last message")):
                match = 60
            if match:
                cb = self._wrap_callback(self._make_edit_last_message_cb())
                yield Hit(match, label, cb, text=label, help=help_text)

        # Always offer quick session info (lightweight, useful)
        label = "Show current session info"
        help_text = "Quick stats: session name, recent messages, tool results"
        match = matcher.match(label) or matcher.match("session info") or matcher.match("stats")
        if not match and any(k in qlower for k in ("session", "info", "stats", "status")):
            match = 40
        if match:
            cb = self._wrap_callback(lambda: self.app.action_show_session_info())
            yield Hit(match, label, cb, text=label, help=help_text)

        # Smart "Recent power actions" section (appears for broad/recent queries)
        # This gives a "Recent" feel without full usage tracking
        if len(qlower) < 4 or "recent" in qlower or "last" in qlower:
            recent_actions = []

            if getattr(self.app, "_last_user_message", None):
                recent_actions.append((
                    "Edit last message",
                    "Load your last message for editing",
                    lambda: self.app.action_edit_last_message()
                ))
                recent_actions.append((
                    "Regenerate last response",
                    "Get a fresh answer for your last message",
                    lambda: self.app.action_regenerate_last_response()
                ))

            if getattr(self.app, "_recent_memories", None):
                has_assistant = any(m.get("role") == "assistant" for m in self.app._recent_memories)
                if has_assistant:
                    recent_actions.append((
                        "Insert last Holix response as context",
                        "Add previous assistant output into input",
                        lambda: self.app.action_insert_last_assistant()
                    ))

            for label, help_text, action in recent_actions[:3]:
                match = matcher.match(label) or (len(qlower) < 3)
                if match:
                    cb = self._wrap_callback(action)
                    yield Hit(70, label, cb, text=label, help=help_text)  # high base score for recent

        # Dynamic recent sessions quick-switch (Phase 2 power-user, mirrors memory hits)
        sessions = getattr(self.app, "known_sessions", []) or []
        current_cid = getattr(self.app, "conversation_id", None)
        for i, sess in enumerate(sessions[:5]):
            cid = sess.get("conversation_id", "")
            if cid == current_cid:
                continue  # don't offer "switch to current"
            count = sess.get("message_count", 0)
            short = self.app._get_short_session_name(cid) if hasattr(self.app, "_get_short_session_name") else cid[-8:]
            label = f"Switch to session: {short} ({count} msgs)"
            help_text = "Switch conversation context (loads history)"
            match = matcher.match(label) or matcher.match("session") or matcher.match("switch")
            if not match:
                if any(k in qlower for k in ("sess", "switch", "recent", "history")):
                    match = 60
            if match:
                cb = self._wrap_callback(self._make_session_switch_cb(i + 1))
                yield Hit(match, label, cb, text=label, help=help_text)

        # Dynamic Skills actions (Phase 2 completion – symmetric to Memory/Sessions/Tools)
        skills = getattr(self.app, "_available_skills", []) or []
        for i, sk in enumerate(skills[:6]):  # top skills
            name = sk.get("name", "skill")[:22]
            tags = sk.get("tags", []) or []
            tags_hint = f" [{', '.join(tags[:2])}]" if tags else ""
            label = f"Describe skill: {name}{tags_hint}"
            help_text = "Show full skill description in chat"
            match = matcher.match(label) or matcher.match("skill") or matcher.match("describe")
            if not match:
                if any(k in qlower for k in ("skill", "describe", "agent", "capability")):
                    match = 58
            if match:
                cb = self._wrap_callback(self._make_skill_describe_cb(i))
                yield Hit(match, label, cb, text=label, help=help_text)

            # Also offer quick-insert of the skill as context
            ins_label = f"Insert skill as context: {name}"
            ins_match = matcher.match(ins_label) or matcher.match("insert") and matcher.match("skill")
            if not ins_match and "skill" in qlower and "insert" in qlower:
                ins_match = 50
            if ins_match:
                cb = self._wrap_callback(self._make_skill_insert_cb(i))
                yield Hit(ins_match, ins_label, cb, text=ins_label, help="Insert this skill description into input as context")

        # Dynamic recent/recently-used profile switches (very high value — profile switch is 'heavy')
        profiles = getattr(self.app, "_available_profiles", []) or []
        current_profile = getattr(self.app, "profile", None)
        history = getattr(self.app, "profile_switch_history", []) or []
        recent_profiles = []
        for h in reversed(history):
            p = h.get("profile")
            if p and p != current_profile and p not in recent_profiles:
                recent_profiles.append(p)
        # Also include other available profiles not in recent history
        for p in profiles:
            if p != current_profile and p not in recent_profiles:
                recent_profiles.append(p)
        for i, prof in enumerate(recent_profiles[:4]):
            label = f"Switch to profile: {prof}"
            if i < len(history):
                label += " (recent)"
            help_text = "Start profile switch (requires /yes confirmation)"
            match = matcher.match(label) or matcher.match("profile") or matcher.match("switch")
            if not match:
                if "profile" in qlower or "switch" in qlower:
                    match = 55
            if match:
                cb = self._wrap_callback(self._make_profile_switch_cb(prof))
                yield Hit(match, label, cb, text=label, help=help_text)

    def _make_memory_insert_cb(self, idx: int):
        """Factory for zero-arg callbacks used by dynamic palette Hits."""
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic memory callback running[/dim]")
                self.app._insert_memory_from_sidebar(idx)
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_insert_last_tool_cb(self):
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic last-tool callback running[/dim]")
                self.app._insert_last_tool_result_as_context()
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_insert_tool_result_cb(self, idx_from_end: int):
        """Factory for inserting a specific recent tool result (0 = last, 1 = second last, etc.)."""
        def _cb() -> None:
            try:
                self.app._append_to_log(f"[dim]→ Dynamic insert tool result [{idx_from_end+1}] running[/dim]")
                self.app._insert_tool_result_as_context(idx_from_end)
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_rerun_tool_cb(self, idx_from_end: int):
        """Factory for re-running a specific recent tool call."""
        def _cb() -> None:
            try:
                self.app._append_to_log(f"[dim]→ Dynamic re-run tool [{idx_from_end+1}] running[/dim]")
                self.app._rerun_tool_by_index(idx_from_end)
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_insert_last_assistant_cb(self):
        """Factory for the dynamic 'Insert last Holix response' palette hit."""
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic last-assistant insert running[/dim]")
                self.app.action_insert_last_assistant()
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_regenerate_cb(self):
        """Factory for dynamic 'Regenerate last response' palette hit."""
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic regenerate callback running[/dim]")
                self.app.action_regenerate_last_response()
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_edit_last_message_cb(self):
        """Factory for dynamic 'Edit last message' palette hit."""
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic edit last message callback running[/dim]")
                self.app.action_edit_last_message()
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_session_switch_cb(self, one_based_idx: int):
        """Factory for session quick-switch callbacks from dynamic palette hits."""
        def _cb() -> None:
            try:
                self.app._append_to_log("[dim]→ Dynamic session switch callback running[/dim]")
                self.app._switch_to_session_by_index(one_based_idx)
            except Exception as e:
                try:
                    self.app._append_to_log(f"[red]Dynamic error: {e}[/red]")
                except Exception:
                    pass
        return _cb

    def _make_skill_describe_cb(self, idx: int):
        def _cb() -> None:
            try:
                sk = self.app._available_skills[idx]
                self.app._describe_skill(sk)
            except Exception:
                pass
        return _cb

    def _make_skill_insert_cb(self, idx: int):
        def _cb() -> None:
            try:
                sk = self.app._available_skills[idx]
                self.app._insert_skill_as_context(sk)
            except Exception:
                pass
        return _cb

    def _make_profile_switch_cb(self, profile_name: str):
        def _cb() -> None:
            try:
                self.app._initiate_profile_switch(profile_name)
            except Exception:
                pass
        return _cb


class HolixTUI(App):
    """Minimal Holix TUI application."""

    ENABLE_MOUSE_SUPPORT = True

    def on_mouse_scroll_up(self, event) -> None:
        """Forward mouse wheel up to the chat log (helps on some macOS terminals)."""
        try:
            chat_log = self._chat_log()
            chat_log.scroll_up()
            self._auto_scroll_chat = False
            self._update_scroll_indicator()
        except Exception:
            pass

    def on_mouse_scroll_down(self, event) -> None:
        """Forward mouse wheel down to the chat log."""
        try:
            chat_log = self._chat_log()
            chat_log.scroll_down()
            if self._is_chat_at_bottom(chat_log):
                self._auto_scroll_chat = True
            self._update_scroll_indicator()
        except Exception:
            pass

    def on_error(self, error: Exception) -> None:
        """Global error handler — Textual calls this for unhandled exceptions.

        Our goal: the TUI must never crash the whole process. We try to
        surface the problem to the user in the chat log (if possible) and keep running.
        """
        try:
            self._chat_log()
            self._append_to_log(
                f"\n[bold red]⚠ Internal TUI error (recovered):[/bold red] "
                f"{type(error).__name__}: {error}"
            )
            self._append_to_log("[dim]The interface should still be usable. You can continue working.[/dim]\n")
        except Exception:
            # If even writing the error failed, we silently swallow it.
            # The most important thing is that the app stays alive.
            pass

    CSS = HOLIX_TUI_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        # Global binding for sending. It is the reliable path for chat messages.
        # We block it only in on_key when the slash suggestions explicitly want Enter (when something is highlighted).
        Binding("enter", "send_message", "Send", priority=True),

        # macOS-friendly scroll bindings (less likely to be captured by the OS)
        Binding("ctrl+up", "scroll_chat_up", "Scroll Up (line)", show=True),
        Binding("ctrl+down", "scroll_chat_down", "Scroll Down (line)", show=True),
        Binding("ctrl+page_up", "scroll_chat_page_up", "Page Up", show=True),
        Binding("ctrl+page_down", "scroll_chat_page_down", "Page Down", show=True),
        Binding("ctrl+u", "scroll_chat_half_up", show=False),
        Binding("ctrl+d", "scroll_chat_half_down", show=False),
        Binding("ctrl+home", "scroll_chat_top", "Top", show=True),
        Binding("ctrl+end", "scroll_chat_bottom", "Bottom", show=True),

        # Keep some legacy bindings (may not work on all macOS terminals)
        Binding("page_up", "scroll_chat_page_up", show=False),
        Binding("page_down", "scroll_chat_page_down", show=False),
        Binding("home", "scroll_chat_top", show=False),
        Binding("end", "scroll_chat_bottom", show=False),

        Binding("f1", "help", "Help", show=True),
        Binding("ctrl+p", "command_palette", "Command Palette", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar", show=True),
        Binding("ctrl+shift+c", "copy_last_output", "Copy last output", show=True),
        # Shift+Tab cycles execution mode (react → plan_and_execute → hybrid → auto → react)
        Binding("shift+tab", "cycle_execution_mode", "Cycle Mode (react→plan→hybrid→auto)", show=True),
        Binding("ctrl+s", "stop_all", "Stop all tasks", show=True),
    ]

    def __init__(self, profile: str = "default", config: ProfileConfig | None = None):
        super().__init__()
        self.profile = profile
        self.config = config or init_profile(profile)
        self.profile_manager = ProfileManager()
        self.agent: HolixAgent | None = None
        self._event_handler = AgentEventHandler(self)
        self._slash_handler = SlashCommandHandler(self)
        self._modals = ModalStack(self)
        self.conversation_id = f"tui_{profile}"
        self.streaming_enabled: bool = False  # for /stream command

        # Buffer for streaming deltas (to avoid writing one character at a time to the chat log)
        self._stream_buffer: str = ""

        # Whether new messages should automatically scroll the chat to the bottom
        self._auto_scroll_chat: bool = True

        # Phase 2: Sidebar toggle (collapsed by default)
        self._sidebar_visible: bool = False
        self._sidebar_width: int = 32   # comfortable width when open

        # Ring buffer of recent full tool results (V1 stabilization for long outputs).
        # Lets user do /last or /tools to see complete output without truncation.
        self._recent_tool_results: list[dict] = []  # [{"name", "full_result"}]

        # Available tools for the current agent (populated after init)
        self._available_tools: list[dict] = []  # [{"name", "description"}]

        # Recent memory entries for current conversation (sidebar)
        self._recent_memories: list[dict] = []  # [{"role", "content", "short"}]

        # Phase 2: Advanced memory search UI — search results shown in Memory sidebar list
        # (distinct mode from "recent msgs in current conv"; clickable to insert)
        self._memory_search_results: list[dict] = []
        self._memory_search_query: str = ""
        self._memory_search_active: bool = False

        # Used to reliably execute palette commands on both mouse and Enter
        # (some older Textual versions don't auto-execute on list Enter)
        self._last_palette_command: Callable[[], None] | None = None

        # For "Regenerate last response" power-user feature (Wave 4)
        self._last_user_message: str | None = None

        # Live streaming state (Wave 5 UX polish)
        self._is_streaming: bool = False

        # Cached context display for header (updated after each response)
        self._cached_context_display: str | None = None

        # Marker for responses that came from "Regenerate" action
        self._next_response_is_regenerated: bool = False

        # Session management (Phase 1)
        self.known_sessions: list[dict] = []   # from list_conversations
        self.session_display_name: str = "main"
        self.session_names: dict[str, str] = {}  # conv_id -> custom human name (persisted)

        # Phase 2: Track active tool calls for rich Collapsible UI
        # key: tool_id -> {collapsible, container (Vertical), info}
        self._active_tool_calls: dict[str, dict] = {}

        # Phase 2: Skills loaded for the agent
        self._available_skills: list[dict] = []  # [{"name", "description", "tags"}]

        # Phase 2: Profile switching enhancements
        self._available_profiles: list[str] = []
        self.profile_switch_history: list[dict] = []  # [{"profile": str, "timestamp": str}]
        self._pending_profile_switch: str | None = None

        # Confirmation system: pending dangerous action confirmation
        self._pending_confirmation: Any | None = None  # ConfirmationRequestEvent
        self._action_guard_reference: Any | None = None  # ActionGuard instance

        # Phase 2: Support for re-running tool calls
        self._last_tool_call: dict | None = None  # {"tool_name": str, "arguments": dict}

        # Phase 2: Interface density (light customization)
        self.density: str = "normal"  # compact | normal | comfortable

        # Phase 2: Persisted UI state (density + which Collapsible sections are closed)
        # Loaded on mount, saved on change via _persist_ui_state ( ~/.holix/tui-state.json )
        self._persisted_ui: dict = {}

        # Execution mode state (shift+tab cycling)
        self._execution_modes: list[str] = ["react", "plan_and_execute", "hybrid", "auto"]
        self._execution_mode_index: int = 0  # Start with "react"

        # Slash command suggestions state (now used mainly for TAB completion)
        self._suggestion_commands: list[tuple[str, str]] = []  # (command, description)
        self._suggestions_visible: bool = False
        self._just_inserted_suggestion: bool = False

        # TAB autocompletion state for slash commands
        self._tab_completion_matches: list[str] = []
        self._tab_completion_index: int = -1
        self._tab_last_line: str = ""

        # Master list of slash commands for autocomplete
        self._all_slash_commands: list[tuple[str, str]] = [
            ("/clear", "Clear the chat"),
            ("/help", "Show help"),
            ("/metrics", "Show agent metrics"),
            ("/stream", "Toggle streaming mode"),
            ("/last", "Show full output of last tool call"),
            ("/tools", "List recent tool results"),
            ("/memory", "Semantic search in memory"),
            ("/memory-clear", "Clear search results, return Memory sidebar to recent messages"),
            ("/new", "Start a new session"),
            ("/sessions", "List recent sessions"),
            ("/switch", "Switch to another session"),
            ("/profile", "Switch to another profile"),
            ("/yes", "Confirm pending action"),
            ("/no", "Cancel pending action"),
            ("/rerun", "Repeat the last tool call"),
            ("/copy", "Copy last tool result / message"),
            ("/density", "Change interface density (compact/normal/comfort)"),
            ("/reset-ui", "Reset saved density and sidebar section collapse preferences"),
            ("/regenerate", "Regenerate response for your last message"),
            ("/session-info", "Show quick stats for the current session"),
            ("/insert-assistant", "Insert last Holix response as context"),
            ("/insert-tool", "Insert last tool result as context"),
            ("/edit-last", "Edit your last message and resend it"),
            ("/compress", "Compress conversation context to free up context window"),
            ("/init", "Deep project analysis → .holix/HOLIX.md"),
            ("/cron", "Cron jobs: list / add / enable / disable / remove"),
            ("/cron list", "List scheduled cron jobs"),
            ("/models", "Switch LLM model at runtime"),
            ("/model", "Switch LLM model (alias)"),
            ("/mode", "Cycle or set execution mode (react/plan_and_execute/hybrid/auto)"),
            ("/subagent-spawn", "Spawn a sub-agent (type required: researcher/coder/analyst/reviewer/writer)"),
            ("/subagent-list", "List all sub-agents and their status"),
            ("/subagent-terminate", "Terminate a sub-agent by name"),
            ("/subagent-result", "Show a sub-agent's result"),
            ("/ltm-stats", "Show long-term memory statistics"),
            ("/1", "Allow once (confirm pending dangerous action)"),
            ("/2", "Allow for this session (confirm pending action)"),
            ("/3", "Allow always (confirm permanently for this type)"),
            ("/4", "Deny (cancel pending dangerous action)"),
            ("/safety permissions", "List all active permission grants"),
            ("/plan-confirm", "Confirm current plan (step-by-step)"),
            ("/plan-auto", "Auto-execute current plan"),
            ("/plan-refine", "Refine current plan with feedback"),
            ("/plan-reject", "Reject current plan"),
            ("/stop", "Stop all running tasks immediately"),
        ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield HolixSidebar(profile=self.profile, model=self.config.model)
        yield HolixMainContent()
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize agent and welcome message when app starts."""
        try:
            self.title = "Holix"
            # sub_title will be immediately overwritten by _refresh_header_subtitle() with rich info

            self._append_to_log("[bold cyan]Holix[/bold cyan] — ready\n")
            self._append_to_log("[dim]Enter = send  •  Shift+Enter = newline  •  Ctrl+P = command palette (recommended)  •  Ctrl+B = sidebar[/dim]\n")
            self._append_to_log("[dim]Ctrl+↑/↓ scroll  •  /help or F1  •  density: compact/normal/comfort  •  sessions & profiles fully supported[/dim]\n\n")

            # Force scroll so the welcome text is visible immediately
            try:
                log = self._chat_log()
                log.scroll_end(animate=False)
            except Exception:
                pass

            # Initialize agent
            await self._initialize_agent()
        except Exception as e:
            # Even if initialization partially fails, try to keep the TUI alive
            try:
                self._chat_log()
                self._append_to_log(f"[bold red]Startup error (partial):[/bold red] {e}\n")
                self._append_to_log("[yellow]Some features may be limited, but the interface should still work.[/yellow]\n")
            except Exception:
                pass

    async def _initialize_agent(self) -> None:
        chat_log = self._chat_log()

        self._append_to_log("[yellow]Initializing Holix agent...[/yellow]\n")
        self._set_status("Initializing...", "yellow")

        from core.di import resolve_runtime_config
        from core.models.manager import ModelManager
        from core.models.profile_cleanup import MISSING_LLM_HINT, profile_has_llm_config

        if not profile_has_llm_config(self.config):
            self._append_to_log(f"[red]{MISSING_LLM_HINT}[/red]\n")
            self._set_status("No LLM configured", "red")
            self.agent = None
            self._resolved_model = "—"
            return

        runtime_config = resolve_runtime_config(self.config)
        try:
            model_config = ModelManager(self.config).get_default_model_config()
            if model_config:
                runtime_config = runtime_config.with_overrides(
                    model=model_config.model,
                    base_url=model_config.base_url,
                    api_key=model_config.api_key,
                    temperature=model_config.temperature,
                )
                self._append_to_log(f"[dim]Using provider: {model_config.model}[/dim]\n")
        except Exception as e:
            self._append_to_log(
                f"[red]Could not resolve model config ({e}). {MISSING_LLM_HINT}[/red]\n"
            )
            self._set_status("No LLM configured", "red")
            self.agent = None
            self._resolved_model = "—"
            return

        self.agent = HolixAgent(config=runtime_config)
        self._resolved_model = runtime_config.model

        # Subscribe to all events for reactive UI updates
        self.agent.events.subscribe(self._on_agent_event)

        await self.agent.initialize()

        # Load previous conversation history for better continuity (nice polish)
        await self._load_conversation_history(chat_log)

        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self._append_to_log(f"[dim]Model for this session: {restored}[/dim]\n")

        self._append_to_log("[green]Agent ready.[/green]  (sidebar closed by default — Ctrl+B to open)\n\n")
        self._update_sidebar()
        self._populate_tools_list()   # Phase 1: show available tools
        self._populate_memory_list()  # Phase 1: show recent memory
        self._update_sidebar_session()
        await self._load_known_sessions()  # for /sessions command
        self._populate_sessions_list()     # visual sessions in sidebar
        self._populate_skills_list()       # Phase 2: skills in sidebar
        self._populate_profiles_list()     # Phase 2: visual profiles list

        # Force scroll to bottom so initial content is visible
        try:
            log = self._chat_log()
            log.scroll_end(animate=False)
        except Exception:
            pass

        # Note: early "force sidebar closed" removed — the persisted restore later in this
        # method (with default=False) now owns the initial closed behavior + remembers user choice.

        self._set_status("Ready", "green")

        # Phase 2: load persisted density before applying (collapsed sections applied below)
        persisted = self._load_persisted_ui_state()
        self._persisted_ui = persisted
        d = persisted.get("density")
        if d in ("compact", "normal", "comfort"):
            self.density = d

        # Apply interface density (may come from persisted prefs)
        self.apply_density(self.density)
        self._update_density_indicator()

        # Ensure the input field has focus so user can start typing immediately
        try:
            input_area = self.query_one("#input-area", TextArea)
            input_area.focus()
        except Exception:
            pass

        # Phase 2: apply persisted Collapsible collapsed states (sidebar sections open/closed)
        # Done late so all Collapsibles from compose() are in the DOM.
        collapsed_map = persisted.get("collapsed") or {}
        for cid, is_coll in collapsed_map.items():
            try:
                c = self.query_one(f"#{cid}", Collapsible)
                if c is not None:
                    c.collapsed = bool(is_coll)
            except Exception:
                pass

        # Phase 2 finish: also restore last sidebar open/closed preference (default closed is only for first run)
        try:
            want_visible = persisted.get("sidebar_visible", False)
            sidebar = self.query_one("#sidebar")
            if want_visible:
                sidebar.styles.width = self._sidebar_width
                sidebar.styles.min_width = self._sidebar_width
                self._sidebar_visible = True
                self.set_timer(0.08, self._focus_first_sidebar_widget)
            else:
                sidebar.styles.width = 0
                sidebar.styles.min_width = 0
                self._sidebar_visible = False
        except Exception:
            pass

        # Make sure header always shows rich status from the very first frame
        self._refresh_header_subtitle()

        # Initialize context bar with current usage (async — reads from agent memory)
        await self._update_context_display_async()
        self._refresh_header_subtitle()

        # CRITICAL: Restore input focus after all populate calls.
        # The _populate_*_list methods add items to ListView widgets which steal focus.
        # Without this, the user cannot type on TUI startup.
        # force=True overrides the sidebar-focus guard since this is initialization,
        # not a user-initiated sidebar interaction.
        self._restore_input_focus(delay=0.15, force=True)

    async def _load_conversation_history(self, chat_log: RichLog | None = None) -> None:
        """Load recent messages from agent memory on startup (polish feature).
        The optional chat_log param is legacy and ignored; we always query the live RichLog.
        """
        try:
            history = await self.agent.get_conversation_history(
                self.conversation_id, limit=12
            )
            if not history:
                return

            self._append_to_log("[dim]--- Previous conversation ---[/dim]\n")
            for msg in history:
                role = msg.get("role", "unknown")
                content = str(msg.get("content", ""))[:300]
                if role == "user":
                    self._append_to_log(f"[bold blue]You:[/bold blue] {content}\n")
                elif role == "assistant":
                    self._append_to_log(f"[bold green]Holix:[/bold green] {content}\n")
                elif role == "tool":
                    self._append_to_log(f"[yellow]Tool result:[/yellow] {content[:150]}...\n")
            self._append_to_log("[dim]--- End of history ---[/dim]\n\n")
            self._scroll_chat_to_bottom()
            self._update_scroll_indicator()

            # Refresh memory sidebar with the loaded history
            self._populate_memory_list(history)

            # Update context bar with the loaded history (async — reads from agent memory)
            await self._update_context_display_async()
            self._refresh_header_subtitle()

            # Make sure input is focused even after loading history
            self._restore_input_focus(delay=0.05, force=True)

            # Ensure we are at the bottom after loading history
            try:
                log = self._chat_log()
                log.scroll_end(animate=False)
            except Exception:
                pass
        except Exception:
            # History loading is non-critical — fail silently
            pass

    def _on_agent_event(self, event: AgentEvent) -> None:
        """Delegate agent events to AgentEventHandler."""
        self._event_handler.handle(event)

    # We no longer rely on TextArea.Submitted for sending.
    # Sending is handled explicitly in on_key() for precise Enter vs Shift+Enter control.
    # This method can stay for future use if needed.

    async def _run_agent_task(self, user_input: str) -> None:
        """Execute the agent in non-streaming mode (with strong error protection)."""
        if not self.agent:
            return

        # Resolve current execution mode
        execution_mode = self._execution_modes[self._execution_mode_index]

        try:
            await self.agent.run(
                user_input=user_input,
                conversation_id=self.conversation_id,
                execution_mode=execution_mode,
            )
        except Exception as exc:
            try:
                self._chat_log()
                self._append_to_log(f"[bold red]Agent error:[/bold red] {exc}")
                self._set_status("Error", "red")

                self._is_streaming = False
                self._refresh_header_subtitle()

                self._restore_input_focus(delay=0.1)
            except Exception:
                pass  # UI may be in bad state — fail silently for this run

    async def _run_agent_streaming(self, user_input: str) -> None:
        """Execute the agent in real streaming mode (with strong error protection)."""
        if not self.agent:
            return

        # Resolve current execution mode
        execution_mode = self._execution_modes[self._execution_mode_index]

        try:
            from core.runtime.executor import run_holix

            async for event in run_holix(
                self.agent,
                user_input,
                self.conversation_id,
                stream=True,
                execution_mode=execution_mode,
            ):
                self.agent.emit(event)

        except Exception as exc:
            try:
                self._chat_log()
                self._append_to_log(f"[bold red]Streaming error:[/bold red] {exc}")
                self._set_status("Error", "red")

                self._is_streaming = False
                self._refresh_header_subtitle()

                self._restore_input_focus(delay=0.1)
            except Exception:
                pass

    def action_clear_chat(self) -> None:
        """Clear the chat log."""
        try:
            chat_log = self._chat_log()
            chat_log.clear()
            self._append_to_log("[dim]Chat cleared.[/dim]\n")
            # Reset scroll state + tool result buffer so indicator and /last don't show stale data
            self._auto_scroll_chat = True
            self._recent_tool_results.clear()
            self._recent_memories.clear()
            self.known_sessions = []  # will be repopulated on next load if needed
            self._active_tool_calls.clear()
            self._first_delta_seen = False
            self._last_user_message = None
            self._is_streaming = False
            self._next_response_is_regenerated = False
            self._update_scroll_indicator()

            # Phase 2: exit any memory search mode + clear list (will repopulate recent below)
            self._memory_search_active = False
            self._memory_search_results.clear()
            self._memory_search_query = ""
            try:
                mem_list = self.query_one("#memory-list", ListView)
                mem_list.clear()
                mem_list.append(ListItem(Static("[dim]No recent memory yet[/dim]")))
            except Exception:
                pass

            try:
                sess_list = self.query_one("#sessions-list", ListView)
                sess_list.clear()
                sess_list.append(ListItem(Static("[dim]No other sessions yet[/dim]")))
                # Reset the Collapsible title for the sessions section
                try:
                    coll = self.query_one("#sessions-collapsible", Collapsible)
                    if coll:
                        coll.title = "Sessions"
                except Exception:
                    pass
            except Exception:
                pass

            # Return focus to input after clearing
            self._restore_input_focus(delay=0.02)
        except Exception:
            pass

    def _action_stop_all(self) -> None:
        """Stop all running agent tasks immediately.

        Cancels any active streaming, running workers, pending plan reviews,
        and sub-agent processes. Resets the UI to ready state.
        """
        stopped_items = []

        # 1. Cancel streaming / agent workers
        try:
            # Textual workers are named "agent-stream" and "agent-run"
            for worker in self.workers:
                if worker.name in ("agent-stream", "agent-run"):
                    worker.cancel()
                    stopped_items.append("agent task")
        except Exception:
            pass

        # 2. Cancel sub-agent processes
        try:
            if self.agent and hasattr(self.agent, "sub_agent_manager") and self.agent.sub_agent_manager:
                active = self.agent.sub_agent_manager.list_active()
                if active:
                    self.run_worker(self.agent.sub_agent_manager.terminate_all())
                    stopped_items.append(f"{len(active)} sub-agent(s)")
        except Exception:
            pass

        # 3. Reject pending plan review
        if self._modals.plan_review.is_awaiting:
            self._modals.plan_review.cancel()
            stopped_items.append("plan review")

        # 4. Cancel pending confirmation
        if self._pending_confirmation:
            try:
                from core.security.confirmation import get_action_guard
                guard = get_action_guard()
                if guard:
                    review_id = list(guard._pending_confirmations.keys())[-1] if guard._pending_confirmations else None
                    if review_id:
                        from core.security.confirmation_events import ConfirmationChoice
                        guard.resolve_confirmation(review_id, ConfirmationChoice.DENY)
                        stopped_items.append("confirmation")
            except Exception:
                pass
            self._pending_confirmation = None

        # 5. Reset streaming state
        self._is_streaming = False
        self._stream_buffer = ""

        # 6. Disable plan execution auto-approve
        try:
            if self.agent and hasattr(self.agent, "tools") and hasattr(self.agent.tools, "_action_guard"):
                self.agent.tools._action_guard._auto_approve_plan_execution = False
        except Exception:
            pass

        # 7. Reset UI state
        self._set_status("Stopped", "yellow")
        self._refresh_header_subtitle()

        # Report what was stopped
        if stopped_items:
            items_str = ", ".join(stopped_items)
            self._append_to_log(f"\n[bold red]⏹ Stopped:[/bold red] {items_str}\n")
        else:
            self._append_to_log("\n[yellow]⏹ Nothing was running.[/yellow]\n")

        # Return focus to input
        self._restore_input_focus(delay=0.05)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses (sidebar + scroll indicator)."""
        try:
            if event.button.id == "btn-clear":
                self.action_clear_chat()
            elif event.button.id == "scroll-indicator":
                # User clicked the "new messages below" banner → jump to bottom
                self.action_jump_to_bottom()
        except Exception:
            # Button handling must never crash the TUI
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection in sidebar lists (Tools, Memory, Sessions, Skills, Profiles)."""
        try:
            list_view = event.list_view
            try:
                index = list_view.children.index(event.item)
            except ValueError:
                index = 0

            if list_view.id == "tools-list":
                if 0 <= index < len(self._available_tools):
                    self._show_tool_details(self._available_tools[index])

            elif list_view.id == "memory-list":
                self._insert_memory_from_sidebar(index)

            elif list_view.id == "sessions-list":
                # Switch to the selected session
                if 0 <= index < len(self.known_sessions):
                    # Run the switch (index is 0-based here, _switch_to_session expects 1-based)
                    self.run_worker(self._switch_to_session(index + 1))

            elif list_view.id == "skills-list":
                if 0 <= index < len(self._available_skills):
                    self._describe_skill(self._available_skills[index])  # shared with palette

            elif list_view.id == "profiles-list":
                if 0 <= index < len(self._available_profiles):
                    target = self._available_profiles[index]
                    if target != self.profile:
                        self._initiate_profile_switch(target)  # shared with palette (keeps /yes confirmation)
                    else:
                        self._chat_log()
                        self._append_to_log(f"[dim]Already using profile '{target}'.[/dim]")

        except Exception:
            pass

    def action_stop_all(self) -> None:
        """Ctrl+S: Stop all running tasks immediately."""
        self._action_stop_all()

    def action_send_message(self) -> None:
        """Send the current content of the input area (Enter)."""
        try:
            input_area = self.query_one("#input-area", TextArea)
            message = input_area.text.strip()

            if not message:
                return

            # Clear input immediately
            input_area.clear()

            # Reset TAB completion state
            self._tab_completion_matches = []
            self._tab_completion_index = -1
            self._tab_last_line = ""

            # Schedule the async send logic
            self.run_worker(self._send_message_manually(message))

            # Restore focus to input so user can type the next message immediately
            self._restore_input_focus(delay=0.06)
        except Exception:
            # Sending must never crash the whole TUI
            pass

    # Note: Shift+Enter newline is now handled naturally by TextArea
    # via the on_key handler (we just don't prevent default on shift+enter)

    async def _send_message_manually(self, message: str) -> None:
        """Internal method to send a message (used by both binding and submitted event).

        If a plan review is pending, the message is intercepted as a review
        response instead of being sent to the agent.
        """
        # Intercept message if we're awaiting a plan review response
        if self._modals.plan_review.is_awaiting:
            self._append_to_log(f"\n[bold blue]You:[/bold blue] {message}\n")
            self._modals.plan_review.handle_text_response(message)
            return

        if self.agent and not message.startswith("/"):
            from core.subagents.interaction import try_route_subagent_reply

            handled, feedback = try_route_subagent_reply(self.agent, message)
            if handled:
                self._append_to_log(f"\n[bold blue]You:[/bold blue] {message}\n")
                if feedback:
                    self._append_to_log(f"[dim]{feedback}[/dim]\n")
                return

        self._chat_log()

        # Handle slash commands locally in TUI
        if message.startswith("/"):
            await self._handle_slash_command(message)
            return

        # Remember for "Regenerate last response" (Wave 4)
        self._last_user_message = message
        self._next_response_is_regenerated = False  # user started a normal turn

        # Display user message
        self._append_to_log(f"\n[bold blue]You:[/bold blue] {message}\n")
        self._auto_scroll_chat = True   # User sent a message → they want to see the response
        self._scroll_chat_to_bottom()
        self._update_scroll_indicator()

        # Polish: refresh memory sidebar with the new user message
        self._refresh_memory_sidebar()

        if not self.agent:
            from core.models.profile_cleanup import MISSING_LLM_HINT

            self._append_to_log(f"[red]{MISSING_LLM_HINT}[/red]")
            return

        self._set_status("⟳ Thinking...", "yellow")
        self._first_delta_seen = False
        self._is_streaming = self.streaming_enabled

        # Choose execution path depending on streaming mode
        if self.streaming_enabled:
            self.run_worker(
                self._run_agent_streaming(message),
                name="agent-stream",
                exclusive=True,
            )
        else:
            self.run_worker(
                self._run_agent_task(message),
                name="agent-run",
                exclusive=True,
            )

    async def _handle_slash_command(self, command: str) -> None:
        """Delegate slash commands to SlashCommandHandler."""
        await self._slash_handler.handle(command)


    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility (Phase 2).
        Sidebar starts collapsed. Ctrl+B opens/closes it.
        """
        try:
            sidebar = self.query_one("#sidebar")
            self._sidebar_visible = not self._sidebar_visible

            if self._sidebar_visible:
                sidebar.styles.width = self._sidebar_width
                sidebar.styles.min_width = self._sidebar_width
                # Try to focus the first useful list when opening
                self.set_timer(0.05, self._focus_first_sidebar_widget)
                self._populate_profiles_list()  # refresh in case profiles changed
            else:
                sidebar.styles.width = 0
                sidebar.styles.min_width = 0
        except Exception:
            pass

        # Persist the visibility choice immediately (same as density / collapsibles)
        self._persist_ui_state()

        # QoL: when closing the sidebar, return focus to input so user can keep typing
        if not self._sidebar_visible:
            self._restore_input_focus(delay=0.04)

    # --- Copy functionality (best effort for RichLog) ---

    # --- Execution Mode Cycling (Shift+Tab) ---

    MODE_LABELS = {
        "react": "⚡ ReAct",
        "plan_and_execute": "📋 Plan & Execute",
        "hybrid": "🔄 Hybrid",
        "auto": "🤖 Auto",
    }

    async def action_cycle_execution_mode(self, just_set: bool = False) -> None:
        """Cycle execution mode (Shift+Tab) or set a specific mode.

        Modes cycle: react → plan_and_execute → hybrid → auto → react

        Args:
            just_set: If True, don't cycle — just display the current mode.
                      Used when /mode <mode> sets a specific mode.
        """
        if not just_set:
            # Cycle to next mode
            self._execution_mode_index = (self._execution_mode_index + 1) % len(self._execution_modes)

        mode = self._execution_modes[self._execution_mode_index]
        mode_label = self.MODE_LABELS.get(mode, mode)

        # Update config
        from config import settings
        settings.execution_mode = mode

        # Update the header subtitle if possible
        try:
            self._refresh_header_subtitle()
        except Exception:
            pass

        # Log the mode change
        self._append_to_log(
            f"[bold cyan]Execution mode:[/bold cyan] {mode_label}\n"
            f"[dim]Use Shift+Tab to cycle, /mode <name> to set directly[/dim]\n"
        )

        # Update sidebar mode display if it exists
        try:
            mode_display = self.query_one("#exec-mode-display", Static)
            await mode_display.update(mode_label)
        except Exception:
            pass

    # --- Sub-agent action methods ---

    async def _action_spawn_subagent(self, agent_type: str) -> None:
        """Spawn a sub-agent of the given type (called from /subagent-spawn)."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        from config import settings
        if not settings.enable_subagents:
            self._append_to_log("[yellow]Sub-agents are disabled. Set enable_subagents=True in config.[/yellow]\n")
            return

        from core.subagents.registry import get_subagent_config
        try:
            config = get_subagent_config(agent_type)
        except KeyError:
            self._append_to_log(f"[red]Unknown sub-agent type: {agent_type}[/red]\n")
            return

        # Get task from input area
        input_area = self.query_one("#input-area", TextArea)
        task = input_area.text.strip()
        if not task:
            self._append_to_log("[yellow]Enter a task description in the input field first.[/yellow]\n")
            return

        self._append_to_log(f"[cyan]Spawning {agent_type} sub-agent...[/cyan]\n")
        self._set_status(f"Spawning {agent_type}...", "yellow")

        try:
            subagent_mgr = getattr(self._agent, '_subagent_manager', None)
            if not subagent_mgr:
                self._append_to_log("[red]Sub-agent manager not available.[/red]\n")
                return

            handle = await subagent_mgr.spawn_sub_agent(config, task=task)
            mode_label = config.process_mode.value if hasattr(config, 'process_mode') else "?"
            self._append_to_log(
                f"[green]✓ Sub-agent '{config.name}' spawned (mode={mode_label})[/green]\n"
            )
            self._set_status(f"Running: {config.name}", "green")

            # Wait for result in background
            self.run_worker(self._wait_for_subagent(config.name, handle))

        except Exception as e:
            self._append_to_log(f"[red]Failed to spawn sub-agent: {e}[/red]\n")
            self._set_status("Error", "red")

    async def _wait_for_subagent(self, name: str, handle) -> None:
        """Wait for a sub-agent to complete and display its result."""
        try:
            result = await handle
            if result and hasattr(result, 'response'):
                self._append_to_log(
                    f"[green]✓ Sub-agent '{name}' completed[/green]\n"
                    f"[dim]Duration: {getattr(result, 'duration_ms', 0):.0f}ms[/dim]\n\n"
                    f"{result.response[:2000]}\n"
                )
            elif result:
                self._append_to_log(f"[green]✓ Sub-agent '{name}' completed[/green]\n")
            else:
                self._append_to_log(f"[yellow]Sub-agent '{name}' returned no result.[/yellow]\n")
        except Exception as e:
            self._append_to_log(f"[red]Sub-agent '{name}' error: {e}[/red]\n")
        finally:
            self._set_status("Ready", "green")

    async def _action_list_subagents(self) -> None:
        """List all sub-agents and their status."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        subagent_mgr = getattr(self._agent, '_subagent_manager', None)
        if not subagent_mgr:
            self._append_to_log("[dim]Sub-agent manager not available (sub-agents disabled).[/dim]\n")
            return

        try:
            handles = subagent_mgr.list_all()
            if not handles:
                self._append_to_log("[dim]No sub-agents running.[/dim]\n")
                return

            from cli.tui.legacy.subagents_widget import format_subagent_status
            lines = []
            for h in handles:
                lines.append(f"  {format_subagent_status(h)}")
            self._append_to_log(
                f"[bold]Sub-Agents ({len(handles)}):[/bold]\n" + "\n".join(lines) + "\n"
            )
        except Exception as e:
            self._append_to_log(f"[red]Error listing sub-agents: {e}[/red]\n")

    async def _action_terminate_subagent(self, name: str) -> None:
        """Terminate a running sub-agent by name."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        subagent_mgr = getattr(self._agent, '_subagent_manager', None)
        if not subagent_mgr:
            self._append_to_log("[dim]Sub-agent manager not available.[/dim]\n")
            return

        self._append_to_log(f"[yellow]Terminating sub-agent '{name}'...[/yellow]\n")
        try:
            success = await subagent_mgr.terminate(name)
            if success:
                self._append_to_log(f"[green]✓ Sub-agent '{name}' terminated.[/green]\n")
            else:
                self._append_to_log(f"[yellow]Sub-agent '{name}' not found or already stopped.[/yellow]\n")
        except Exception as e:
            self._append_to_log(f"[red]Error terminating sub-agent: {e}[/red]\n")

    async def _action_show_subagent_result(self, name: str) -> None:
        """Show a sub-agent's result."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        subagent_mgr = getattr(self._agent, '_subagent_manager', None)
        if not subagent_mgr:
            self._append_to_log("[dim]Sub-agent manager not available.[/dim]\n")
            return

        try:
            result = subagent_mgr.get_result(name)
            if result:
                self._append_to_log(
                    f"[bold]Result from '{name}':[/bold]\n"
                    f"Success: {result.success}\n"
                    f"Duration: {getattr(result, 'duration_ms', 0):.0f}ms\n\n"
                    f"{result.response[:3000]}\n"
                )
            else:
                self._append_to_log(f"[yellow]No result available for '{name}'.[/yellow]\n")
        except Exception as e:
            self._append_to_log(f"[red]Error getting result: {e}[/red]\n")

    async def _action_show_ltm_stats(self) -> None:
        """Display long-term memory statistics in the chat."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        memory = getattr(self._agent, 'memory', None)
        if not memory or not hasattr(memory, 'episodic'):
            self._append_to_log("[yellow]Long-term memory not available.[/yellow]\n")
            return

        try:
            stats = memory.get_memory_stats()
            vs = stats.get("vector_store", {})

            lines = ["[bold]Long-Term Memory Statistics[/bold]\n"]
            total = 0
            for collection, count in vs.items():
                name = collection.replace("ltm_", "").title()
                lines.append(f"  {name}: {count} entries")
                total += count
            lines.append(f"\n  [bold]Total: {total} entries[/bold]")

            # Also show strategy summary
            try:
                strategies = await memory.strategic.get_all_strategies()
                if strategies:
                    lines.append(f"\n  Strategies stored: {len(strategies)}")
            except Exception:
                pass

            self._append_to_log("\n".join(lines) + "\n")
        except Exception as e:
            self._append_to_log(f"[red]Error getting LTM stats: {e}[/red]\n")

    # --- Dangerous action confirmation UI (via ModalStack) ---

    def _handle_confirmation_request(self, event: ConfirmationRequestEvent) -> None:
        self._modals.confirmation.show(event)

    def _on_confirmation_result(self, result: str) -> None:
        self._modals.confirmation.on_dismissed(result)

    def _resolve_confirmation(self, choice: ConfirmationChoice) -> None:
        self._modals.confirmation.resolve(choice)

    # --- Plan review UI (in-chat via ModalStack) ---

    def _handle_plan_review_request(self, event: PlanReviewRequestEvent) -> None:
        self._modals.plan_review.show(event)

    def _resolve_plan_review(self, choice, feedback: str = "") -> None:
        self._modals.plan_review.resolve(choice, feedback)

    def _parse_review_response(self, text: str):
        return self._modals.plan_review.parse_response(text)

    def _handle_review_response(self, message: str) -> None:
        self._modals.plan_review.handle_text_response(message)

    def _show_safety_permissions(self) -> None:
        """Show all active permission grants."""
        if not self._action_guard_reference:
            self._append_to_log("[yellow]ActionGuard not initialized.[/yellow]")
            return

        try:
            from core.security.confirmation import permission_manager
            grants = permission_manager.list_grants()
            lines = ["[bold]Active Permission Grants[/bold]\n"]

            session_grants = grants.get("session", [])
            always_grants = grants.get("always", [])

            if session_grants:
                lines.append("[cyan]Session grants:[/cyan]")
                for g in session_grants:
                    pattern = f" ({g['pattern']})" if g.get("pattern") else ""
                    lines.append(f"  • {g['tool']}: {g['risk']}{pattern}")
            else:
                lines.append("[dim]No session grants.[/dim]")

            if always_grants:
                lines.append("\n[blue]Permanent grants:[/blue]")
                for g in always_grants:
                    pattern = f" ({g['pattern']})" if g.get("pattern") else ""
                    lines.append(f"  • {g['tool']}: {g['risk']}{pattern}")
            else:
                lines.append("[dim]No permanent grants.[/dim]")

            self._append_to_log("\n".join(lines) + "\n")
        except Exception as e:
            self._append_to_log(f"[red]Error listing permissions: {e}[/red]")

    def action_copy_last_output(self) -> None:
        """Copy the last meaningful output to clipboard (best effort)."""
        try:
            self._chat_log()

            if self._recent_tool_results:
                last = self._recent_tool_results[-1]
                name = last.get("name", "unknown")
                content = last.get("full_result", "")
                text = f"=== Tool: {name} ===\n\n{content}"
                self.app.copy_to_clipboard(text)
                self._append_to_log("[dim]Last tool result copied to clipboard.[/dim]")
                return

            # Fallback to recent memory
            if self._recent_memories:
                last = self._recent_memories[-1]
                text = f"=== {last.get('role', 'message').title()} ===\n\n{last.get('content', '')}"
                self.app.copy_to_clipboard(text)
                self._append_to_log("[dim]Last message copied to clipboard.[/dim]")
                return

            self._append_to_log("[yellow]No recent content found to copy. Try /copy or select text if your terminal allows it.[/yellow]")

        except Exception as e:
            self._append_to_log(f"[red]Copy failed: {e}[/red]")

    def action_copy_log(self) -> None:
        """Copy recent chat log content (best effort)."""
        try:
            self._chat_log()
            self._append_to_log("[yellow]RichLog has limited selection. Use Ctrl+Shift+C or /copy for recent output.[/yellow]")
        except Exception:
            pass

    def action_copy_last_assistant(self) -> None:
        """Copy the last assistant (Holix) response to clipboard via Textual (works in most modern terminals)."""
        try:
            if not self._recent_memories:
                self._append_to_log("[yellow]No assistant responses yet in this session.[/yellow]")
                return

            # Find the most recent assistant message
            for mem in reversed(self._recent_memories):
                if mem.get("role") == "assistant":
                    content = mem.get("content", "")
                    self.app.copy_to_clipboard(content)
                    content[:80].replace("\n", " ")
                    self._append_to_log(f"[dim]Last Holix response copied ({len(content)} chars).[/dim]")
                    return

            self._append_to_log("[yellow]No assistant response found yet.[/yellow]")
        except Exception as e:
            self._append_to_log(f"[red]Copy failed: {e}[/red]")

    def action_copy_last_tool_result(self) -> None:
        """Explicit palette-friendly action to copy the full last tool output."""
        try:
            if not self._recent_tool_results:
                self._append_to_log("[yellow]No tool results in this session yet. Use /tools or run something first.[/yellow]")
                return

            last = self._recent_tool_results[-1]
            name = last.get("name", "unknown")
            content = last.get("full_result", last.get("result", ""))
            text = f"=== Tool: {name} ===\n\n{content}"
            self.app.copy_to_clipboard(text)
            self._append_to_log(f"[dim]Full tool result for '{name}' copied to clipboard.[/dim]")
        except Exception as e:
            self._append_to_log(f"[red]Copy failed: {e}[/red]")

    def _focus_first_sidebar_widget(self) -> None:
        """Focus the first list in the sidebar when it is opened."""
        for list_id in ("#tools-list", "#memory-list", "#sessions-list", "#skills-list"):
            try:
                widget = self.query_one(list_id, ListView)
                if widget:
                    widget.focus()
                    return
            except Exception:
                continue

    def apply_density(self, level: str) -> None:
        """Apply interface density (compact / normal / comfortable)."""
        if level not in ("compact", "normal", "comfort"):
            level = "normal"

        self.density = level

        try:
            screen = self.screen
            # Remove existing density classes
            for cls in ("density-compact", "density-normal", "density-comfort"):
                screen.remove_class(cls)
            screen.add_class(f"density-{level}")
        except Exception:
            pass

        # Persist the change (density + current collapsed states snapshot)
        self._persist_ui_state()

        # Update the visual indicator
        self._update_density_indicator()
        self._refresh_header_subtitle()

        # Small QoL: after changing density the user almost always wants to continue typing
        self._restore_input_focus(delay=0.03)

    # --- Phase 2: UI state persistence (density + Collapsible sections) ---

    def _get_tui_state_path(self) -> Path:
        """Return path to persisted TUI prefs."""
        HOLIX_HOME.mkdir(parents=True, exist_ok=True)
        return HOLIX_HOME / "tui-state.json"

    def _load_persisted_ui_state(self) -> dict:
        """Load saved density / collapsed sections. Safe on any error."""
        try:
            sp = self._get_tui_state_path()
            if sp.exists():
                data = json.loads(sp.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _persist_ui_state(self) -> None:
        """Snapshot current density + all known sidebar Collapsibles into json file."""
        try:
            state = self._load_persisted_ui_state()
            state["density"] = self.density
            collapsed: dict[str, bool] = {}
            for cid in (
                "tools-collapsible",
                "memory-collapsible",
                "sessions-collapsible",
                "skills-collapsible",
                "profiles-collapsible",
            ):
                try:
                    c = self.query_one(f"#{cid}", Collapsible)
                    collapsed[cid] = bool(getattr(c, "collapsed", False))
                except Exception:
                    pass
            if collapsed:
                state["collapsed"] = collapsed
            # Also remember user's last choice for sidebar open/closed (Phase 2 finish)
            state["sidebar_visible"] = bool(self._sidebar_visible)
            # Persist custom session names
            if self.session_names:
                state["session_names"] = self.session_names
            self._get_tui_state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            # Never let persistence break the TUI
            pass

    def _apply_persisted_ui_state(self) -> None:
        """Apply saved density (if valid) and set Collapsible collapsed states after mount."""
        persisted = self._load_persisted_ui_state()
        self._persisted_ui = persisted

        # Density first (before or right after initial apply)
        d = persisted.get("density")
        if d in ("compact", "normal", "comfort"):
            self.density = d

        # Collapsed sections (widgets must exist)
        collapsed_map = persisted.get("collapsed") or {}
        for cid, is_coll in collapsed_map.items():
            try:
                c = self.query_one(f"#{cid}", Collapsible)
                if c is not None:
                    c.collapsed = bool(is_coll)
            except Exception:
                pass

        # Load custom session names
        self.session_names = persisted.get("session_names") or {}

    def _reset_ui_state(self) -> None:
        """Delete persisted file and restore compile-time defaults (used by /reset-ui)."""
        try:
            sp = self._get_tui_state_path()
            if sp.exists():
                sp.unlink()
        except Exception:
            pass
        self._persisted_ui = {}
        self.session_names = {}
        # Reset density to normal
        self.apply_density("normal")
        # Reset Collapsibles to the defaults used in compose()
        defaults = {
            "tools-collapsible": False,
            "memory-collapsible": False,
            "sessions-collapsible": True,
            "skills-collapsible": True,
            "profiles-collapsible": False,
        }
        for cid, is_coll in defaults.items():
            try:
                c = self.query_one(f"#{cid}", Collapsible)
                if c:
                    c.collapsed = is_coll
            except Exception:
                pass
        # Also reset sidebar to closed (the documented default)
        try:
            sidebar = self.query_one("#sidebar")
            sidebar.styles.width = 0
            sidebar.styles.min_width = 0
            self._sidebar_visible = False
        except Exception:
            pass
        self._append_to_log("[dim]UI preferences reset to defaults (density + sidebar sections + sidebar closed).[/dim]")

    def on_collapsible_collapsed(self, event: Collapsible.Collapsed) -> None:
        """Any sidebar section collapsed by user → persist the new layout prefs."""
        self._persist_ui_state()

    def on_collapsible_expanded(self, event: Collapsible.Expanded) -> None:
        """Any sidebar section expanded → persist."""
        self._persist_ui_state()

    def _on_input_text_changed(self, text: str) -> None:
        """Called when the content of the input TextArea changes."""
        if self.focused and getattr(self.focused, "id", None) == "input-area":
            self._update_command_suggestions(text)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Update slash suggestions when typing in the input."""
        if event.text_area.id == "input-area":
            self._on_input_text_changed(event.text_area.text)

    def _chat_log(self) -> HolixChatLog | None:
        try:
            return self.query_one(HolixChatLog)
        except Exception:
            return None

    def _append_to_log(self, content) -> None:
        """Append content to the chat log."""
        log = self._chat_log()
        if log:
            log.append(content)

    # Slash command handling and suggestions (dropdown kept for / UX; main power-user entry is Ctrl+P palette)

    # --- Command Palette Actions (Phase 2) ---

    def action_new_session(self) -> None:
        self.run_worker(self._create_new_session())

    def action_show_sessions(self) -> None:
        self.run_worker(self._show_sessions_list())

    def _switch_to_session_by_index(self, one_based_index: int) -> None:
        """Thin wrapper for dynamic Command Palette session switch hits (and reuse)."""
        self.run_worker(self._switch_to_session(one_based_index))

    def action_show_metrics(self) -> None:
        self.run_worker(self._handle_slash_command("/metrics"))

    def action_toggle_streaming(self) -> None:
        self.run_worker(self._handle_slash_command("/stream"))

    def action_search_memory(self) -> None:
        """Focus input and prepare for memory search."""
        try:
            input_area = self.query_one("#input-area", TextArea)
            input_area.text = "/memory "
            input_area.focus()
            input_area.cursor_location = (0, len(input_area.text))
        except Exception:
            pass

    def action_clear_memory_search(self) -> None:
        """Clear semantic search results from Memory sidebar and return to recent messages (Command Palette + /memory-clear)."""
        self._clear_memory_search()

    def action_rerun_last_tool(self) -> None:
        """Re-run the last tool call (exposed to Command Palette)."""
        self.run_worker(self._rerun_last_tool())

    def action_insert_last_memory(self) -> None:
        """Insert the most recent memory entry into the input as context."""
        if not self._recent_memories:
            try:
                self._chat_log()
                self._append_to_log("[yellow]No recent memory to insert yet.[/yellow]")
            except Exception:
                pass
            return

        try:
            mem = self._recent_memories[-1]
            input_area = self.query_one("#input-area", TextArea)
            context = f"\n[Memory from {mem['role']}]:\n{mem['content']}\n"
            current = input_area.text or ""
            input_area.text = (current.rstrip() + context).lstrip()
            input_area.focus()
        except Exception:
            pass

    def action_insert_last_assistant(self) -> None:
        """Insert the most recent assistant (Holix) response as context into the input field.
        Extremely useful for iterative refinement in long conversations.
        """
        try:
            if not self._recent_memories:
                self._append_to_log("[yellow]No conversation history yet.[/yellow]")
                return

            # Find the most recent assistant message (from the end)
            last_assistant = None
            for mem in reversed(self._recent_memories):
                if mem.get("role") == "assistant":
                    last_assistant = mem
                    break

            if not last_assistant:
                self._append_to_log("[yellow]No assistant response yet in this session.[/yellow]")
                return

            input_area = self.query_one("#input-area", TextArea)
            context = f"\n[Previous Holix response]:\n{last_assistant['content']}\n"
            current = input_area.text or ""
            input_area.text = (current.rstrip() + context).lstrip()
            lines = input_area.text.splitlines()
            input_area.cursor_location = (len(lines) - 1, 0)
            input_area.focus()
            self._append_to_log("[dim]Last Holix response inserted as context.[/dim]")
        except Exception as e:
            try:
                self._append_to_log(f"[red]Insert failed: {e}[/red]")
            except Exception:
                pass

    def action_regenerate_last_response(self) -> None:
        """Re-send the last user message to get a fresh response from the agent.
        Extremely useful when the previous answer was not satisfactory.
        """
        if not self._last_user_message:
            try:
                self._append_to_log("[yellow]No previous user message to regenerate.[/yellow]")
            except Exception:
                pass
            return

        try:
            self._chat_log()
            self._append_to_log("\n[dim]⟳ Regenerating response for your last message...[/dim]\n")

            # Re-display the user message to make the new turn clear in history
            self._append_to_log(f"[bold blue]You (regenerate):[/bold blue] {self._last_user_message}\n")
            self._auto_scroll_chat = True
            self._scroll_chat_to_bottom()

            # Robustness: clear any leftover streaming state from previous turn
            self._stream_buffer = ""
            self._first_delta_seen = False

            # Refresh memory sidebar so the new user message appears immediately
            self._refresh_memory_sidebar()

            if not self.agent:
                self._append_to_log("[red]Agent not initialized.[/red]")
                return

            self._set_status("⟳ Thinking...", "yellow")
            self._is_streaming = self.streaming_enabled
            self._next_response_is_regenerated = True   # mark the upcoming response

            if self.streaming_enabled:
                self.run_worker(
                    self._run_agent_streaming(self._last_user_message),
                    name="agent-stream",
                    exclusive=True,
                )
            else:
                self.run_worker(self._run_agent_task(self._last_user_message))

            self._update_scroll_indicator()
            self._restore_input_focus(delay=0.08)
        except Exception as e:
            try:
                self._append_to_log(f"[red]Regenerate failed: {e}[/red]")
            except Exception:
                pass

    def action_edit_last_message(self) -> None:
        """Prefill the input area with the last user message so the user can easily edit and resend it.
        Excellent companion to /regenerate for iterative refinement.
        """
        if not self._last_user_message:
            try:
                self._append_to_log("[yellow]No previous user message to edit.[/yellow]")
            except Exception:
                pass
            return

        try:
            input_area = self.query_one("#input-area", TextArea)
            input_area.text = self._last_user_message
            input_area.focus()
            # Move cursor to the end
            lines = input_area.text.splitlines() or [""]
            input_area.cursor_location = (len(lines) - 1, len(lines[-1]))
            self._append_to_log("[dim]Editing last message — edit and press Enter to resend.[/dim]")

            # Defensive: clear any pending regeneration marker
            self._next_response_is_regenerated = False
        except Exception as e:
            try:
                self._append_to_log(f"[red]Edit failed: {e}[/red]")
            except Exception:
                pass

    def _insert_memory_from_sidebar(self, index: int) -> None:
        """Reusable insert logic for sidebar clicks + dynamic Command Palette hits (Phase 2)."""
        try:
            if self._memory_search_active and 0 <= index < len(self._memory_search_results):
                mem = self._memory_search_results[index]
                role = mem.get("metadata", {}).get("role", "memory")
                content = mem.get("content", "")
                context = f"\n[Memory search hit ({role})]:\n{content}\n"
            elif 0 <= index < len(self._recent_memories):
                mem = self._recent_memories[index]
                context = f"\n[From previous {mem['role']} memory]:\n{mem['content']}\n"
            else:
                return
            input_area = self.query_one("#input-area", TextArea)
            current = input_area.text or ""
            input_area.text = (current.rstrip() + context).lstrip()
            lines = input_area.text.splitlines()
            input_area.cursor_location = (len(lines) - 1, 0)
            input_area.focus()
        except Exception:
            # Fallback to chat log
            try:
                self._chat_log()
                self._append_to_log("[yellow]Could not insert memory directly; see chat for details.[/yellow]")
            except Exception:
                pass

    def _insert_tool_result_as_context(self, idx_from_end: int = 0) -> None:
        """Insert a specific recent tool result into input (0 = most recent).
        Used by dynamic palette hits for last N tools.
        """
        if not self._recent_tool_results:
            try:
                self._append_to_log("[yellow]No tool results yet to insert.[/yellow]")
            except Exception:
                pass
            return
        try:
            idx = -(idx_from_end + 1)
            if abs(idx) > len(self._recent_tool_results):
                return
            entry = self._recent_tool_results[idx]
            name = entry.get("name", "tool")
            full = str(entry.get("full_result", ""))[:800]
            context = f"\n[Tool result from {name}]:\n{full}\n"
            input_area = self.query_one("#input-area", TextArea)
            current = input_area.text or ""
            input_area.text = (current.rstrip() + context).lstrip()
            lines = input_area.text.splitlines()
            input_area.cursor_location = (len(lines) - 1, 0)
            input_area.focus()
        except Exception:
            pass

    def _insert_last_tool_result_as_context(self) -> None:
        """Backward-compatible wrapper for the most recent tool result."""
        self._insert_tool_result_as_context(0)

    def _describe_skill(self, skill: dict) -> None:
        """Show skill details (reused by sidebar click and palette)."""
        try:
            self._chat_log()
            name = skill.get("name", "unknown")
            desc = skill.get("description", "(no description)")
            tags = skill.get("tags", []) or []
            self._append_to_log(f"\n[bold magenta]Skill:[/bold magenta] {name}")
            if tags:
                self._append_to_log(f"[dim]tags: {', '.join(tags)}[/dim]")
            self._append_to_log(f"[dim]{desc}[/dim]\n")
        except Exception:
            pass

    def _insert_skill_as_context(self, skill: dict) -> None:
        """Insert a skill's description + tags as useful context (for palette)."""
        try:
            name = skill.get("name", "skill")
            desc = skill.get("description", "")
            tags = skill.get("tags", []) or []
            tags_str = f" (tags: {', '.join(tags)})" if tags else ""
            context = f"\n[Skill: {name}{tags_str}]\n{desc}\n"
            input_area = self.query_one("#input-area", TextArea)
            current = input_area.text or ""
            input_area.text = (current.rstrip() + context).lstrip()
            lines = input_area.text.splitlines()
            input_area.cursor_location = (len(lines) - 1, 0)
            input_area.focus()
        except Exception:
            pass

    def action_set_density_compact(self) -> None:
        self.apply_density("compact")

    def action_set_density_normal(self) -> None:
        self.apply_density("normal")

    def action_set_density_comfort(self) -> None:
        self.apply_density("comfort")

    def action_reset_ui_state(self) -> None:
        """Reset persisted UI prefs (density + collapsed sections) via Command Palette."""
        self._reset_ui_state()

    def action_show_skills(self) -> None:
        """Show skills (via sidebar population + details in chat for first few)."""
        self._populate_skills_list()
        # Show first 3 skills in chat as a quick overview (power-user friendly)
        try:
            for sk in self._available_skills[:3]:
                self._describe_skill(sk)
            if len(self._available_skills) > 3:
                self._chat_log()
                self._append_to_log(f"[dim]... and {len(self._available_skills)-3} more. Click in sidebar Skills list for details.[/dim]\n")
        except Exception:
            pass

    def _initiate_profile_switch(self, profile_name: str) -> None:
        """Start profile switch flow (used by sidebar + dynamic palette hits). Keeps the /yes confirmation safety."""
        if profile_name == self.profile:
            return
        self._pending_profile_switch = profile_name
        try:
            self._chat_log()
            self._append_to_log(f"\n[yellow]Switch to profile '{profile_name}'?[/yellow] Type /yes to confirm or /no to cancel.")
            self._append_to_log("[dim]This will create a fresh session for the new profile.[/dim]\n")
        except Exception:
            pass

    def action_show_last_tool_result(self) -> None:
        """Show the full last tool result in chat using the same rich Panel formatting as live tool calls."""
        self._show_full_tool_result(index_from_end=0)

    def action_switch_profile(self) -> None:
        """Show profile switcher (Phase 2)."""
        self.run_worker(self._show_profile_switcher())

    def action_command_palette(self) -> None:
        """Open the real Textual Command Palette (Phase 2)."""
        self.push_screen(CommandPalette(providers=[HolixCommandProvider]))
        # Ensure input gets focus back after palette closes (best effort)
        self.set_timer(0.2, self._restore_input_focus)

    @on(CommandPalette.Closed)
    def _on_command_palette_closed(self, event: CommandPalette.Closed) -> None:
        """Main fallback for keyboard Enter.

        Execute the command we remembered from OptionHighlighted when the palette closes.
        """

        if self._last_palette_command is not None:
            cmd = self._last_palette_command
            self._last_palette_command = None
            self.call_later(cmd)
        else:
            if event.option_selected:
                # Selection happened but no pending command remembered — fallback
                pass

    @on(CommandPalette.OptionHighlighted)
    def _on_palette_option_highlighted(self, event: CommandPalette.OptionHighlighted) -> None:
        """Remember the command when user navigates with arrows.

        This is the most reliable signal we get during keyboard navigation.
        """
        option = getattr(event, 'option', None)
        if isinstance(option, PaletteCommandOption):
            hit = getattr(option, 'hit', None)
            if hit is not None and hasattr(hit, 'command') and callable(hit.command):
                self._last_palette_command = hit.command

                # UX improvement: show the highlighted command in the input (helps user see what will run)
                try:
                    prompt = str(getattr(hit, 'text', hit) or '')
                    input_field = self.query_one(CommandInput)
                    with self.prevent(Input.Changed):
                        input_field.value = prompt
                except Exception:
                    pass
            else:
                self._last_palette_command = None

    @on(OptionList.OptionSelected)
    def _on_palette_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Force-execute the command when an option is selected in the palette list.

        This catches Enter presses on the results list in Textual versions where
        the palette does not automatically invoke hit.command on list selection.
        """
        option = getattr(event, 'option', None)
        if isinstance(option, PaletteCommandOption):
            hit = getattr(option, 'hit', None)
            if hit is not None and hasattr(hit, 'command') and callable(hit.command):
                cmd = hit.command
                # Clear to avoid double execution from Closed handler
                self._last_palette_command = None
                self.call_later(cmd)

    @on(ExecutePaletteCommand)
    def _on_execute_palette_command(self, event: ExecutePaletteCommand) -> None:
        """The single reliable execution point for all palette items (mouse and Enter).

        We clear the pending command and run the actual logic here.
        """
        self._last_palette_command = None
        try:
            event.command()
        except Exception as e:
            try:
                self._append_to_log(f"[red]Palette execution error: {e}[/red]")
            except Exception:
                pass

    @on(Input.Submitted)
    def _on_palette_input_submitted(self, event: Input.Submitted) -> None:
        """Catch Enter presses inside the CommandPalette.

        This is the most reliable "commit" gesture we can hook in the current
        Textual version for keyboard users. If the user highlighted something
        with arrows, we have a pending command and execute it here.
        """
        if not CommandPalette.is_open(self):
            return

        if self._last_palette_command is not None:
            cmd = self._last_palette_command
            self._last_palette_command = None
            self.call_later(cmd)
            event.stop()
        else:
            # Normal search submit behavior (if someone types and presses Enter)
            pass

    def action_help(self) -> None:
        """Show help in the chat log."""
        try:
            self._chat_log()
            self._append_to_log("\n[bold cyan]Holix TUI — Phase 2 (polished)[/bold cyan]")
            self._append_to_log("[dim]Header always shows: profile • model • session [density]  (even with sidebar closed)[/dim]")
            self._append_to_log("[dim]Strong keyboard focus on input + all sidebar lists • Better contrast in compact mode[/dim]\n")

            self._append_to_log("[bold]Recent power-user features (Ctrl+P is fastest):[/bold]")
            self._append_to_log("  Regenerate last response     — Re-run the agent on your previous message")
            self._append_to_log("  Insert last Holix response   — Add previous assistant output as context")
            self._append_to_log("  Copy last assistant / tool   — Copy full content via clipboard protocol")
            self._append_to_log("  Session ▸ Show Current Info  — Quick stats (messages, tools in view)\n")

            self._append_to_log("[bold]Keybindings & Commands:[/bold]")
            self._append_to_log("  Enter                 — Send message")
            self._append_to_log("  Shift+Enter           — New line (multiline)")
            self._append_to_log("")
            self._append_to_log("  Mouse wheel / trackpad — Scroll chat (works best in iTerm2)")
            self._append_to_log("  When scrolled up + new output arrives → yellow banner appears above input")
            self._append_to_log("    Click the banner or Ctrl+End → jump to bottom + resume auto-scroll")
            self._append_to_log("")
            self._append_to_log("  Recommended macOS bindings (more reliable):")
            self._append_to_log("    Ctrl + ↑ / ↓        — Scroll line by line")
            self._append_to_log("    Ctrl + PageUp/Down  — Scroll by page")
            self._append_to_log("    Ctrl + u / d        — Scroll half page")
            self._append_to_log("    Ctrl + Home / End   — Jump to top / bottom")
            self._append_to_log("")
            self._append_to_log("  /stream               — Toggle live token streaming")
            self._append_to_log("  /clear                — Clear chat")
            self._append_to_log("  /metrics              — Show agent metrics")
            self._append_to_log("  /last [N]             — Show full (untruncated) output of last tool call")
            self._append_to_log("  /tools                — List recent tool calls (then use /last N)")
            self._append_to_log("                        (or use Ctrl+P → Tools ▸ for quick access to last result / rerun)")
            self._append_to_log("                        Tool calls now shown in structured panels with duration & syntax highlight")
            self._append_to_log("")
            self._append_to_log("  Sidebar sections        — Click titles to collapse/expand (Tools, Memory, etc.) — preferences saved")
            self._append_to_log("  Sidebar → Tools list  — Select + Enter to view tool description")
            self._append_to_log("  Sidebar → Memory list — Click to insert memory (recent or search results) as context")
            self._append_to_log("  Sidebar → Skills list — Select + Enter (or Ctrl+P 'skill') to view / insert skill")
            self._append_to_log("  /memory <query>       — Semantic search in long-term memory (results → chat + clickable in sidebar)")
            self._append_to_log("  /memory-clear         — Return Memory sidebar from search results to recent messages")
            self._append_to_log("  TAB                   — Autocomplete slash commands (/) — cycles through matches")
            self._append_to_log("  /new                  — Start a fresh conversation session")
            self._append_to_log("  /session name <name>  — Give the current session a human name")
            self._append_to_log("  /sessions             — List recent sessions")
            self._append_to_log("  /switch N             — Switch to session number N")
            self._append_to_log("  Ctrl+P → 'switch' or 'session' — Quick-switch recent sessions directly from palette")
            self._append_to_log("  /profile <name|N>     — Switch to another profile")
            self._append_to_log("  /yes /no              — Confirm or cancel profile switch")
            self._append_to_log("  /rerun, /rerun last   — Repeat the last tool call with same arguments")
            self._append_to_log("  /copy, /copy last     — Copy last tool result / response to clipboard")
            self._append_to_log("  Ctrl+P → 'copy'       — 'Copy last tool result' and 'Copy last assistant response' (recommended)")
            self._append_to_log("  /density compact|normal|comfort — Change interface density (saved across restarts)")
            self._append_to_log("  /reset-ui             — Reset saved density + sidebar collapse states + sidebar visibility")
            self._append_to_log("  /mode [name]          — Cycle or set execution mode (Shift+Tab to cycle)")
            self._append_to_log("  /stop                 — ⏹ Stop all running tasks immediately (agent, sub-agents, plan)")
            self._append_to_log("  /subagent-spawn <type> — Spawn sub-agent (researcher/coder/analyst/reviewer/writer)")
            self._append_to_log("  /subagent-list        — List all sub-agents and status")
            self._append_to_log("  /subagent-terminate <name> — Terminate a sub-agent")
            self._append_to_log("  /ltm-stats            — Show long-term memory statistics")
            self._append_to_log("  /1 /2 /3 /4           — Confirm/deny dangerous actions (or press number keys)")
            self._append_to_log("  /safety permissions   — List all active permission grants")
            self._append_to_log("  Ctrl+L                — Clear chat")
            self._append_to_log("  Ctrl+C                — Quit")
            self._append_to_log("  Ctrl+B                — Toggle sidebar (collapsed by default)")
            self._append_to_log("  Ctrl+P                — Open command palette")
            self._append_to_log("  In palette:")
            self._append_to_log("    • Type to filter")
            self._append_to_log("    • ↑↓ arrows to browse results → Enter to run (or click with mouse)")
            self._append_to_log("    • When an item is highlighted you will see a message in chat")
            self._append_to_log("  Mouse drag + Ctrl+C   — Select and copy any text in chat history")
            self._append_to_log("  Ctrl+Shift+C          — Quick copy of last tool result / message")
            self._append_to_log("  F1                    — This help\n")
        except Exception:
            pass

    def action_scroll_chat_up(self) -> None:
        """Scroll chat history up one line (disables auto-scroll)."""
        try:
            self._auto_scroll_chat = False
            self._update_scroll_indicator()
            chat_log = self._chat_log()
            chat_log.scroll_up()
        except Exception:
            pass

    def action_scroll_chat_down(self) -> None:
        """Scroll chat history down one line. Re-enable auto-scroll if at bottom."""
        try:
            chat_log = self._chat_log()
            chat_log.scroll_down()
            if self._is_chat_at_bottom(chat_log):
                self._auto_scroll_chat = True
            self._update_scroll_indicator()
        except Exception:
            pass

    def action_scroll_chat_page_up(self) -> None:
        """Scroll chat history up one page (disables auto-scroll)."""
        self._auto_scroll_chat = False
        self._update_scroll_indicator()
        try:
            chat_log = self._chat_log()
            chat_log.scroll_page_up()
        except Exception:
            pass

    def action_scroll_chat_page_down(self) -> None:
        """Scroll chat history down one page. Re-enable auto-scroll if at bottom."""
        try:
            chat_log = self._chat_log()
            chat_log.scroll_page_down()
            if self._is_chat_at_bottom(chat_log):
                self._auto_scroll_chat = True
            self._update_scroll_indicator()
        except Exception:
            pass

    def action_scroll_chat_top(self) -> None:
        """Jump to the very top of the chat history (disables auto-scroll)."""
        self._auto_scroll_chat = False
        self._update_scroll_indicator()
        try:
            chat_log = self._chat_log()
            chat_log.scroll_home(animate=False)
        except Exception:
            pass

    def action_scroll_chat_bottom(self) -> None:
        """Jump to the very bottom of the chat history and re-enable auto-scroll."""
        self._auto_scroll_chat = True
        self._update_scroll_indicator()
        try:
            chat_log = self._chat_log()
            chat_log.scroll_end(animate=False)
        except Exception:
            pass

    def action_jump_to_bottom(self) -> None:
        """Force jump to bottom and re-enable auto-scroll (useful after scrolling up)."""
        self._auto_scroll_chat = True
        self._update_scroll_indicator()
        try:
            chat_log = self._chat_log()
            chat_log.scroll_end(animate=False)
        except Exception:
            pass

    def action_focus_input(self) -> None:
        """Move focus back to the chat input (useful after using sidebar or palette)."""
        try:
            input_area = self.query_one("#input-area", TextArea)
            input_area.focus()
        except Exception:
            pass

    def action_rename_current_session(self) -> None:
        """Prompt to rename current session via input (simple flow)."""
        try:
            input_area = self.query_one("#input-area", TextArea)
            input_area.text = "/session name "
            input_area.focus()
            input_area.cursor_location = (0, len(input_area.text))
        except Exception:
            pass

    def action_scroll_chat_half_up(self) -> None:
        """Scroll chat up by approximately half a page (Ctrl+U style)."""
        try:
            self._auto_scroll_chat = False
            self._update_scroll_indicator()
            chat_log = self._chat_log()
            chat_log.scroll_relative(y=-15)
        except Exception:
            pass

    def action_scroll_chat_half_down(self) -> None:
        """Scroll chat down by approximately half a page (Ctrl+D style)."""
        try:
            chat_log = self._chat_log()
            chat_log.scroll_relative(y=15)
            if self._is_chat_at_bottom(chat_log):
                self._auto_scroll_chat = True
            self._update_scroll_indicator()
        except Exception:
            pass

    @staticmethod
    def _is_chat_at_bottom(chat_log: RichLog) -> bool:
        """Check if the chat log is scrolled to (or very near) the bottom."""
        return HolixChatLog.is_at_bottom(chat_log)

    def _on_chat_log_scrolled(self, scroll_y: float | None) -> None:
        """React to any scroll change on the chat log (mouse, trackpad, keyboard, etc.).

        This keeps the "new messages below" indicator in sync even if the user
        scrolls with mechanisms we don't explicitly handle in action_* methods.
        """
        try:
            chat_log = self._chat_log()
            at_bottom = self._is_chat_at_bottom(chat_log)

            changed = False
            if at_bottom and not self._auto_scroll_chat:
                self._auto_scroll_chat = True
                changed = True
            elif not at_bottom and self._auto_scroll_chat:
                self._auto_scroll_chat = False
                changed = True

            if changed:
                self._update_scroll_indicator()
        except Exception:
            pass

    def _update_sidebar(self) -> None:
        """Refresh sidebar values (used after toggling streaming etc.)."""
        try:
            model_widget = self.query_one("#sidebar-model", Static)
            # Prefer the actually resolved model over the raw profile value
            model_text = getattr(self, "_resolved_model", None) or self.config.model
            if getattr(self, "streaming_enabled", False):
                model_text += " [green](stream)[/green]"
            model_widget.update(model_text)

            # Make current profile more visible
            profile_widget = self.query_one("#sidebar-profile", Static)
            profile_widget.update(f"[bold]{self.profile}[/bold]")
        except Exception:
            pass

    def _update_sidebar_session(self) -> None:
        """Update any session-related info in sidebar (called on switch/new)."""
        try:
            status = self.query_one("#sidebar-status", Static)
            custom = self.session_names.get(self.conversation_id)
            current = custom or getattr(self, "session_display_name", "main")
            status.update(f"[green]Ready[/green]  [dim]({current})[/dim]")
        except Exception:
            pass

        self._refresh_header_subtitle()

    def _update_density_indicator(self) -> None:
        """Update the small density mode indicator in the sidebar header."""
        try:
            widget = self.query_one("#sidebar-density", Static)
            mode = self.density or "normal"
            widget.update(f"[dim]{mode}[/dim]")
        except Exception:
            pass

        self._refresh_header_subtitle()

    def _refresh_header_subtitle(self) -> None:
        """Keep a compact, always-visible status in the Header sub_title
        (profile • model • session • context [density]). This gives at-a-glance info
        even when the sidebar is closed (the default state).
        """
        try:
            sess = getattr(self, "session_display_name", None) or "main"
            # Keep session name short
            if len(sess) > 18:
                sess = sess[:15] + "…"
            dens = self.density or "normal"
            model = getattr(self, "_resolved_model", None) or self.config.model
            # Shorten very long model names
            if "/" in model:
                model = model.split("/")[-1]
            if len(model) > 22:
                model = model[:19] + "…"

            # Context usage display
            ctx_display = ""
            agent = getattr(self, "agent", None)
            if agent and hasattr(agent, "context_manager") and agent.context_manager:
                try:
                    # Use cached context usage if available
                    cached = getattr(self, "_cached_context_display", None)
                    if cached:
                        ctx_display = f" • {cached}"
                except Exception:
                    pass

            mode = self._execution_modes[self._execution_mode_index]
            mode_short = {"react": "ReAct", "plan_and_execute": "Plan", "hybrid": "Hybrid", "auto": "Auto"}.get(mode, mode)

            self.sub_title = f"{self.profile} • {model} • {sess} • {mode_short}{ctx_display} [{dens}]"
        except Exception:
            pass

    def _update_context_display(self) -> None:
        """Update the visual context usage bar and cached header display.

        Synchronous version — uses in-memory _recent_memories cache.
        For a full update from agent memory, call _update_context_display_async() instead.
        """
        try:
            agent = getattr(self, "agent", None)
            if not agent or not hasattr(agent, "context_manager") or not agent.context_manager:
                self._cached_context_display = None
                self._update_context_bar_widget(None, None, None)
                return

            # Count tokens from recent memories (in-memory cache)
            memories = getattr(self, "_recent_memories", []) or []
            if memories:
                # Convert recent memories to message format for token counting
                msg_list = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in memories if m.get("content")]
                usage = agent.context_manager.get_usage(msg_list)
                level = agent.context_manager.get_usage_level(msg_list)
                color_map = {"green": "green", "yellow": "yellow", "red": "red"}
                color = color_map.get(level, "white")

                from core.context.token_counter import TokenCounter
                used_str = TokenCounter.format_token_count(usage["used"])
                total_str = TokenCounter.format_token_count(usage["total"])
                percent = usage["percent"]

                # Update header cache
                self._cached_context_display = f"[{color}]{used_str}/{total_str}[/{color}]"

                # Update visual context bar
                self._update_context_bar_widget(percent, color, usage)
            else:
                self._cached_context_display = None
                self._update_context_bar_widget(None, None, None)
        except Exception:
            self._cached_context_display = None

    async def _update_context_display_async(self) -> None:
        """Update the context bar from the real agent memory (async SQLite read).

        This is the authoritative update — reads the full conversation history
        from the agent's memory database and counts tokens accurately.
        Used after agent responses and after loading conversation history.
        """
        try:
            agent = getattr(self, "agent", None)
            if not agent or not hasattr(agent, "context_manager") or not agent.context_manager:
                self._cached_context_display = None
                self._update_context_bar_widget(None, None, None)
                return

            # Read real conversation history from agent memory
            try:
                messages = await agent.memory.get_conversation(
                    self.conversation_id, limit=200
                )
            except Exception:
                messages = []

            if not messages:
                # Show empty context bar with total size info
                total = agent.context_manager.context_window
                from core.context.token_counter import TokenCounter
                total_str = TokenCounter.format_token_count(total)
                self._update_context_bar_widget(0.0, "green", {
                    "used": 0, "total": total, "percent": 0.0,
                })
                self._cached_context_display = f"[green]0/{total_str}[/green]"
                return

            usage = agent.context_manager.get_usage(messages)
            level = agent.context_manager.get_usage_level(messages)
            color_map = {"green": "green", "yellow": "yellow", "red": "red"}
            color = color_map.get(level, "white")

            from core.context.token_counter import TokenCounter
            used_str = TokenCounter.format_token_count(usage["used"])
            total_str = TokenCounter.format_token_count(usage["total"])
            percent = usage["percent"]

            # Update header cache
            self._cached_context_display = f"[{color}]{used_str}/{total_str}[/{color}]"

            # Update visual context bar
            self._update_context_bar_widget(percent, color, usage)
        except Exception:
            self._cached_context_display = None

    def _update_context_bar_widget(
        self,
        percent: float | None,
        color: str | None,
        usage: dict[str, Any] | None,
    ) -> None:
        """Update the #context-bar Static widget with a visual progress bar.

        Shows a Unicode block-based progress bar + percentage + token counts.
        Color-coded: green < 70%, yellow 70-89%, red >= 90%.

        Args:
            percent: Usage percent (0-100). None = no agent yet.
            color: Rich color name ("green", "yellow", "red").
            usage: Dict from ContextManager.get_usage().
        """
        try:
            bar_widget = self.query_one("#context-bar", Static)
        except Exception:
            return

        try:
            if percent is None or color is None or usage is None:
                bar_widget.update("[dim]Context: ──[/dim]")
                return

            from core.context.token_counter import TokenCounter
            used_str = TokenCounter.format_token_count(usage["used"])
            total_str = TokenCounter.format_token_count(usage["total"])

            # Build Unicode progress bar (10 blocks wide)
            bar_width = 10
            filled = min(bar_width, int(percent / 100 * bar_width))
            empty = bar_width - filled

            # Use block characters: █ for filled, ░ for empty
            filled_bar = "█" * filled
            empty_bar = "░" * empty

            # Color the entire bar + text
            bar_text = f"[{color}]▌{filled_bar}{empty_bar}▐[/{color}]"
            percent_text = f"[{color}]{percent:.0f}%[/{color}]"
            count_text = f"[dim]{used_str}/{total_str}[/dim]"

            bar_widget.update(f"Context: {bar_text} {percent_text} {count_text}")
        except Exception:
            try:
                bar_widget.update("[dim]Context: ──[/dim]")
            except Exception:
                pass

    def _rename_current_session(self, name: str) -> None:
        """Give the current session a human-friendly name."""
        if not name or not self.conversation_id:
            return
        self.session_names[self.conversation_id] = name.strip()
        self.session_display_name = name.strip()
        self._update_sidebar_session()
        self._persist_ui_state()
        try:
            self._append_to_log(f"[green]Session renamed to: {name.strip()}[/green]")
        except Exception:
            pass

        # Robustness: after rename the user typically wants to continue chatting
        self._restore_input_focus(delay=0.04)

    def action_show_session_info(self) -> None:
        """Print basic current session info (quick stats)."""
        try:
            self._chat_log()
            name = self.session_display_name or self.conversation_id
            mem_count = len(self._recent_memories)
            tool_count = len(self._recent_tool_results)
            self._append_to_log(f"\n[dim]Session: {name}[/dim]")
            self._append_to_log(f"[dim]  Recent messages in view: {mem_count}  •  Tool results: {tool_count}[/dim]")
            # Show context usage
            agent = getattr(self, "agent", None)
            if agent and hasattr(agent, "context_manager") and agent.context_manager:
                msg_list = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in (self._recent_memories or []) if m.get("content")]
                if msg_list:
                    usage = agent.context_manager.get_usage(msg_list)
                    level = agent.context_manager.get_usage_level(msg_list)
                    color_map = {"green": "green", "yellow": "yellow", "red": "red"}
                    color = color_map.get(level, "white")
                    ctx_str = agent.context_manager.format_usage_display(msg_list)
                    self._append_to_log(f"[dim]  Context: [{color}]{ctx_str}[/{color}] (window: {usage['total']:,} tokens)[/dim]")
            self._append_to_log("")
        except Exception:
            pass

    async def _handle_compress_command(self) -> None:
        """Handle /compress slash command — manually compress conversation context."""
        try:
            agent = getattr(self, "agent", None)
            if not agent or not hasattr(agent, "context_manager") or not agent.context_manager:
                self._append_to_log("[yellow]Context compression not available.[/yellow]")
                return

            if not agent.context_manager.compressor:
                self._append_to_log("[yellow]ContextCompressor not configured.[/yellow]")
                return

            self._append_to_log("[dim]Compressing context...[/dim]")

            messages = await agent.memory.get_conversation(self.conversation_id, limit=200)
            compressed, was_compressed = await agent.context_manager.compress_context(messages)

            if was_compressed:
                from core.profile.soul import inject_soul_into_messages

                compressed = inject_soul_into_messages(compressed, self.profile)
                usage_before = agent.token_counter.count_message_tokens(messages)
                usage_after = agent.token_counter.count_message_tokens(compressed)
                self._append_to_log(
                    f"[green]⚡ Context compressed:[/green] "
                    f"{usage_before:,} → {usage_after:,} tokens "
                    f"({len(messages)} → {len(compressed)} messages)"
                )
                # Persist the compressed conversation — replace old messages in DB
                try:
                    await agent.memory.replace_conversation_messages(
                        self.conversation_id, compressed
                    )
                    self._append_to_log("[dim]Compressed context saved to memory.[/dim]")
                except Exception as persist_err:
                    # Fallback: save summary as system message
                    if agent.context_manager.last_summary:
                        await agent.memory.save_message(
                            self.conversation_id, "system",
                            f"Context compressed. Summary of previous conversation:\n\n{agent.context_manager.last_summary}",
                            metadata={"type": "context_compression"},
                        )
                    self._append_to_log(f"[yellow]Warning: could not fully persist: {persist_err}[/yellow]")
            else:
                self._append_to_log("[dim]Not enough messages to compress.[/dim]")

            await self._update_context_display_async()
            self._refresh_header_subtitle()
        except Exception as e:
            self._append_to_log(f"[red]Compression error: {e}[/red]")

    # --- Light Debug / Introspection (Wave 8 B) ---

    def action_debug_show_context(self) -> None:
        """Show recent conversation context (light debugging view)."""
        self.run_worker(self._debug_show_context())

    async def _debug_show_context(self) -> None:
        try:
            self._chat_log()
            if not self.agent:
                self._append_to_log("[yellow]Agent not ready.[/yellow]")
                return

            history = await self.agent.get_conversation_history(self.conversation_id, limit=8)
            self._append_to_log("\n[bold magenta]Debug ▸ Recent Context (last 8 messages):[/bold magenta]")
            for msg in history:
                role = msg.get("role", "?")
                content = str(msg.get("content", ""))[:120].replace("\n", " ")
                marker = {"user": "You", "assistant": "Holix", "tool": "Tool"}.get(role, role)
                self._append_to_log(f"  [dim]{marker}:[/dim] {content}...")
            self._append_to_log("[dim]Use full agent memory for deeper inspection.[/dim]\n")
        except Exception as e:
            self._append_to_log(f"[red]Debug context failed: {e}[/red]")

    def action_debug_show_tools(self) -> None:
        """Show loaded tools (debug view)."""
        try:
            self._chat_log()
            if not self.agent:
                self._append_to_log("[yellow]Agent not ready.[/yellow]")
                return
            tools = self.agent.get_tools() or []
            self._append_to_log("\n[bold magenta]Debug ▸ Loaded Tools:[/bold magenta]")
            for t in tools:
                self._append_to_log(f"  • {t}")
            if not tools:
                self._append_to_log("  (no tools)")
            self._append_to_log("")
        except Exception as e:
            self._append_to_log(f"[red]Debug tools failed: {e}[/red]")

    def action_debug_show_skills(self) -> None:
        """Show loaded skills (debug view)."""
        try:
            self._chat_log()
            if not self.agent:
                self._append_to_log("[yellow]Agent not ready.[/yellow]")
                return
            skills = self.agent.get_skills() or {}
            self._append_to_log("\n[bold magenta]Debug ▸ Loaded Skills:[/bold magenta]")
            for name, skill in skills.items():
                desc = str(skill.get("description", ""))[:80] if isinstance(skill, dict) else ""
                self._append_to_log(f"  • {name}: {desc}")
            if not skills:
                self._append_to_log("  (no skills)")
            self._append_to_log("")
        except Exception as e:
            self._append_to_log(f"[red]Debug skills failed: {e}[/red]")

    def _populate_tools_list(self) -> None:
        """Populate the Tools list in the sidebar from the agent's ToolRegistry.
        Improved display: name + very short description (Phase 1 polish).
        """
        try:
            tools_list = self.query_one("#tools-list", ListView)
            tools_list.clear()

            if not self.agent or not hasattr(self.agent, "tools"):
                tools_list.append(ListItem(Static("[dim]No tools loaded yet[/dim]")))
                try:
                    tools_coll = self.query_one("#tools-collapsible", Collapsible)
                    tools_coll.title = "Tools (0)"
                except Exception:
                    pass
                return

            tools_dict = self.agent.tools.tools
            self._available_tools = []

            for tool_name, tool in sorted(tools_dict.items()):
                desc = getattr(tool, "description", "") or ""
                # Store for later use (click handler etc.)
                self._available_tools.append({
                    "name": tool_name,
                    "description": desc,
                })

                # Improved compact display for narrow sidebar
                short_desc = desc.split(".")[0][:25] if desc else ""
                if short_desc:
                    label = f"{tool_name} — {short_desc}"
                else:
                    label = tool_name

                # Truncate for width 22 sidebar
                if len(label) > 19:
                    label = label[:16] + "…"

                item = ListItem(Static(label))
                tools_list.append(item)

            if not self._available_tools:
                tools_list.append(ListItem(Static("[dim]No tools registered[/dim]")))
                try:
                    tools_coll = self.query_one("#tools-collapsible", Collapsible)
                    tools_coll.title = "Tools (0)"
                except Exception:
                    pass
            else:
                try:
                    tools_coll = self.query_one("#tools-collapsible", Collapsible)
                    tools_coll.title = f"Tools ({len(self._available_tools)})"
                except Exception:
                    pass

        except Exception:
            pass  # Sidebar may not be ready yet — fail silently

    def _populate_memory_list(self, recent_messages: list | None = None) -> None:
        """Populate compact recent memory list in sidebar from conversation history."""
        try:
            mem_list = self.query_one("#memory-list", ListView)
            mem_list.clear()
            self._recent_memories = []

            # Reset Memory collapsible title when back to recent mode (Phase 2 search UI)
            try:
                coll = self.query_one("#memory-collapsible", Collapsible)
                if coll:
                    coll.title = "Memory"
            except Exception:
                pass

            messages = recent_messages or []

            # If no messages passed, try to load from agent (sync-safe fallback)
            if not messages and self.agent:
                try:
                    # Use create_task pattern in real async context is better,
                    # but for PoC we accept the limitation here.
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule for later; for now just show what we have
                        messages = []
                    else:
                        messages = loop.run_until_complete(
                            self.agent.get_conversation_history(self.conversation_id, limit=10)
                        )
                except Exception:
                    messages = []

            # Take last 6 user/assistant messages for sidebar
            relevant = [m for m in messages if m.get("role") in ("user", "assistant")][-6:]

            for msg in relevant:
                role = msg.get("role", "")
                content = str(msg.get("content", ""))[:120]
                short = content.replace("\n", " ")[:45] + ("…" if len(content) > 45 else "")

                self._recent_memories.append({
                    "role": role,
                    "content": msg.get("content", ""),
                    "short": short,
                })

                prefix = "U:" if role == "user" else "A:"
                label = f"{prefix} {short}"
                mem_list.append(ListItem(Static(label)))

            if not self._recent_memories:
                mem_list.append(ListItem(Static("[dim]No recent memory yet[/dim]")))

        except Exception:
            pass

    def _refresh_memory_sidebar(self) -> None:
        """Quick refresh of memory list (call after new messages)."""
        # Best effort: reload last messages and repopulate
        self._populate_memory_list()

    def _populate_memory_search_results(self, results: list[dict], query: str) -> None:
        """Phase 2: Populate Memory sidebar ListView with semantic search hits (search mode)."""
        try:
            mem_list = self.query_one("#memory-list", ListView)
            mem_list.clear()
            self._memory_search_results = results or []
            self._memory_search_query = query or ""
            self._memory_search_active = bool(self._memory_search_results)

            # Dynamic title on the Collapsible to indicate search mode (best-effort)
            try:
                coll = self.query_one("#memory-collapsible", Collapsible)
                if coll:
                    qshort = (query or "")[:25]
                    coll.title = f"Memory — 🔍 {qshort}" if qshort else "Memory — Search"
            except Exception:
                pass

            if not self._memory_search_results:
                mem_list.append(ListItem(Static("[dim]No relevant memories found[/dim]")))
                self._memory_search_active = False
                return

            for mem in self._memory_search_results:
                content = str(mem.get("content", ""))[:100].replace("\n", " ")
                short = content[:50] + ("…" if len(content) > 50 else "")
                role = mem.get("metadata", {}).get("role", "?")
                label = f"[S] {role}: {short}"
                mem_list.append(ListItem(Static(label)))

            # Note: mode info + how to exit is printed to chat log by caller
        except Exception:
            pass

    def _clear_memory_search(self) -> None:
        """Exit search mode and restore recent conversation memory in sidebar."""
        if not self._memory_search_active:
            return
        self._memory_search_active = False
        self._memory_search_results = []
        self._memory_search_query = ""
        # Repopulate with recent msgs for current conv (also resets title via _populate_memory_list)
        self._populate_memory_list()

        # Small UX: after clearing search mode, user usually wants to type next query or message
        self._restore_input_focus(delay=0.03)

    def _populate_sessions_list(self) -> None:
        """Populate the Sessions list in sidebar with recent conversations."""
        try:
            sess_list = self.query_one("#sessions-list", ListView)
            sess_list.clear()

            # Dynamic Collapsible title with count.
            try:
                coll = self.query_one("#sessions-collapsible", Collapsible)
                if coll:
                    n = len(self.known_sessions or [])
                    coll.title = f"Sessions ({n})" if n else "Sessions"
            except Exception:
                pass

            if not self.known_sessions:
                sess_list.append(ListItem(Static("[dim]No other sessions yet[/dim]")))
                return

            for i, sess in enumerate(self.known_sessions[:8]):  # limit for narrow sidebar
                cid = sess.get("conversation_id", "")
                count = sess.get("message_count", 0)
                short = self._get_short_session_name(cid)

                # Phase 2 polish: show last activity hint
                last_ts = sess.get("last_timestamp")
                last_hint = ""
                if last_ts:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                        delta = datetime.now(UTC) - dt
                        if delta.days > 0:
                            last_hint = f" {delta.days}d ago"
                        elif delta.seconds > 3600:
                            last_hint = f" {delta.seconds // 3600}h ago"
                        else:
                            last_hint = f" {delta.seconds // 60}m ago"
                    except Exception:
                        pass

                # Phase 2 polish: stronger visual for current session
                if cid == self.conversation_id:
                    label = f"[bold cyan]→ {short} ({count}){last_hint}  [current][/bold cyan]"
                else:
                    label = f"  {short} ({count}){last_hint}"

                sess_list.append(ListItem(Static(label)))

        except Exception:
            pass

    def _populate_skills_list(self) -> None:
        """Populate Skills list in sidebar (Phase 2) — now first-class with dynamic title + tags."""
        try:
            skills_list = self.query_one("#skills-list", ListView)
            skills_list.clear()

            # Dynamic Collapsible title
            try:
                coll = self.query_one("#skills-collapsible", Collapsible)
                if coll:
                    # count will be known after loading
                    pass  # will set after
            except Exception:
                pass

            if not self.agent:
                skills_list.append(ListItem(Static("[dim]No agent[/dim]")))
                try:
                    coll = self.query_one("#skills-collapsible", Collapsible)
                    if coll:
                        coll.title = "Skills"
                except Exception:
                    pass
                return

            skills_dict = self.agent.get_skills() or {}
            self._available_skills = []

            for name, skill in sorted(skills_dict.items()):
                desc = skill.get("description", "") or ""
                tags = skill.get("tags", []) or []

                self._available_skills.append({
                    "name": name,
                    "description": desc,
                    "tags": tags,
                })

                # Phase 2 polish: show short name + first tag(s) for quick recognition
                short = name if len(name) <= 16 else name[:13] + "…"
                tag_hint = f" [{tags[0]}]" if tags else ""
                label = f"{short}{tag_hint}"

                skills_list.append(ListItem(Static(label)))

            count = len(self._available_skills)
            try:
                coll = self.query_one("#skills-collapsible", Collapsible)
                if coll:
                    coll.title = f"Skills ({count})" if count else "Skills"
            except Exception:
                pass

            if count == 0:
                skills_list.append(ListItem(Static("[dim]No skills loaded yet[/dim]")))

        except Exception:
            pass

    def _populate_profiles_list(self) -> None:
        """Populate visual Profiles list in sidebar (Phase 2) — now consistent with other sections."""
        try:
            profiles_list = self.query_one("#profiles-list", ListView)
            profiles_list.clear()

            # Dynamic Collapsible title
            try:
                coll = self.query_one("#profiles-collapsible", Collapsible)
                if coll:
                    pass  # set after count known
            except Exception:
                pass

            self._available_profiles = self._get_available_profiles()

            for prof in self._available_profiles:
                if prof == self.profile:
                    label = f"[bold cyan]→ {prof}  [current][/bold cyan]"
                else:
                    label = f"  {prof}"

                profiles_list.append(ListItem(Static(label)))

            count = len(self._available_profiles)
            try:
                coll = self.query_one("#profiles-collapsible", Collapsible)
                if coll:
                    coll.title = f"Profiles ({count})" if count else "Profiles"
            except Exception:
                pass

            if count == 0:
                profiles_list.append(ListItem(Static("[dim]No profiles found[/dim]")))

        except Exception:
            pass

    def _get_available_profiles(self) -> list[str]:
        """Return list of available profiles."""
        try:
            return self.profile_manager.list_profiles()
        except Exception:
            return ["default"]

    async def _switch_profile(self, new_profile: str, *, profile_key: str | None = None) -> None:
        """Switch to a different profile (Phase 2 feature)."""
        from core.profile_keys import ProfileKeyError, profile_has_access_key

        self._chat_log()

        if new_profile == self.profile:
            self._append_to_log(f"[yellow]Already using profile '{new_profile}'.[/yellow]")
            return

        self._append_to_log(f"\n[yellow]Switching to profile '{new_profile}'...[/yellow]")

        try:
            new_config = init_profile(new_profile, profile_key=profile_key, prompt_key=False)

            # Unsubscribe old agent from events
            if self.agent and hasattr(self.agent, 'events'):
                # Best effort - we can't easily unsubscribe, so we'll just stop using it
                pass

            from core.di import resolve_runtime_config

            runtime_config = resolve_runtime_config(new_config)
            try:
                from core.models.manager import ModelManager

                model_config = ModelManager(new_config).get_default_model_config()
                if model_config:
                    runtime_config = runtime_config.with_overrides(
                        model=model_config.model,
                        base_url=model_config.base_url,
                        api_key=model_config.api_key,
                        temperature=model_config.temperature,
                    )
            except Exception:
                pass

            new_agent = HolixAgent(config=runtime_config)
            resolved_model = runtime_config.model

            # Initialize new agent
            await new_agent.initialize()

            # Switch references
            self.agent = new_agent
            self.profile = new_profile
            self.config = new_config
            self._resolved_model = resolved_model

            # Re-subscribe to events
            self.agent.events.subscribe(self._on_agent_event)

            # Update UI
            self._update_sidebar()
            self._populate_tools_list()
            self._populate_skills_list()
            self._populate_memory_list()
            self._populate_profiles_list()

            self._append_to_log(f"[green]Successfully switched to profile '{new_profile}'.[/green]")
            self._append_to_log(f"[dim]Using model: {resolved_model}[/dim]\n")

            self._refresh_header_subtitle()

            # Reset per-session power-user state on profile switch
            self._last_user_message = None
            self._first_delta_seen = False
            self._last_tool_call = None

            # Record in switch history
            from datetime import datetime
            self.profile_switch_history.append({
                "profile": new_profile,
                "timestamp": datetime.now().isoformat(),
            })
            # Keep only last 10
            if len(self.profile_switch_history) > 10:
                self.profile_switch_history.pop(0)

            # Start fresh session for the new profile (clean experience)
            await self._create_new_session()

        except ProfileKeyError as exc:
            self._append_to_log(f"[red]{exc}[/red]")
            if profile_has_access_key(new_profile) and not profile_key:
                self._append_to_log("[dim]Use: /profile <name> <access-key>[/dim]\n")
        except Exception as e:
            self._append_to_log(f"[red]Failed to switch to profile '{new_profile}': {e}[/red]\n")

    async def _show_profile_switcher(self) -> None:
        """Show list of profiles and allow switching (simple version for PoC)."""
        self._chat_log()
        profiles = self._get_available_profiles()

        if not profiles:
            self._append_to_log("[yellow]No profiles found.[/yellow]")
            return

        self._append_to_log("\n[bold cyan]Available Profiles:[/bold cyan]")
        for i, prof in enumerate(profiles, 1):
            marker = " ← current" if prof == self.profile else ""
            self._append_to_log(f"  {i}. {prof}{marker}")

        self._append_to_log("\n[dim]Use /profile <name> or /profile <number> to switch.[/dim]\n")

    # --- Slash command autocomplete (dropdown in input) ---

    def _fuzzy_score(self, query: str, text: str) -> int:
        """Simple but effective fuzzy score (higher = better match)."""
        if not query:
            return 100
        query = query.lower()
        text_lower = text.lower()

        if query in text_lower:
            return 1000 - (text_lower.find(query) * 5)  # strong bonus for substring

        score = 0
        q_idx = 0
        for char in text_lower:
            if q_idx < len(query) and char == query[q_idx]:
                score += 10
                q_idx += 1
                if q_idx == len(query):
                    break
        if q_idx == len(query):
            score += 50  # bonus for matching all characters (fuzzy)
        return score

    def _update_command_suggestions(self, current_text: str) -> None:
        """Show or hide the command suggestions dropdown with fuzzy search.
        Note: Slash commands (/) now use TAB completion instead of dropdown (see on_key).
        """
        suggestions_widget = self.query_one("#command-suggestions", ListView)

        # If we just inserted via the dropdown, ignore the immediate text change
        if self._just_inserted_suggestion:
            self._just_inserted_suggestion = False
            self._hide_command_suggestions()
            return

        lines = current_text.splitlines()
        current_line = lines[-1] if lines else ""

        if not current_line.startswith("/"):
            self._hide_command_suggestions()
            return

        typed = current_line[1:].strip()

        # Score all commands with fuzzy matching
        scored = []
        for cmd, desc in self._all_slash_commands:
            cmd_clean = cmd[1:]  # remove leading /
            score = self._fuzzy_score(typed, cmd_clean)
            if score > 0:
                scored.append((score, cmd, desc))

        if not scored:
            self._hide_command_suggestions()
            return

        # Sort by score descending
        scored.sort(reverse=True)
        matches = [(cmd, desc) for _, cmd, desc in scored[:8]]

        # Rebuild list with nicer formatting
        suggestions_widget.clear()
        for cmd, desc in matches:
            # Nicer visual: command in accent, description dim
            label = f"[bold cyan]{cmd}[/bold cyan]  [dim]{desc}[/dim]"
            suggestions_widget.append(ListItem(Static(label)))

        self._suggestion_commands = matches

        # Show and highlight first item
        self._show_command_suggestions()
        if suggestions_widget.children:
            suggestions_widget.index = 0

    def _show_command_suggestions(self) -> None:
        suggestions_widget = self.query_one("#command-suggestions", ListView)
        if not self._suggestions_visible:
            suggestions_widget.add_class("-visible")
            self._suggestions_visible = True
        # Do NOT auto-highlight here. Only highlight when user presses arrows.
        # This way, if user types a full command and presses Enter, it will send instead of selecting.

    def _hide_command_suggestions(self) -> None:
        suggestions_widget = self.query_one("#command-suggestions", ListView)
        if self._suggestions_visible:
            suggestions_widget.remove_class("-visible")
            suggestions_widget.clear()
            self._suggestions_visible = False
            self._suggestion_commands = []
        self._just_inserted_suggestion = False

    def _handle_slash_tab_completion(self) -> None:
        """Handle TAB autocompletion for slash commands (replacement for the old dropdown + Enter flow)."""
        try:
            input_area = self.query_one("#input-area", TextArea)
            lines = input_area.text.splitlines()
            if not lines:
                return
            current_line = lines[-1]

            if not current_line.startswith("/"):
                return

            typed = current_line[1:].strip()

            # Recompute matches if query changed
            if typed != self._tab_last_line:
                scored = []
                for cmd, desc in self._all_slash_commands:
                    cmd_clean = cmd[1:]
                    score = self._fuzzy_score(typed, cmd_clean)
                    if score > 0:
                        scored.append((score, cmd))

                scored.sort(reverse=True)
                self._tab_completion_matches = [cmd for _, cmd in scored[:10]]
                self._tab_completion_index = -1
                self._tab_last_line = typed

            if not self._tab_completion_matches:
                return

            # Cycle through matches
            self._tab_completion_index = (self._tab_completion_index + 1) % len(self._tab_completion_matches)
            chosen = self._tab_completion_matches[self._tab_completion_index]

            # Replace the current line with the chosen command + space
            lines[-1] = chosen + " "
            input_area.text = "\n".join(lines)

            # Move cursor to end
            row = len(input_area.text.splitlines()) - 1
            input_area.cursor_location = (row, len(chosen) + 1)

            input_area.focus()
        except Exception:
            pass

    def _insert_selected_command(self) -> None:
        """Insert the selected command from the dropdown into the input field.
        Does NOT auto-execute. The user presses Enter normally to send.
        """
        if not self._suggestions_visible or not self._suggestion_commands:
            return

        suggestions_widget = self.query_one("#command-suggestions", ListView)

        highlighted = suggestions_widget.highlighted_child
        if not highlighted:
            if self._suggestion_commands:
                cmd = self._suggestion_commands[0][0]
            else:
                return
        else:
            try:
                index = suggestions_widget.children.index(highlighted)
            except ValueError:
                return
            if index >= len(self._suggestion_commands):
                return
            cmd = self._suggestion_commands[index][0]

        try:
            input_area = self.query_one("#input-area", TextArea)

            # Replace current line with the command + space (ready for arguments or immediate send)
            lines = input_area.text.splitlines()
            if lines:
                lines[-1] = cmd + " "
                input_area.text = "\n".join(lines)
            else:
                input_area.text = cmd + " "

            # Place cursor after the command
            row = len(input_area.text.splitlines()) - 1
            input_area.cursor_location = (row, len(cmd) + 1)

            self._hide_command_suggestions()
            self._just_inserted_suggestion = False
            input_area.focus()
        except Exception:
            pass

    # --- Sessions (Phase 1 multi-conversation support) ---

    async def _load_known_sessions(self) -> None:
        """Load recent conversations from memory DB."""
        if not self.agent:
            return
        try:
            self.known_sessions = await self.agent.list_conversations(limit=12)
        except Exception:
            self.known_sessions = []

    def _get_short_session_name(self, conv_id: str) -> str:
        """Create a short human-friendly name for a conversation id."""
        # Prefer user-given name if available
        if conv_id in self.session_names:
            return self.session_names[conv_id]
        if conv_id == self.conversation_id:
            return "current"
        # Try to make it short
        if "_" in conv_id:
            parts = conv_id.split("_")
            return parts[-1][:8]
        return conv_id[:10]

    async def _create_new_session(self) -> None:
        """Create and switch to a brand new conversation."""
        import time
        new_id = f"tui_{self.profile}_{int(time.time())}"
        self.conversation_id = new_id
        self.session_display_name = self._get_short_session_name(new_id)

        self._chat_log()
        self._append_to_log(f"\n[bold cyan]=== New session started: {self.session_display_name} ===[/bold cyan]\n")

        # Clear UI state for new session
        self._recent_memories.clear()
        # Phase 2: also exit memory search mode for fresh context
        self._memory_search_active = False
        self._memory_search_results.clear()
        self._memory_search_query = ""
        self._first_delta_seen = False
        self._last_user_message = None
        self._is_streaming = False
        self._next_response_is_regenerated = False
        try:
            mem_list = self.query_one("#memory-list", ListView)
            mem_list.clear()
            mem_list.append(ListItem(Static("[dim]No recent memory[/dim]")))
        except Exception:
            pass

        self._update_sidebar_session()
        self._refresh_memory_sidebar()

        # Reload known sessions list + UI
        await self._load_known_sessions()
        self._populate_sessions_list()

        # Reset context bar for the new empty session
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self._append_to_log(f"[dim]Model for this session: {restored}[/dim]\n")
        await self._update_context_display_async()
        self._refresh_header_subtitle()

        # Robustness: always return focus to input after creating a fresh session
        self._restore_input_focus(delay=0.06, force=True)

    async def _switch_to_session(self, index: int) -> None:
        """Switch to one of the known sessions by 1-based index."""
        if not self.known_sessions or index < 1 or index > len(self.known_sessions):
            chat_log = self._chat_log()
            self._append_to_log("[yellow]Invalid session number. Use /sessions to list.[/yellow]")
            return

        target = self.known_sessions[index - 1]
        new_id = target["conversation_id"]

        if new_id == self.conversation_id:
            return

        self.conversation_id = new_id
        self.session_display_name = self._get_short_session_name(new_id)

        chat_log = self._chat_log()
        chat_log.clear()
        self._append_to_log(f"[bold cyan]Switched to session {index}: {new_id}[/bold cyan]\n")

        # Reload history for the new session
        await self._load_conversation_history(chat_log)
        self._update_sidebar_session()
        self._refresh_memory_sidebar()

        # Refresh sessions list UI
        self._populate_sessions_list()

        # Update context bar for the switched session
        from core.session_models import restore_session_model

        restored = restore_session_model(self)
        if restored:
            self._append_to_log(f"[dim]Model for this session: {restored}[/dim]\n")
        await self._update_context_display_async()
        self._refresh_header_subtitle()

        # Robustness: return focus after session switch
        self._restore_input_focus(delay=0.05, force=True)

    def on_key(self, event: events.Key) -> None:
        """
        Global key handler.
        Handles:
        - TAB autocompletion for slash commands (replacing the old dropdown + Enter behavior)
        - Arrow navigation for the (now mostly disabled for /) suggestions dropdown
        - Number keys 1-4 for confirmation prompts
        """
        try:
            # Number keys 1-4 for confirmation prompts (handled by modal if active)
            # These are now handled by the ConfirmationModal directly

            # TAB autocompletion for slash commands
            if event.key == "tab":
                if self.focused and getattr(self.focused, "id", None) == "input-area":
                    self._handle_slash_tab_completion()
                    event.prevent_default()
                    event.stop()
                    return

            # When Command Palette is open we stay completely out of the way
            if CommandPalette.is_open(self):
                return

            # Only handle arrows for the suggestions dropdown (legacy support).
            # Main slash completion now uses TAB.
            if self._suggestions_visible:
                suggestions = self.query_one("#command-suggestions", ListView)

                if event.key == "up":
                    event.prevent_default()
                    event.stop()
                    suggestions.action_cursor_up()
                    return

                if event.key == "down":
                    event.prevent_default()
                    event.stop()
                    suggestions.action_cursor_down()
                    return
        except Exception:
            # Never let a key handling error kill the TUI
            pass

    def on_text_area_key(self, event: events.Key) -> None:
        """
        Полностью контролируем поведение Enter в поле ввода.
        Сразу делаем prevent_default(), чтобы TextArea гарантированно не вставил перенос строки.
        """
        if event.key != "enter":
            return

        # === ВАЖНО: сразу предотвращаем дефолтное поведение TextArea ===
        event.prevent_default()
        event.stop()

        if event.shift:
            # Shift+Enter → вставляем перенос строки вручную
            try:
                input_area = self.query_one("#input-area", TextArea)
                input_area.insert("\n")
            except Exception:
                pass
            return

        # === Обычный Enter ===

        if self._suggestions_visible:
            suggestions = self.query_one("#command-suggestions", ListView)
            if suggestions.highlighted_child is not None:
                # Пользователь выбрал пункт стрелками → вставляем команду
                self._insert_selected_command()
                return
            else:
                # Меню открыто, но ничего не выбрано → закрываем его
                self._hide_command_suggestions()

        # Отправляем сообщение
        self.action_send_message()

    def _set_status(self, text: str, style: str = "") -> None:
        """Update the status label in the sidebar and header (for better visibility)."""
        try:
            status_widget = self.query_one("#sidebar-status", Static)
            if style:
                status_widget.update(f"[{style}]{text}[/{style}]")
            else:
                status_widget.update(text)
        except Exception:
            pass

        # Also reflect important states in the header subtitle (rich version)
        try:
            if "Thinking" in text or text == "Error":
                self.sub_title = f"{self.profile} • {self.config.model} • {text}"
            elif text == "Ready":
                self._refresh_header_subtitle()
        except Exception:
            pass

    # --- Scroll indicator helpers (stabilization feature) ---

    def _show_scroll_indicator(self) -> None:
        """Show the 'new messages below' indicator."""
        try:
            indicator = self.query_one("#scroll-indicator", Button)
            indicator.add_class("-visible")
        except Exception:
            pass

    def _hide_scroll_indicator(self) -> None:
        """Hide the scroll indicator."""
        try:
            indicator = self.query_one("#scroll-indicator", Button)
            indicator.remove_class("-visible")
        except Exception:
            pass

    def _update_scroll_indicator(self) -> None:
        """Show or hide the indicator based on current auto-scroll state."""
        if self._auto_scroll_chat:
            self._hide_scroll_indicator()
        else:
            self._show_scroll_indicator()

    # --- Long tool results helpers (Вариант 1 stabilization) ---

    def _store_tool_result(self, name: str, full_result: str, duration_ms: int | None = None) -> None:
        """Store full tool (or error) output so user can retrieve it later with /last."""
        try:
            entry = {
                "name": name,
                "full_result": full_result,
            }
            if duration_ms is not None:
                entry["duration_ms"] = duration_ms
            self._recent_tool_results.append(entry)
            # Keep only last 8 results to avoid unbounded memory growth in long sessions
            if len(self._recent_tool_results) > 8:
                self._recent_tool_results.pop(0)
        except Exception:
            pass

    def _show_full_tool_result(self, index_from_end: int = 0) -> None:
        """Print the full (untruncated) result of a recent tool call into the chat."""
        self._chat_log()
        if not self._recent_tool_results:
            self._append_to_log("[yellow]No tool results in this session yet.[/yellow]")
            return

        try:
            idx = -(index_from_end + 1)  # 0 = last, 1 = second last, etc.
            entry = self._recent_tool_results[idx]
            name = entry["name"]
            full = entry["full_result"]

            # Pretty header
            duration_part = ""
            if "duration_ms" in entry:
                duration_part = f" ({entry['duration_ms']:.0f}ms)"

            if name.startswith("ERROR:"):
                clean_name = name[6:]
                header = f"[bold red]Full error for: {clean_name}{duration_part}[/bold red]"
                panel_title = "[bold red]Tool Error (full)[/bold red]"
                border = "red"
            else:
                header = f"[bold cyan]Full output for: {name}{duration_part}[/bold cyan] (most recent if index omitted)"
                panel_title = "[bold]Tool Result (full)[/bold]"
                border = "cyan"

            self._append_to_log("\n" + header)

            # Structured viewing for tool results (Wave 8 A improvement)
            display_content = full
            try:
                if full.strip().startswith(("{", "[")):
                    import json
                    parsed = json.loads(full)
                    # Pretty print with indentation
                    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
                    display_content = Syntax(pretty, "json", theme="monokai", line_numbers=False, word_wrap=True)
            except Exception:
                # Not valid JSON or parse failed - fall back to raw text
                pass

            panel = Panel(
                display_content,
                title=panel_title,
                border_style=border,
                padding=(0, 1),
            )
            self._append_to_log(panel)
            self._scroll_chat_to_bottom()
        except IndexError:
            self._append_to_log("[red]No tool result at that index. Use /tools to list available.[/red]")
        except Exception as e:
            self._append_to_log(f"[red]Failed to show full tool result: {e}[/red]")

    def _restore_input_focus(self, delay: float = 0.04, *, force: bool = False) -> None:
        """Robustly return keyboard focus to the input TextArea.

        This is critical for chat-like TUI usability — after sending a message
        or after the agent finishes, the user should be able to type immediately
        without clicking the input field.

        We deliberately avoid stealing focus if the user is currently interacting
        with any sidebar widget (sessions, skills, profiles, memory, tools).

        Args:
            delay: Seconds to wait before attempting focus restore.
            force: If True, always restore focus to input even if sidebar has focus.
                   Use during initialization or after non-interactive operations
                   where sidebar got focus automatically (not from user action).
        """
        def _do_focus():
            try:
                focused = self.focused
                focused_id = getattr(focused, "id", None) if focused else None

                # Do not steal focus from sidebar widgets unless forced
                if not force:
                    sidebar_ids = {
                        "sessions-list", "skills-list", "profiles-list",
                        "memory-list", "tools-list",
                        "sessions-collapsible", "skills-collapsible", "profiles-collapsible",
                        "memory-collapsible", "tools-collapsible",
                    }

                    if focused_id in sidebar_ids:
                        return

                    # Also don't steal from children of sidebar lists
                    if focused and hasattr(focused, "parent"):
                        parent_id = getattr(getattr(focused, "parent", None), "id", None)
                        if parent_id in sidebar_ids:
                            return

                input_area = self.query_one("#input-area", TextArea)
                input_area.focus()
            except Exception:
                pass  # Widget might be temporarily unavailable — ignore

        if delay > 0:
            self.set_timer(delay, _do_focus)
        else:
            _do_focus()

    def _list_recent_tools(self) -> None:
        """List recent tool calls with short previews so user can pick one with /last N."""
        self._chat_log()
        if not self._recent_tool_results:
            self._append_to_log("[yellow]No tool results recorded in this TUI session yet.[/yellow]")
            return

        self._append_to_log("\n[bold cyan]Recent tool results (1 = oldest shown, last = most recent):[/bold cyan]")
        for i, entry in enumerate(self._recent_tool_results, 1):
            name = entry["name"]
            full = entry["full_result"]
            preview = full.strip().split("\n")[0][:65]
            if len(full) > 90:
                preview += " …"

            duration_part = ""
            if "duration_ms" in entry:
                duration_part = f" ({entry['duration_ms']:.0f}ms)"

            if name.startswith("ERROR:"):
                clean_name = name[6:]
                self._append_to_log(f"  [dim]{i}.[/dim] [bold red]✗ {clean_name}{duration_part}[/bold red] — {preview}")
            else:
                self._append_to_log(f"  [dim]{i}.[/dim] {name}{duration_part} — {preview}")

        self._append_to_log("[dim]Use /last N  •  /insert-tool N  •  /rerun  •  or Ctrl+P → Tools ▸ for quick actions on recent results[/dim]\n")

    def _show_tool_details(self, tool: dict) -> None:
        """Show full details of a tool from the sidebar list into the chat."""
        try:
            self._chat_log()
            name = tool.get("name", "unknown")
            desc = tool.get("description", "(no description)")

            self._append_to_log(f"\n[bold cyan]Tool:[/bold cyan] {name}")
            self._append_to_log(f"[dim]{desc}[/dim]\n")
        except Exception:
            pass

    async def _rerun_last_tool(self) -> None:
        """Re-run the last tool call with the same arguments (Phase 2 feature)."""
        if not self._last_tool_call:
            self._append_to_log("[yellow]No previous tool call to re-run.[/yellow]")
            return

        tool_name = self._last_tool_call["tool_name"]
        arguments = self._last_tool_call["arguments"]

        self._append_to_log(f"\n[yellow]⟳ Re-running {tool_name}...[/yellow]")

        if not self.agent or not hasattr(self.agent, "tools"):
            self._append_to_log("[red]Cannot re-run: agent/tools not ready.[/red]")
            return

        try:
            if tool_name not in self.agent.tools.tools:
                self._append_to_log(f"[red]Tool '{tool_name}' is no longer registered.[/red]")
                return

            tool = self.agent.tools.tools[tool_name]
            result = await tool.execute(**arguments)

            self._append_to_log(f"\n[bold green]✓ Re-run Result: {tool_name}[/bold green]")
            self._append_to_log(result)
            self._append_to_log("[dim]→ Use /last to view full output if truncated[/dim]")

            self._store_tool_result(tool_name, result)
            self._scroll_chat_to_bottom()

        except Exception as e:
            self._append_to_log(f"[bold red]Re-run of {tool_name} failed:[/bold red] {e}")
            self._scroll_chat_to_bottom()

    def _show_skill_details(self, skill: dict) -> None:
        """Show details of a skill when clicked in the sidebar (Phase 2)."""
        try:
            self._chat_log()
            name = skill.get("name", "unknown")
            desc = skill.get("description", "(no description)")
            tags = skill.get("tags", [])

            self._append_to_log(f"\n[bold magenta]Skill:[/bold magenta] {name}")
            if tags:
                self._append_to_log(f"[dim]tags: {', '.join(tags)}[/dim]")
            self._append_to_log(f"[dim]{desc}[/dim]\n")
        except Exception:
            pass

    async def _search_memory_in_chat(self, query: str) -> None:
        """Perform semantic memory search and display results in chat (used by /memory)."""
        self._chat_log()

        if not query.strip():
            self._append_to_log("[yellow]Usage: /memory <your question or keywords>[/yellow]")
            return

        if not self.agent:
            self._append_to_log("[red]Agent not ready for memory search.[/red]")
            return

        self._append_to_log(f"\n[dim]Searching memory for:[/dim] {query}...")

        try:
            results = await self.agent.search_memory(query, top_k=6)

            if not results:
                self._append_to_log("[yellow]No relevant memories found.[/yellow]")
                return

            self._append_to_log(f"[bold green]Found {len(results)} relevant memories:[/bold green]")

            formatted = self.agent.format_memory_results(
                results,
                conversation_id=self.conversation_id,
                include_current=True,
                content_limit=400,
            )
            for line in formatted.split("\n"):
                if line.strip():
                    self._append_to_log(f"  {line}")

            # Phase 2: also load actionable results into Memory sidebar list (click to insert)
            self._populate_memory_search_results(results, query)
            self._append_to_log("[dim]→ Search results now in sidebar Memory list (click any to insert as context). Use /memory-clear or Command Palette to return to recent.[/dim]")

            self._scroll_chat_to_bottom()

        except Exception as e:
            self._append_to_log(f"[red]Memory search failed: {e}[/red]")

    async def _show_sessions_list(self) -> None:
        """Show list of recent conversations (sessions)."""
        self._chat_log()
        await self._load_known_sessions()

        if not self.known_sessions:
            self._append_to_log("[yellow]No previous conversations found.[/yellow]")
            return

        self._append_to_log("\n[bold cyan]Recent sessions:[/bold cyan]")
        for i, sess in enumerate(self.known_sessions, 1):
            cid = sess["conversation_id"]
            count = sess.get("message_count", 0)
            last_role = sess.get("last_role", "?")
            short = self._get_short_session_name(cid)
            marker = " ← current" if cid == self.conversation_id else ""

            last_hint = ""
            last_ts = sess.get("last_timestamp")
            if last_ts:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    delta = datetime.now(UTC) - dt
                    if delta.days > 0:
                        last_hint = f" {delta.days}d"
                    elif delta.seconds > 3600:
                        last_hint = f" {delta.seconds // 3600}h"
                    else:
                        last_hint = f" {delta.seconds // 60}m"
                except Exception:
                    pass

            self._append_to_log(f"  {i}. {short}  ({count} msgs, last: {last_role}{last_hint}){marker}")

        self._append_to_log("\n[dim]Use /switch N  or  /new  to create fresh session[/dim]\n")

        # Keep sidebar sessions list in sync
        self._populate_sessions_list()

    def _scroll_chat_to_bottom(self) -> None:
        """Scroll the chat log to the bottom (only if auto-scroll is enabled)."""
        if not self._auto_scroll_chat:
            return
        log = self._chat_log()
        if log:
            log.scroll_to_bottom(animate=False)


def run_tui_legacy(profile: str = "default") -> None:
    """Launch the legacy dashboard TUI (HOLIX_TUI_LEGACY=1)."""
    config = init_profile(profile)
    app = HolixTUI(profile=profile, config=config)
    app.run()


if __name__ == "__main__":
    run_tui_legacy()
