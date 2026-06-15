"""Agent events → strict transcript formatting."""

from __future__ import annotations

import json

from core.agent_events import (
    AgentEvent,
    AssistantDeltaEvent,
    ContextCompressedEvent,
    ContextWarningEvent,
    ErrorEvent,
    FinalResponseEvent,
    PlanCompletedEvent,
    PlanStepCompletedEvent,
    ThinkingEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.plan_review.review_events import PlanReviewRequestEvent
from core.security.confirmation_events import ConfirmationRequestEvent
from core.presenters.final_content import resolve_messenger_final_content
from core.subagents.interaction_events import SubAgentQuestionEvent
from rich.markdown import Markdown

from cli.tui.shared.formatters import (
    format_tool_args,
    format_tool_header,
    format_tool_result_preview,
    format_write_file_diff_display,
    format_write_file_result_preview,
    split_write_file_result,
)


class CodeEventHandler:
    def __init__(self, app) -> None:
        self.app = app

    def handle(self, event: AgentEvent) -> None:
        try:
            if isinstance(event, ThinkingEvent):
                self._thinking(event.message or "thinking…")

            elif isinstance(event, ToolCallStartEvent):
                self._tool_start(event)

            elif isinstance(event, ToolCallResultEvent):
                self._tool_result(event, error=False)

            elif isinstance(event, ToolCallErrorEvent):
                self._tool_result(event, error=True)

            elif isinstance(event, AssistantDeltaEvent):
                self.app.append_stream_delta(event.content)

            elif isinstance(event, FinalResponseEvent):
                had_stream = self.app._is_streaming
                streamed_answer = self.app._transcript_store.stream_plain()
                content = resolve_messenger_final_content(
                    event.content or "",
                    streamed_answer=streamed_answer,
                    last_tool_result=self.app._transcript_store.last_tool() or "",
                )
                self.app.clear_stream_display()
                self.app.set_thinking(None)
                self.app._transcript_store.clear_stream()
                if content.strip():
                    self.app.transcript_write("")
                    try:
                        self.app.transcript_write(Markdown(content))
                    except Exception:
                        self.app.transcript_write(content)
                    self.app._transcript_store.append(
                        "assistant",
                        content,
                        markdown=content,
                    )
                else:
                    self.app.transcript_write("")
                self.app._schedule_scroll_hint_update()
                self.app._last_assistant_plain = content
                self.app._is_streaming = False
                self.app.set_status_line("ready")
                self.app.run_worker(self.app._update_context_display_async())
                self.app._restore_prompt_focus()

            elif isinstance(event, ConfirmationRequestEvent):
                self.app.set_thinking(None)
                sub = getattr(event, "subagent_name", "") or ""
                if sub:
                    self.app.transcript_write(
                        f"\n[yellow]Sub-agent [cyan]{sub}[/cyan] needs approval:[/yellow] "
                        f"{event.tool_name} — {event.reason}\n"
                        f"[dim]/1 once · /2 session · /3 always · /4 deny[/dim]\n"
                    )
                else:
                    self.app.transcript_write(
                        f"\n[yellow]Confirmation:[/yellow] {event.tool_name} — {event.reason}\n"
                        f"[dim]/1 once · /2 session · /3 always · /4 deny[/dim]\n"
                    )
                self.app._handle_confirmation_request(event)

            elif isinstance(event, SubAgentQuestionEvent):
                self.app.set_thinking(None)
                name = event.subagent_name or "sub-agent"
                q = (event.question or "").strip()
                self.app.transcript_write(
                    f"[magenta]❓ {name}:[/magenta] {q}\n"
                    f"[dim]Reply, /subagent-reply {name} …, or @{name} …[/dim]"
                )

            elif isinstance(event, PlanReviewRequestEvent):
                self.app.set_thinking(None)
                self.app._handle_plan_review_request(event)

            elif isinstance(event, (PlanStepCompletedEvent, PlanCompletedEvent)):
                self.app.transcript_write(
                    f"[dim]· plan: {getattr(event, 'message', '') or type(event).__name__}[/dim]"
                )

            elif isinstance(event, (ContextCompressedEvent, ContextWarningEvent)):
                msg = getattr(event, "message", "") or ""
                if msg:
                    self.app.transcript_write(f"[dim]· context: {msg}[/dim]")
                agent = getattr(self.app, "agent", None)
                cm = getattr(agent, "context_manager", None) if agent else None
                if cm:
                    cm.invalidate_usage_cache(getattr(self.app, "conversation_id", None))
                self.app.run_worker(self.app._update_context_display_async())

            elif isinstance(event, ErrorEvent):
                if self.app._is_streaming and self.app._stream_buffer:
                    self.app.flush_partial_stream_to_transcript()
                else:
                    self.app.clear_stream_display()
                self.app._transcript_store.clear_stream()
                self.app.set_thinking(None)
                err = str(event.error or "")
                self.app.transcript_write(
                    f"[red]Error: {err}[/red]",
                    store_kind="error",
                    store_plain=err,
                )
                self.app.set_status_line("error")
                self.app._is_streaming = False
                self.app._restore_prompt_focus()

        except Exception as exc:
            self.app.transcript_write(
                f"[red]Event error ({type(exc).__name__}): {exc}[/red]"
            )

    def _thinking(self, message: str) -> None:
        short = message[:60] + ("…" if len(message) > 60 else "")
        self.app.set_thinking(short)
        self.app.set_status_line(f"thinking — {short}")

    def _tool_start(self, event: ToolCallStartEvent) -> None:
        if self.app._is_streaming and self.app._stream_buffer:
            self.app.flush_partial_stream_to_transcript()
        else:
            self.app.clear_stream_display()
        self.app.set_thinking(None)
        try:
            args = json.loads(event.arguments_raw) if event.arguments_raw else {}
        except Exception:
            args = event.arguments_raw

        tool_id = event.tool_id or f"{event.tool_name}_{id(event)}"
        self.app._active_tools[tool_id] = event.tool_name
        self.app._last_tool_call = {
            "tool_name": event.tool_name,
            "arguments": args if isinstance(args, dict) else {},
        }

        self.app.transcript_write("")
        self.app.transcript_write(f"[bold]{format_tool_header(event.tool_name, running=True)}[/bold]")
        args_text = format_tool_args(args)
        if args_text:
            self.app.transcript_write(f"[dim]{args_text}[/dim]")
        self.app.transcript_scroll_bottom()

    def _tool_result(self, event, *, error: bool) -> None:
        tool_id = getattr(event, "tool_id", None) or ""
        name = getattr(event, "tool_name", None) or self.app._active_tools.pop(tool_id, "tool")
        if tool_id in self.app._active_tools:
            del self.app._active_tools[tool_id]

        duration = getattr(event, "duration_ms", None)
        duration_s = (duration / 1000.0) if duration else None

        if error:
            body = getattr(event, "error", "") or ""
            header = format_tool_header(name, duration_s=duration_s, error=True)
            self.app.transcript_write(f"[red]{header}[/red]")
            self.app.transcript_write(
                body,
                store_kind="tool",
                store_plain=body,
                store_title=f"ERROR:{name}",
            )
            self.app._store_tool_result(f"ERROR:{name}", body, duration_s)
        else:
            body = getattr(event, "result", "") or ""
            header = format_tool_header(name, duration_s=duration_s, error=False)
            self.app.transcript_write(f"[dim]{header}[/dim]")

            if name == "write_file" and body.strip():
                summary, diff = split_write_file_result(body)
                path = ""
                last = getattr(self.app, "_last_tool_call", None) or {}
                if last.get("tool_name") == "write_file":
                    path = str((last.get("arguments") or {}).get("path") or "")
                preview = format_write_file_result_preview(body, max_len=400)
                if preview.strip():
                    self.app.transcript_write(f"[dim]  {preview}[/dim]")
                if diff:
                    self.app.transcript_write(format_write_file_diff_display(diff, path=path))
                elif not summary:
                    self.app.transcript_write(f"[dim]  {body[:400]}[/dim]")
            else:
                preview = format_tool_result_preview(body, max_len=400)
                if preview.strip():
                    self.app.transcript_write(f"[dim]  {preview}[/dim]")
                if len(body) > 400:
                    self.app.transcript_write("[dim]  … truncated — /last[/dim]")

            if body.strip():
                self.app._transcript_store.append("tool", body, title=name)
            self.app._store_tool_result(name, body, duration_s)

        self.app._maybe_refresh_context_display()
        self.app.transcript_scroll_bottom()