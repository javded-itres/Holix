"""Agent event → TUI updates."""

from __future__ import annotations

import json

from cli.tui.shared.formatters import (
    format_write_file_diff_display,
    split_write_file_result,
)
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
from core.plan_review.review_events import PlanReviewRequestEvent, PlanReviewResponseEvent
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction_events import SubAgentQuestionEvent
from rich.panel import Panel
from rich.syntax import Syntax
from textual.widgets import RichLog


class AgentEventHandler:
    """Maps AgentEvent stream to Helix TUI widgets (via app reference)."""

    def __init__(self, app) -> None:
        self.app = app

    def handle(self, event: AgentEvent) -> None:
        """Handle incoming agent events and update the UI safely.
        All event processing is wrapped so that a bad event never crashes the TUI.
        """
        try:
            self.app.query_one("#chat-log", RichLog)
        except Exception:
            return  # Widgets not ready yet — ignore safely

        try:
            if isinstance(event, ThinkingEvent):
                # Wave 3 polish: more alive thinking indicator
                msg = event.message or "thinking..."
                self.app._append_to_log(f"[dim]⟳ {msg}[/dim]")
                self.app._scroll_chat_to_bottom()
                self.app._update_scroll_indicator()

                short = msg[:50] + ("…" if len(msg) > 50 else "")
                self.app._set_status(f"⟳ {short}", "yellow")

            elif isinstance(event, ToolCallStartEvent):
                try:
                    args = json.loads(event.arguments_raw) if event.arguments_raw else {}
                    args_str = json.dumps(args, indent=2, ensure_ascii=False)
                except Exception:
                    args = {}
                    args_str = event.arguments_raw or "{}"

                tool_id = event.tool_id or f"{event.tool_name}_{id(event)}"

                self.app._active_tool_calls[tool_id] = {
                    "info": {
                        "tool_name": event.tool_name,
                        "arguments": args,
                        "arguments_raw": event.arguments_raw,
                    }
                }

                # Remember for /rerun
                self.app._last_tool_call = {
                    "tool_name": event.tool_name,
                    "arguments": args,
                }

                # Phase 2: richer visualization — structured panel for tool start
                content = args_str if args_str.strip() else "(no arguments)"
                panel = Panel(
                    content,
                    title=f"[bold yellow]▶ {event.tool_name}[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 1),
                )
                self.app._append_to_log("\n")
                self.app._append_to_log(panel)
                self.app._scroll_chat_to_bottom()
                self.app._update_scroll_indicator()

            elif isinstance(event, ToolCallResultEvent):
                full_result = event.result
                tool_id = event.tool_id or ""
                duration_str = f" ({event.duration_ms:.0f}ms)" if event.duration_ms else ""

                call_info = self.app._active_tool_calls.pop(tool_id, None) or {}
                info = call_info.get("info", {})
                args = info.get("arguments", {})

                # Phase 2 richer viz: nice panel + duration + smart syntax highlight
                content = full_result
                if event.tool_name == "write_file":
                    summary, diff = split_write_file_result(full_result)
                    path = str(args.get("path") or "")
                    if diff:
                        self.app._append_to_log("\n")
                        self.app._append_to_log(
                            Panel(
                                summary or full_result,
                                title=f"[bold green]✓ {event.tool_name}{duration_str}[/bold green]",
                                border_style="green",
                                padding=(0, 1),
                            )
                        )
                        self.app._append_to_log(format_write_file_diff_display(diff, path=path))
                        self.app._append_to_log("[dim]→ /rerun to repeat this call[/dim]")
                        self.app._scroll_chat_to_bottom()
                        duration_for_store = int(event.duration_ms) if event.duration_ms else None
                        self.app._store_tool_result(event.tool_name, full_result, duration_for_store)
                        self.app._update_scroll_indicator()
                        return

                # Smart syntax highlighting for common result types
                if full_result.strip().startswith(("{", "[")) or full_result.strip().startswith("def ") or "Traceback" not in full_result[:50]:
                    try:
                        # Try as JSON first for pretty + highlight
                        json.loads(full_result)
                        content = Syntax(full_result, "json", theme="monokai", line_numbers=False, word_wrap=True)
                    except Exception:
                        # Fallback to generic code-ish highlighting
                        if len(full_result) < 2000:
                            content = Syntax(full_result, "python", theme="monokai", line_numbers=False, word_wrap=True)

                # Truncate very long results for the log view
                if isinstance(content, str) and (len(content) > 800 or content.count("\n") > 20):
                    lines = content.splitlines()
                    content = "\n".join(lines[:14])
                    if len(lines) > 14:
                        total_lines = len(lines)
                        total_chars = len(content)
                        content += f"\n... (truncated — {total_lines - 14} more lines, {total_chars} chars total — use /last or Ctrl+P ▸ Tools ▸ Show last tool result)"

                args_preview = ""
                if args:
                    try:
                        args_preview = " " + json.dumps(args, ensure_ascii=False)[:120]
                        if len(args_preview) > 120:
                            args_preview = args_preview[:117] + "..."
                    except Exception:
                        pass

                panel = Panel(
                    content,
                    title=f"[bold green]✓ {event.tool_name}{args_preview}{duration_str}[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                )
                self.app._append_to_log("\n")
                self.app._append_to_log(panel)
                self.app._append_to_log("[dim]→ /rerun to repeat this call[/dim]")

                self.app._scroll_chat_to_bottom()
                duration_for_store = int(event.duration_ms) if event.duration_ms else None
                self.app._store_tool_result(event.tool_name, full_result, duration_for_store)
                self.app._update_scroll_indicator()

            elif isinstance(event, ToolCallErrorEvent):
                full_error = event.error
                tool_id = event.tool_id or ""

                call_info = self.app._active_tool_calls.pop(tool_id, None) or {}
                info = call_info.get("info", {})
                args = info.get("arguments", {})

                # Phase 2 richer viz: error in distinct red panel + duration if present
                duration_str = f" ({event.duration_ms:.0f}ms)" if getattr(event, "duration_ms", None) else ""

                args_preview = ""
                if args:
                    try:
                        args_preview = " " + json.dumps(args, ensure_ascii=False)[:100]
                    except Exception:
                        pass

                display_error = full_error
                if len(full_error) > 600:
                    lines = full_error.splitlines()
                    if len(lines) > 12:
                        display_error = "\n".join(lines[:12])
                        total_lines = len(lines)
                        total_chars = len(full_error)
                        display_error += f"\n... (truncated — {total_lines - 12} more lines, {total_chars} chars total — use /last or Ctrl+P ▸ Tools ▸ Show last tool result)"
                    else:
                        display_error = full_error[:450] + "\n... (truncated — use /last or Ctrl+P ▸ Tools)"

                panel = Panel(
                    display_error,
                    title=f"[bold red]✗ {event.tool_name}{args_preview}{duration_str}[/bold red]",
                    border_style="red",
                    padding=(0, 1),
                )
                self.app._append_to_log("\n")
                self.app._append_to_log(panel)
                self.app._append_to_log("[dim]→ /rerun to try again[/dim]")

                self.app._scroll_chat_to_bottom()
                duration_for_store = int(getattr(event, "duration_ms", 0) or 0) or None
                self.app._store_tool_result(f"ERROR:{event.tool_name}", full_error, duration_for_store)
                self.app._update_scroll_indicator()

            elif isinstance(event, AssistantDeltaEvent):
                # Accumulate deltas for smoother streaming
                self.app._stream_buffer += event.content

                # Flush on sentence boundaries, double newlines, or after a good chunk (~60 chars)
                flush = (
                    event.content.endswith(('.', '!', '?', '\n\n')) or
                    len(self.app._stream_buffer) > 60
                )
                if flush:
                    self.app._append_to_log(self.app._stream_buffer)
                    self.app._stream_buffer = ""
                    # During streaming: if user scrolled away, keep indicator visible
                    self.app._update_scroll_indicator()

                # Live feedback: as soon as we receive real tokens, show "Streaming..." in header
                if not getattr(self.app, "_first_delta_seen", False):
                    self.app._first_delta_seen = True
                    if self.app._is_streaming:
                        try:
                            self.app.sub_title = f"{self.app.profile} • streaming..."
                        except Exception:
                            pass

            elif isinstance(event, FinalResponseEvent):
                # Flush any remaining streaming buffer
                if self.app._stream_buffer:
                    self.app._append_to_log(self.app._stream_buffer)
                    self.app._stream_buffer = ""

                self.app._append_to_log("\n")

                # Render full response with Markdown support when possible
                regen_tag = (
                    " [dim][regenerated][/dim]"
                    if getattr(self.app, "_next_response_is_regenerated", False)
                    else ""
                )
                self.app._next_response_is_regenerated = False

                try:
                    from rich.markdown import Markdown
                    self.app._append_to_log(f"[bold green]Helix:{regen_tag}[/bold green]")
                    self.app._append_to_log(Markdown(event.content))
                except Exception:
                    self.app._append_to_log(f"[bold green]Helix:{regen_tag}[/bold green]")
                    self.app._append_to_log(event.content)

                self.app._scroll_chat_to_bottom()
                self.app._update_scroll_indicator()
                self.app._set_status("Ready", "green")

                # End of streaming turn
                self.app._is_streaming = False

                # Update context bar from real agent memory (async)
                self.app.run_worker(self.app._update_context_display_async())
                self.app._refresh_header_subtitle()

                # User should be able to type the next question right away
                self.app._restore_input_focus(delay=0.08)

                # Polish: update memory sidebar after assistant response
                self.app._refresh_memory_sidebar()

            elif isinstance(event, ContextCompressedEvent):
                # Context was auto-compressed
                try:
                    self.app._append_to_log(
                        f"\n[yellow]⚡ Context compressed:[/yellow] "
                        f"{event.original_tokens:,} → {event.compressed_tokens:,} tokens "
                        f"({event.messages_before} → {event.messages_after} messages)"
                    )
                    if event.summary_preview:
                        preview = event.summary_preview[:120].replace("\n", " ")
                        self.app._append_to_log(f"[dim]Summary: {preview}...[/dim]")
                    self.app._append_to_log("")
                    # Refresh context bar after compression (async to read from agent memory)
                    self.app.run_worker(self.app._update_context_display_async())
                    self.app._refresh_header_subtitle()
                except Exception:
                    pass

            elif isinstance(event, ContextWarningEvent):
                # Context usage warning
                try:
                    if event.level == "critical":
                        self.app._append_to_log(
                            f"\n[bold red]⚠ Context usage at {event.usage_percent:.0f}%[/bold red] "
                            f"({event.tokens_used:,}/{event.tokens_total:,} tokens) — auto-compressing..."
                        )
                    else:
                        self.app._append_to_log(
                            f"\n[yellow]⚠ Context usage at {event.usage_percent:.0f}%[/yellow] "
                            f"({event.tokens_used:,}/{event.tokens_total:,} tokens)"
                        )
                except Exception:
                    pass

            elif isinstance(event, ConfirmationRequestEvent):
                # Dangerous action confirmation prompt
                self.app._handle_confirmation_request(event)

            elif isinstance(event, SubAgentQuestionEvent):
                name = event.subagent_name or "sub-agent"
                q = (event.question or "").strip()
                self.app._append_to_log(
                    f"\n[bold magenta]❓ {name} asks:[/bold magenta] {q}\n"
                    f"[dim]Reply here, /subagent-reply {name} …, or @{name} …[/dim]\n"
                )

            elif isinstance(event, PlanReviewRequestEvent):
                # Plan review request — show modal
                self.app._handle_plan_review_request(event)

            elif isinstance(event, PlanReviewResponseEvent):
                # Plan review response — informational log
                choice = event.choice
                labels = {
                    "confirm_step": "confirmed (step-by-step)",
                    "auto_execute": "auto-execute",
                    "refine": "refine plan",
                    "reject": "rejected",
                }
                self.app._append_to_log(
                    f"[dim]Plan review {labels.get(choice, choice)}.[/dim]"
                )

            elif isinstance(event, PlanStepCompletedEvent):
                # Show step progress in chat log
                self.app._append_to_log(
                    f"[cyan]Step {event.step_number}/{event.total_steps} completed:[/cyan] "
                    f"{event.step_description[:100]}"
                )

            elif isinstance(event, PlanCompletedEvent):
                self.app._append_to_log(
                    f"[bold green]Plan completed[/bold green] ({event.total_steps} steps)"
                )

            elif isinstance(event, ErrorEvent):
                # Flush any pending stream buffer on error
                if self.app._stream_buffer:
                    self.app._append_to_log(self.app._stream_buffer)
                    self.app._stream_buffer = ""

                self.app._append_to_log(f"[bold red]Error:[/bold red] {event.error}")
                self.app._scroll_chat_to_bottom()
                self.app._update_scroll_indicator()
                self.app._set_status("Error", "red")

                self.app._is_streaming = False
                self.app._refresh_header_subtitle()

                # Return focus even on error so user can react quickly
                self.app._restore_input_focus(delay=0.08)

        except Exception as exc:
            # Last-resort safety net — never let one bad event kill the UI
            try:
                # Only show the error type + message to avoid spamming
                self.app._append_to_log(f"[bold red]Event handling error:[/bold red] {type(exc).__name__}: {exc}")
            except Exception:
                pass  # Even writing failed — give up silently for this event
