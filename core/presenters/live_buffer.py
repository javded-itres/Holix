"""Accumulates agent run output for a single updatable message (Telegram, etc.)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.presenters.tool_format import (
    format_run_code_program_line,
    format_tool_args,
    format_tool_header,
)
from core.tools.code_mode.policy import RUN_CODE_NAME


@dataclass
class LiveTranscriptBuffer:
    """Build one compact status message from agent events."""

    profile: str = "default"
    mode: str = "react"
    session_label: str = "main"
    status: str = "running"
    background_process: str | None = None
    background_process_id: str | None = None
    background_process_healthy: bool = True
    thinking: str | None = None
    tool_lines: list[str] = field(default_factory=list)
    answer: str = ""
    notes: list[str] = field(default_factory=list)
    # When True (Telegram), the final answer is posted as a separate chat message.
    publish_answer_separately: bool = False
    result_posted_separately: bool = False
    max_tool_lines: int = 8
    max_answer_chars: int = 2800
    compact_tools: bool = False
    todos: list[dict[str, str]] = field(default_factory=list)
    sdd_change_line: str = ""
    _code_runs: dict[str, dict] = field(default_factory=dict)

    def set_header(
        self, *, profile: str | None = None, mode: str | None = None, session: str | None = None
    ) -> None:
        if profile is not None:
            self.profile = profile
        if mode is not None:
            self.mode = mode
        if session is not None:
            self.session_label = session

    def set_thinking(self, message: str | None) -> None:
        self.thinking = (message or "").strip() or None

    def set_background_process(
        self,
        *,
        label: str | None = None,
        process_id: str | None = None,
        healthy: bool = True,
    ) -> None:
        self.background_process = (label or "").strip() or None
        self.background_process_id = (process_id or "").strip() or None
        self.background_process_healthy = healthy

    def clear_background_process(self) -> None:
        self.background_process = None
        self.background_process_id = None
        self.background_process_healthy = True

    def set_todos(self, items: object = None) -> None:
        from core.runtime.todo_list import items_as_dicts

        self.todos = items_as_dicts(items or [])

    def hydrate_todos(self, *, profile: str, conversation_id: str) -> None:
        from core.runtime.todo_list import get_todos, items_as_dicts

        self.todos = items_as_dicts(get_todos(profile, conversation_id))
        self.hydrate_sdd_change(profile=profile, conversation_id=conversation_id)

    def hydrate_sdd_change(self, *, profile: str, conversation_id: str) -> None:
        try:
            from core.sdd.change_workspace import format_active_change_line, get_active_change

            self.sdd_change_line = format_active_change_line(
                get_active_change(profile, conversation_id)
            )
        except Exception:
            self.sdd_change_line = ""

    def add_tool_start(self, name: str, args: object, *, tool_id: str = "") -> None:
        # Partial assistant text before a tool call is preamble, not the final answer.
        self.answer = ""
        if str(name or "") == RUN_CODE_NAME:
            desc = ""
            if isinstance(args, dict):
                desc = str(args.get("description") or "").strip()
            key = (tool_id or RUN_CODE_NAME).strip() or RUN_CODE_NAME
            rec = {"desc": desc, "names": [], "line_index": len(self.tool_lines)}
            self._code_runs[key] = rec
            self._code_runs[RUN_CODE_NAME] = rec
            self.tool_lines.append(format_run_code_program_line(desc, [], running=True))
            self._trim_tools()
            return
        line = format_tool_header(name, running=True)
        if not self.compact_tools:
            args_text = format_tool_args(args)
            if args_text:
                line += f"\n  {args_text}"
        self.tool_lines.append(line)
        self._trim_tools()

    def add_code_inner(self, parent_tool_id: str, tool_name: str) -> None:
        name = str(tool_name or "").strip()
        if not name:
            return
        rec = self._code_runs.get(str(parent_tool_id or "").strip()) or self._code_runs.get(
            RUN_CODE_NAME
        )
        if rec is None:
            rec = {"desc": "", "names": [], "line_index": len(self.tool_lines)}
            self._code_runs[RUN_CODE_NAME] = rec
            self.tool_lines.append(format_run_code_program_line("", [name], running=True))
            self._trim_tools()
            rec["line_index"] = len(self.tool_lines) - 1
            rec["names"].append(name)
            return
        rec["names"].append(name)
        line = format_run_code_program_line(str(rec.get("desc") or ""), rec["names"], running=True)
        idx = rec.get("line_index")
        if isinstance(idx, int) and 0 <= idx < len(self.tool_lines):
            self.tool_lines[idx] = line
        elif self.tool_lines and "программа:" in self.tool_lines[-1]:
            self.tool_lines[-1] = line
        else:
            rec["line_index"] = len(self.tool_lines)
            self.tool_lines.append(line)
        self._trim_tools()

    def add_tool_result(
        self,
        name: str,
        body: str,
        *,
        error: bool = False,
        duration_s: float | None = None,
    ) -> None:
        # Only record the completion header (no body preview) to keep the
        # live transcript message compact — full results are available via
        # transcript / copy-last-tool commands.
        header = format_tool_header(name, duration_s=duration_s, error=error)
        block = header
        if self.tool_lines and "…" in self.tool_lines[-1]:
            self.tool_lines[-1] = block
        else:
            self.tool_lines.append(block)
        self._trim_tools()

    def append_answer_delta(self, text: str) -> None:
        if text:
            self.answer += text
            if len(self.answer) > self.max_answer_chars:
                self.answer = self.answer[: self.max_answer_chars] + "…"

    def set_answer(self, text: str) -> None:
        self.answer = (text or "")[: self.max_answer_chars]

    def add_note(self, text: str) -> None:
        if text.strip():
            self.notes.append(text.strip())

    def mark_done(self) -> None:
        self.status = "done"
        self.thinking = None

    def mark_error(self, message: str) -> None:
        self.status = "error"
        self.thinking = None
        msg = (message or "unknown error").strip()
        self.answer = msg[: self.max_answer_chars]
        self.notes.append(f"Error: {msg}")

    def _trim_tools(self) -> None:
        if len(self.tool_lines) > self.max_tool_lines:
            self.tool_lines = self.tool_lines[-self.max_tool_lines :]

    def render_plain(self) -> str:
        parts: list[str] = [
            f"🤖 Holix · {self.profile} · {self.mode} · {self.session_label}",
            "─" * 32,
        ]
        if self.background_process:
            icon = "🟢" if self.background_process_healthy else "🔴"
            parts.append(f"{icon} Process: {self.background_process}")
        if self.sdd_change_line:
            parts.append(self.sdd_change_line)
        if self.todos:
            from core.runtime.todo_list import format_todo_checklist

            block = format_todo_checklist(self.todos)
            if block:
                parts.append(block)
        if self.thinking:
            from core.i18n.live_ui import live_thinking_label

            parts.append(f"💭 {live_thinking_label(self.profile, fallback=self.thinking)}")
        if self.tool_lines:
            parts.extend(self.tool_lines)
        if self.answer.strip() and not self.publish_answer_separately:
            parts.append(self.answer.strip())
        for note in self.notes[-3:]:
            parts.append(f"· {note}")
        if self.status == "running" and not self.answer.strip() and not self.tool_lines:
            from core.i18n.live_ui import live_working_label

            parts.append(f"⏳ {live_working_label(self.profile)}")
        text = "\n\n".join(parts)
        return text[:4090]
