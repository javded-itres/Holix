"""Map AgentEvent stream to LiveTranscriptBuffer."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

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
from core.subagents.interaction_events import SubAgentQuestionEvent
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

    def handle(self, event: AgentEvent) -> None:
        buf = self._presenter.buffer
        if buf is None:
            return

        try:
            if isinstance(event, ThinkingEvent):
                buf.set_thinking(event.message or "thinking…")
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
                buf.append_answer_delta(event.content)
                self._presenter.schedule_edit()

            elif isinstance(event, FinalResponseEvent):
                buf.set_thinking(None)
                content = event.content or ""
                if content.strip():
                    self._presenter.session._transcript_store.append(
                        "assistant",
                        content,
                        markdown=content,
                    )
                # For very long final answers, send the full content split across
                # multiple Telegram messages (point 3), and keep the live status
                # message short so it doesn't hit the size limit or duplicate.
                if len(content) > 2200:
                    buf.set_answer("📄 Long response follows in chat.")
                    try:
                        asyncio.create_task(
                            self._presenter.send_final_answer_split(content)
                        )
                    except Exception:
                        # fallback to (capped) answer in the status msg
                        buf.set_answer(content[:2000] + "…")
                else:
                    buf.set_answer(content)
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
                buf.add_note(f"⏸ Plan review ({event.step_count} steps)")
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

            elif isinstance(event, ErrorEvent):
                buf.mark_error(str(event.error or "unknown"))
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