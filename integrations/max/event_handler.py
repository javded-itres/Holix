"""Map AgentEvent stream to LiveTranscriptBuffer for MAX."""

from __future__ import annotations

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
    SubAgentWaveCompletedEvent,
    SubAgentWaveStartedEvent,
    ThinkingEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.i18n.live_ui import live_thinking_label
from core.plan_review.review_events import PlanReviewRequestEvent
from core.presenters.final_content import resolve_messenger_final_content
from core.presenters.subagent_tool_text import format_subagent_tool_notice
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction_events import SubAgentQuestionEvent

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from integrations.max.approvals import MaxApprovals
    from integrations.max.live_presenter import MaxLivePresenter

_PROGRESS_TOOLS = frozenset(
    {
        "delegate_to_subagent",
        "wait_subagent_result",
        "list_subagents",
        "terminate_subagent",
        "run_terminal_command",
    }
)


def _tool_result_notice_text(tool_name: str, body: str) -> str:
    name = (tool_name or "").strip()
    if name in _PROGRESS_TOOLS or name in {
        "delegate_to_subagent",
        "list_subagents",
        "terminate_subagent",
    }:
        formatted = format_subagent_tool_notice(name, body)
        if formatted:
            return formatted
    return body


class MaxEventHandler:
    def __init__(self, presenter: MaxLivePresenter, approvals: MaxApprovals) -> None:
        self._presenter = presenter
        self._approvals = approvals

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
                name = (event.tool_name or "").strip()
                detail = self._tool_detail(name, args)
                logger.info("MAX tool started (%s)", name)
                if name == "delegate_to_subagent" and self._has_active_subagents():
                    logger.info("MAX tool progress skipped (%s): sub-agents already active", name)
                else:
                    self._presenter.enqueue_outbound(
                        self._presenter.send_tool_progress(name, detail)
                    )

            elif isinstance(event, ToolCallResultEvent):
                duration = getattr(event, "duration_ms", None)
                duration_s = (duration / 1000.0) if duration else None
                body = getattr(event, "result", "") or ""
                buf.add_tool_result(event.tool_name, body, duration_s=duration_s)
                self._store_tool(self._presenter.session, event.tool_name, body, duration_s)
                if (event.tool_name or "") == "send_chat_files" and body.startswith("Sent "):
                    buf.add_note(f"📎 {body[:240]}")
                self._presenter.schedule_edit()
                name = (event.tool_name or "").strip()
                if (body or "").strip():
                    notice = _tool_result_notice_text(name, body)
                    if name == "delegate_to_subagent" and "already_running" in body:
                        logger.info("MAX tool result skipped (%s): duplicate delegation", name)
                    else:
                        self._presenter.enqueue_outbound(
                            self._presenter.send_tool_result_notice(name, notice)
                        )

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
                name = (event.tool_name or "tool").strip()
                if (body or "").strip():
                    self._presenter.enqueue_outbound(
                        self._presenter.send_tool_result_notice(
                            name,
                            f"✗ {body}",
                        )
                    )

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
                logger.info(
                    "MAX FinalResponseEvent handled (%d chars, queued_final=%s)",
                    len(content),
                    bool(content),
                )

            elif isinstance(event, ConfirmationRequestEvent):
                buf.set_thinking(None)
                self._presenter.schedule_edit(force=True)
                self._presenter.enqueue_outbound(
                    self._approvals.on_confirmation_request(event)
                )

            elif isinstance(event, SubAgentWaveStartedEvent):
                buf.set_thinking(None)
                wave = int(getattr(event, "wave_id", 0)) + 1
                total = int(getattr(event, "total_waves", 0)) or 1
                jobs = ", ".join(getattr(event, "job_ids", []) or []) or "—"
                buf.add_note(f"🚀 subagents wave {wave}/{total}: {jobs[:240]}")
                self._presenter.schedule_edit(force=True)
                self._presenter.enqueue_outbound(
                    self._presenter.send_notice(
                        f"🚀 Запущена волна субагентов {wave}/{total}: {jobs}"
                    )
                )

            elif isinstance(event, SubAgentWaveCompletedEvent):
                buf.set_thinking(None)
                summary = (getattr(event, "summary", None) or "").strip()
                wave = int(getattr(event, "wave_id", 0)) + 1
                total = int(getattr(event, "total_waves", 0)) or 1
                completed = int(getattr(event, "completed", 0))
                total_jobs = int(getattr(event, "total", 0))
                buf.add_note(
                    f"✓ subagents wave {wave}/{total}: {completed}/{total_jobs}"
                )
                self._presenter.schedule_edit(force=True)
                if summary:
                    self._presenter.enqueue_outbound(
                        self._presenter.send_notice(summary)
                    )
                else:
                    self._presenter.enqueue_outbound(
                        self._presenter.send_notice(
                            f"✓ Субагенты: волна {wave}/{total} — "
                            f"{completed}/{total_jobs} готово"
                        )
                    )

            elif isinstance(event, SubAgentQuestionEvent):
                buf.set_thinking(None)
                name = event.subagent_name or "sub-agent"
                q = (event.question or "").strip()
                buf.add_note(f"❓ {name}: {q[:500]}")
                self._presenter.schedule_edit(force=True)
                self._presenter.enqueue_outbound(self._send_subagent_question(event))

            elif isinstance(event, PlanReviewRequestEvent):
                buf.set_thinking(None)
                self._presenter.schedule_edit(force=True)
                self._presenter.enqueue_outbound(
                    self._approvals.on_plan_review_request(event)
                )

            elif isinstance(event, (PlanStepCompletedEvent, PlanCompletedEvent)):
                msg = getattr(event, "message", "") or type(event).__name__
                buf.add_note(f"plan: {msg}")
                self._presenter.schedule_edit()

            elif isinstance(event, ContextCompressedEvent):
                buf.add_note(
                    "⚡ Context compressed: "
                    f"{event.original_tokens:,} → {event.compressed_tokens:,} tokens"
                )
                self._presenter.schedule_edit()

            elif isinstance(event, ContextWarningEvent):
                buf.add_note(
                    f"⚠ Context {event.usage_percent:.0f}% "
                    f"({event.tokens_used:,}/{event.tokens_total:,})"
                )
                self._presenter.schedule_edit()

            elif isinstance(event, BackgroundProcessStartedEvent):
                label = f"{event.label} · pid {event.pid}"
                buf.set_background_process(label=label, process_id=event.process_id)
                from integrations.max.approvals import _register_callback_token
                from integrations.max.keyboards import background_process_stop_keyboard

                token = _register_callback_token(
                    self._presenter.session.process_callback_tokens,
                    event.process_id,
                )
                self._presenter.set_attachments(
                    background_process_stop_keyboard(token)
                )
                self._presenter.schedule_edit(force=True)

            elif isinstance(event, BackgroundProcessStoppedEvent):
                buf.clear_background_process()
                self._presenter.set_attachments(None)
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
                buf.mark_error(str(event.error or "unknown"))
                self._presenter.schedule_edit(force=True)

        except Exception as exc:
            buf.add_note(f"UI error: {exc}")
            self._presenter.schedule_edit()
            logger.exception("MAX event handler failed for %s", type(event).__name__)

    def _has_active_subagents(self) -> bool:
        session = self._presenter.session
        agent = getattr(session, "agent", None)
        if not agent or not hasattr(agent, "subagents"):
            return False
        return bool(agent.subagents.list_active())

    async def _send_subagent_question(self, event: SubAgentQuestionEvent) -> None:
        name = event.subagent_name or "sub-agent"
        question = (event.question or "").strip()
        text = (
            f"❓ Sub-agent {name} asks:\n{question}\n\n"
            f"Reply in chat or /subagent-reply {name} …"
        )
        await self._presenter.send_notice(text)

    @staticmethod
    def _tool_detail(name: str, args: object) -> str:
        if not isinstance(args, dict):
            return ""
        if name in _PROGRESS_TOOLS:
            return str(
                args.get("task")
                or args.get("command")
                or args.get("job_id")
                or args.get("agent_type")
                or ""
            )[:200]
        for key in ("path", "query", "url", "command", "task", "job_id"):
            val = args.get(key)
            if val:
                return str(val)[:200]
        return ""

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