"""Agent events → strict transcript formatting."""

from __future__ import annotations

import json

from core.agent_events import (
    AgentEvent,
    AssistantDeltaEvent,
    BackgroundProcessErrorEvent,
    BackgroundProcessStartedEvent,
    BackgroundProcessStoppedEvent,
    ContextCompressedEvent,
    ContextWarningEvent,
    ErrorEvent,
    FinalResponseEvent,
    PlanCompletedEvent,
    PlanStepCompletedEvent,
    StepBudgetChoiceEvent,
    ThinkingEvent,
    TodoListUpdatedEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
    ToolCodeDispatchStartEvent,
)
from core.plan_review.review_events import PlanReviewRequestEvent
from core.presenters.final_content import resolve_messenger_final_content
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction_events import SubAgentQuestionEvent
from rich.markdown import Markdown

from cli.tui.shared.formatters import (
    format_tool_activity,
    format_tool_outcome,
)
from cli.tui.shared.media_links import MEDIA_TOOL_NAMES, format_media_tool_result


class CodeEventHandler:
    def __init__(self, app) -> None:
        self.app = app

    def handle(self, event: AgentEvent) -> None:
        try:
            if isinstance(event, ThinkingEvent):
                self._thinking(event.message or "thinking…")

            elif isinstance(event, ToolCallStartEvent):
                self._tool_start(event)

            elif isinstance(event, ToolCodeDispatchStartEvent):
                self._code_inner(event)

            elif isinstance(event, ToolCallResultEvent):
                self._tool_result(event, error=False)

            elif isinstance(event, ToolCallErrorEvent):
                self._tool_result(event, error=True)

            elif isinstance(event, AssistantDeltaEvent):
                self.app.append_stream_delta(event.content)

            elif isinstance(event, FinalResponseEvent):
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
                self.app._work_detail = ""
                self.app._work_started_at = None
                self.app._refresh_status_bar()
                self.app.run_worker(self.app._update_context_display_async())
                self.app._restore_prompt_focus()

            elif isinstance(event, ConfirmationRequestEvent):
                self.app.set_thinking(None)
                # Modal queue + transcript; also /1–/4 if dialog dismissed
                self.app._handle_confirmation_request(event)

            elif isinstance(event, StepBudgetChoiceEvent):
                self.app.set_thinking(None)
                self.app._handle_step_budget_choice(event)

            elif isinstance(event, SubAgentQuestionEvent):
                self.app.set_thinking(None)
                # Modal queue + transcript; answer via dialog, free text, or /subagent-reply
                self.app._handle_subagent_question(event)

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

            elif isinstance(event, BackgroundProcessStartedEvent):
                self.app.sync_background_process_bar()
                self.app.transcript_write(f"[dim]▶ {event.label} · pid {event.pid}[/dim]")

            elif isinstance(event, BackgroundProcessStoppedEvent):
                self.app.suppress_process_wake(event.process_id)
                self.app.sync_background_process_bar()
                self.app.transcript_write(
                    f"[dim]⏹ Process stopped: {event.label} (pid {event.pid})[/dim]"
                )

            elif isinstance(event, BackgroundProcessErrorEvent):
                self.app.sync_background_process_bar()
                summary = (event.error_summary or event.status or "error")[:300]
                self.app.transcript_write(
                    f"[red]⚠ Background process error ({event.status}):[/red] {summary}\n"
                    f"[dim]  Fix the issue, restart, then check_background_process[/dim]"
                )
                self.app.wake_on_process_exit(
                    event.process_id,
                    event.label,
                    pid=int(event.pid or 0),
                    reason=event.status or "error",
                )

            elif isinstance(event, TodoListUpdatedEvent):
                self.app.sync_todo_list(event.todos)

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
                self.app._work_detail = ""
                self.app._work_started_at = None
                self.app._refresh_status_bar()
                self.app._is_streaming = False
                self.app._restore_prompt_focus()

        except Exception as exc:
            self.app.transcript_write(f"[red]Event error ({type(exc).__name__}): {exc}[/red]")

    def _sync_process_bar_from_tool_result(self, body: str) -> None:
        del body
        self.app.sync_background_process_bar()

    def _thinking(self, message: str) -> None:
        short = (message or "thinking").strip().splitlines()[0]
        if len(short) > 72:
            short = short[:71] + "…"
        self.app.note_work(short or "thinking")

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

        activity = format_tool_activity(event.tool_name, args if isinstance(args, dict) else {})
        self.app.note_work(activity)
        self.app.transcript_scroll_bottom()

    def _code_inner(self, event: ToolCodeDispatchStartEvent) -> None:
        name = (event.tool_name or "").strip()
        if not name:
            return
        self.app.transcript_write(f"[dim]  · {name}[/dim]")
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
            detail = _outcome_detail(name, body, error=True)
            chip = format_tool_outcome(name, error=True, duration_s=duration_s, detail=detail)
            self.app.transcript_write(
                f"[red]{chip}[/red]",
                store_kind="tool",
                store_plain=body,
                store_title=f"ERROR:{name}",
            )
            self.app._store_tool_result(f"ERROR:{name}", body, duration_s)
        else:
            body = getattr(event, "result", "") or ""
            detail = _outcome_detail(name, body, error=False)
            chip = format_tool_outcome(name, error=False, duration_s=duration_s, detail=detail)
            if name in MEDIA_TOOL_NAMES and body.strip():
                self.app.transcript_write(format_media_tool_result(body, tool_name=name))
            else:
                self.app.transcript_write(f"[dim]{chip}[/dim]")

            if body.strip():
                self.app._transcript_store.append("tool", body, title=name)
            self.app._store_tool_result(name, body, duration_s)
            if name in ("start_background_process", "run_project", "run_terminal_command"):
                self._sync_process_bar_from_tool_result(body)

        self.app.note_work("thinking")

        self.app._maybe_refresh_context_display()
        self.app.transcript_scroll_bottom()


def _outcome_detail(name: str, body: str, *, error: bool) -> str:
    """One clause for the chip. Full output stays available via /last."""
    text = " ".join((body or "").split())
    if not text:
        return ""
    low = text.lower()
    if "background task started" in low:
        return "in background"
    if "timed out" in low:
        return "timed out"
    if error or text.startswith("Error"):
        return text
    if name in {"write_file", "patch_file", "apply_patch"}:
        return text.split(".")[0]
    if name == "todo_write":
        return text.split(".")[0]
    return ""
