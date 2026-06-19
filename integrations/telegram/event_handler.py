"""Map AgentEvent stream to LiveTranscriptBuffer."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

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
    ThinkingEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.i18n.live_ui import live_plan_review_label, live_thinking_label
from core.plan_review.review_events import PlanReviewRequestEvent
from core.presenters.final_content import resolve_messenger_final_content
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction_events import SubAgentQuestionEvent

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from integrations.telegram.approvals import TelegramApprovals
    from integrations.telegram.live_presenter import TelegramLivePresenter


class TelegramEventHandler:
    def __init__(
        self,
        presenter: TelegramLivePresenter,
        approvals: TelegramApprovals,
    ) -> None:
        self._presenter = presenter
        self._approvals = approvals

    @staticmethod
    def _schedule_task(coro) -> None:
        """Schedule a coroutine; requires a running loop (Telegram polling)."""
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            logger.warning("Telegram handler: no event loop; skipped async delivery")

    def handle(self, event: AgentEvent) -> None:
        buf = self._presenter.buffer
        if buf is None:
            return

        try:
            if isinstance(event, ThinkingEvent):
                buf.set_thinking(
                    live_thinking_label(buf.profile, fallback=event.message or "thinking…")
                )
                self._presenter.schedule_edit()

            elif isinstance(event, ToolCallStartEvent):
                buf.set_thinking(None)
                try:
                    args = json.loads(event.arguments_raw) if event.arguments_raw else {}
                except Exception:
                    args = event.arguments_raw
                buf.add_tool_start(event.tool_name, args)
                self._presenter.schedule_edit()

            elif isinstance(event, ToolCallResultEvent):
                duration = getattr(event, "duration_ms", None)
                duration_s = (duration / 1000.0) if duration else None
                body = getattr(event, "result", "") or ""
                buf.add_tool_result(event.tool_name, body, duration_s=duration_s)
                self._store_tool(self._presenter.session, event.tool_name, body, duration_s)
                if (event.tool_name or "") == "send_chat_files" and body.startswith("Sent "):
                    buf.add_note(f"📎 {body[:240]}")
                self._presenter.schedule_edit()

            elif isinstance(event, ToolCallErrorEvent):
                duration = getattr(event, "duration_ms", None)
                duration_s = (duration / 1000.0) if duration else None
                body = getattr(event, "error", "") or ""
                buf.add_tool_result(
                    event.tool_name or "tool",
                    body,
                    error=True,
                    duration_s=duration_s,
                )
                self._presenter.schedule_edit()

            elif isinstance(event, AssistantDeltaEvent):
                accumulated = (getattr(event, "accumulated", None) or "").strip()
                if accumulated:
                    buf.set_answer(accumulated)
                elif event.content:
                    buf.append_answer_delta(event.content)
                self._presenter.schedule_edit()

            elif isinstance(event, FinalResponseEvent):
                buf.set_thinking(None)
                recent = self._presenter.session._recent_tool_results
                last_tool = (
                    str(recent[-1].get("full_result") or "").strip() if recent else ""
                )
                content = resolve_messenger_final_content(
                    event.content,
                    streamed_answer=buf.answer,
                    last_tool_result=last_tool,
                    recent_tool_results=recent,
                )
                if content:
                    self._presenter.session._transcript_store.append(
                        "assistant",
                        content,
                        markdown=content,
                    )
                    buf.result_posted_separately = True
                    self._presenter.note_final_content(content)
                    self._presenter.enqueue_outbound(
                        self._presenter.deliver_final_answer(content)
                    )
                buf.set_answer("")
                buf.mark_done()
                self._presenter.schedule_edit(force=True)

            elif isinstance(event, ConfirmationRequestEvent):
                buf.set_thinking(None)
                # Do not add a "⏸ Confirmation" note here — it produced the
                # unwanted "· ⏸ Confirmation: write_file" in the transcript.
                # The dedicated confirmation message (with command details +
                # inline buttons) is sent via approvals below.
                self._presenter.schedule_edit(force=True)
                asyncio.create_task(self._approvals.on_confirmation_request(event))

            elif isinstance(event, SubAgentQuestionEvent):
                buf.set_thinking(None)
                name = event.subagent_name or "sub-agent"
                q = (event.question or "").strip()
                buf.add_note(f"❓ {name}: {q[:500]}")
                self._presenter.schedule_edit(force=True)
                asyncio.create_task(self._send_subagent_question(event))

            elif isinstance(event, PlanReviewRequestEvent):
                buf.set_thinking(None)
                buf.add_note(
                    live_plan_review_label(buf.profile, step_count=event.step_count)
                )
                self._presenter.schedule_edit(force=True)
                asyncio.create_task(self._approvals.on_plan_review_request(event))

            elif isinstance(event, (PlanStepCompletedEvent, PlanCompletedEvent)):
                msg = getattr(event, "message", "") or type(event).__name__
                buf.add_note(f"plan: {msg}")
                self._presenter.schedule_edit()

            elif isinstance(event, ContextCompressedEvent):
                buf.add_note(
                    "⚡ Context compressed: "
                    f"{event.original_tokens:,} → {event.compressed_tokens:,} tokens "
                    f"({event.messages_before} → {event.messages_after} messages)"
                )
                if event.summary_preview:
                    preview = event.summary_preview[:120].replace("\n", " ")
                    buf.add_note(f"summary: {preview}…")
                self._presenter.schedule_edit()

            elif isinstance(event, ContextWarningEvent):
                if event.level == "critical":
                    buf.add_note(
                        f"⚠ Context {event.usage_percent:.0f}% "
                        f"({event.tokens_used:,}/{event.tokens_total:,}) — compressing…"
                    )
                else:
                    buf.add_note(
                        f"⚠ Context {event.usage_percent:.0f}% "
                        f"({event.tokens_used:,}/{event.tokens_total:,})"
                    )
                self._presenter.schedule_edit()

            elif isinstance(event, BackgroundProcessStartedEvent):
                label = f"{event.label} · pid {event.pid}"
                buf.set_background_process(label=label, process_id=event.process_id)
                from integrations.telegram.approvals import _register_callback_token
                from integrations.telegram.keyboards import background_process_stop_keyboard

                token = _register_callback_token(
                    self._presenter.session.process_callback_tokens,
                    event.process_id,
                )
                self._presenter.set_reply_markup(
                    background_process_stop_keyboard(token)
                )
                self._presenter.schedule_edit(force=True)

            elif isinstance(event, BackgroundProcessStoppedEvent):
                buf.clear_background_process()
                self._presenter.set_reply_markup(None)
                buf.add_note(f"⏹ Process stopped: {event.label}")
                self._presenter.schedule_edit(force=True)

            elif isinstance(event, BackgroundProcessErrorEvent):
                label = f"{event.label} · pid {event.pid} · {event.status}"
                buf.set_background_process(
                    label=label,
                    process_id=event.process_id,
                    healthy=False,
                )
                summary = (event.error_summary or event.status or "error")[:200]
                buf.add_note(f"⚠ Process error: {summary}")
                self._presenter.schedule_edit(force=True)

            elif isinstance(event, ErrorEvent):
                err = str(event.error or "unknown")
                buf.mark_error(err)
                self._presenter.enqueue_outbound(
                    self._presenter.deliver_final_answer(f"✗ **Ошибка:** {err}")
                )
                self._presenter.schedule_edit(force=True)

        except Exception as exc:
            buf.add_note(f"UI error: {exc}")
            self._presenter.schedule_edit()

    async def _send_subagent_question(self, event: SubAgentQuestionEvent) -> None:
        from integrations.telegram.markdown import escape_html

        name = escape_html(event.subagent_name or "sub-agent")
        question = escape_html((event.question or "").strip())
        context = escape_html((event.context or "").strip())
        text = f"<b>❓ Sub-agent <code>{name}</code> asks:</b>\n{question}"
        if context:
            text += f"\n\n<i>{context}</i>"
        text += (
            f"\n\n<i>Reply with your answer, "
            f"<code>/subagent-reply {event.subagent_name} …</code>, "
            f"or <code>@{event.subagent_name} …</code></i>"
        )
        try:
            await self._presenter._bot.send_message(
                self._presenter.session.chat_id,
                text,
                parse_mode="HTML",
            )
        except Exception:
            pass

    @staticmethod
    def _store_tool(session, name: str, body: str, duration_s: float | None) -> None:
        entry = {"name": name, "full_result": body}
        if duration_s is not None:
            entry["duration_ms"] = duration_s * 1000
        session._recent_tool_results.append(entry)
        if len(session._recent_tool_results) > 20:
            session._recent_tool_results.pop(0)
        if body.strip():
            session._transcript_store.append("tool", body, title=name)