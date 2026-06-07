"""Accumulates agent run output for a single updatable message (Telegram, etc.)."""

from __future__ import annotations

from dataclasses import dataclass, field

from cli.tui.shared.formatters import (
    format_tool_args,
    format_tool_header,
)


@dataclass
class LiveTranscriptBuffer:
    """Build one compact status message from agent events."""

    profile: str = "default"
    mode: str = "react"
    session_label: str = "main"
    status: str = "running"
    thinking: str | None = None
    tool_lines: list[str] = field(default_factory=list)
    answer: str = ""
    notes: list[str] = field(default_factory=list)
    max_tool_lines: int = 8
    max_answer_chars: int = 2800

    def set_header(self, *, profile: str | None = None, mode: str | None = None, session: str | None = None) -> None:
        if profile is not None:
            self.profile = profile
        if mode is not None:
            self.mode = mode
        if session is not None:
            self.session_label = session

    def set_thinking(self, message: str | None) -> None:
        self.thinking = (message or "").strip() or None

    def add_tool_start(self, name: str, args: object) -> None:
        line = format_tool_header(name, running=True)
        args_text = format_tool_args(args)
        if args_text:
            line += f"\n  {args_text}"
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
        self.notes.append(f"Error: {message}")

    def _trim_tools(self) -> None:
        if len(self.tool_lines) > self.max_tool_lines:
            self.tool_lines = self.tool_lines[-self.max_tool_lines :]

    def render_plain(self) -> str:
        parts: list[str] = [
            f"🤖 Helix · {self.profile} · {self.mode} · {self.session_label}",
            "─" * 32,
        ]
        if self.thinking:
            parts.append(f"💭 {self.thinking}")
        if self.tool_lines:
            parts.extend(self.tool_lines)
        if self.answer.strip():
            parts.append(self.answer.strip())
        for note in self.notes[-3:]:
            parts.append(f"· {note}")
        if self.status == "running" and not self.answer.strip() and not self.tool_lines:
            parts.append("⏳ Working…")
        text = "\n\n".join(parts)
        return text[:4090]