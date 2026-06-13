"""Deliver agent progress and answers to MAX as new plain-text messages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from integrations.max.client import MaxApiError
from integrations.max.markdown import (
    plain_to_max_html,
    prepare_max_html,
    prepare_max_markdown,
    split_max_html,
    truncate_max_text,
)
from integrations.max.models import message_id_from_response, reply_kwargs_for_session
from integrations.max.render import buffer_to_max_html

if TYPE_CHECKING:
    from integrations.max.client import MaxClient
    from integrations.max.session import MaxChatSession

logger = logging.getLogger(__name__)

_PROGRESS_TOOLS = frozenset(
    {
        "delegate_to_subagent",
        "wait_subagent_result",
        "list_subagents",
        "terminate_subagent",
        "run_terminal_command",
    }
)


class MaxLivePresenter:
    def __init__(
        self,
        client: MaxClient,
        session: MaxChatSession,
        *,
        edit_interval_ms: int = 1500,
        heartbeat_interval_s: int = 45,
    ) -> None:
        self._client = client
        self.session = session
        self._edit_interval = edit_interval_ms / 1000.0
        self._heartbeat_interval_s = heartbeat_interval_s
        self._last_edit = 0.0
        self._started_at = 0.0
        self._edit_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._buffer = session.live_buffer
        self._final_delivered = False
        self._final_content: str | None = None
        self._progress_message_id: str | None = None
        self._outbound_queue: asyncio.Queue[Coroutine[Any, Any, Any] | None] | None = None
        self._outbound_worker: asyncio.Task | None = None

    @property
    def buffer(self):
        return self.session.live_buffer

    @property
    def final_delivered(self) -> bool:
        return self._final_delivered

    def _reply_kwargs(self) -> dict[str, Any]:
        return reply_kwargs_for_session(
            user_id=self.session.user_id,
            reply_user_id=self.session.reply_user_id,
            reply_chat_id=self.session.reply_chat_id,
            chat_type=self.session.chat_type,
        )

    async def _send_outbound(
        self,
        text: str,
        *,
        fmt: str | None = None,
    ) -> dict[str, Any]:
        if not (text or "").strip():
            return {}
        return await self._client.send_message(
            text,
            fmt=fmt,
            **self._reply_kwargs(),
        )

    async def start(self) -> None:
        self.session.bump_live_buffer()
        self._buffer = self.session.live_buffer
        self._buffer.publish_answer_separately = True
        self._started_at = time.monotonic()
        self._final_delivered = False
        self._final_content = None
        self._progress_message_id = None
        self._outbound_queue = asyncio.Queue()
        self._outbound_worker = asyncio.create_task(self._outbound_worker_loop())
        payload = await self._send_outbound("⏳ Holix обрабатывает запрос…")
        self._progress_message_id = message_id_from_response(payload)
        self.session.live_message_id = self._progress_message_id
        logger.info(
            "MAX run started (progress_mid=%s, target=%s)",
            self._progress_message_id,
            self._reply_kwargs(),
        )
        self.start_heartbeat()

    def start_heartbeat(self) -> None:
        self.stop_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def stop_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval_s)
                buf = self._buffer
                if buf is None or buf.status != "running":
                    break
                elapsed = int(time.monotonic() - self._started_at)
                await self._send_outbound(f"⏳ Holix всё ещё работает… ({elapsed}s)")
        except asyncio.CancelledError:
            pass

    def schedule_edit(self, *, force: bool = False) -> None:
        if self._edit_task and not self._edit_task.done():
            if not force:
                return
            self._edit_task.cancel()
        self._edit_task = asyncio.create_task(self._throttled_progress_send(force=force))

    async def _throttled_progress_send(self, *, force: bool = False) -> None:
        now = time.monotonic()
        wait = 0.0 if force else max(0.0, self._edit_interval - (now - self._last_edit))
        if wait:
            await asyncio.sleep(wait)
        await self._maybe_send_progress_snapshot()
        self._last_edit = time.monotonic()

    async def _maybe_send_progress_snapshot(self) -> None:
        buf = self._buffer
        if buf is None or buf.status == "done":
            return
        html = buffer_to_max_html(buf)
        if not html.strip():
            return
        message_id = self._progress_message_id or self.session.live_message_id
        if message_id:
            try:
                await self._client.edit_message(message_id, html, fmt="html")
                return
            except Exception:
                logger.exception("MAX progress edit failed; sending snapshot")
        try:
            await self._send_outbound(html, fmt="html")
        except Exception:
            logger.exception("MAX progress snapshot send failed")

    async def _outbound_worker_loop(self) -> None:
        queue = self._outbound_queue
        if queue is None:
            return
        try:
            while True:
                job = await queue.get()
                try:
                    if job is None:
                        break
                    await job
                except Exception:
                    logger.exception("MAX outbound delivery failed")
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass

    def enqueue_outbound(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Queue outbound MAX messages (tools, finals) in FIFO order."""
        queue = self._outbound_queue
        if queue is None:
            return
        try:
            queue.put_nowait(coro)
        except Exception:
            asyncio.create_task(queue.put(coro))

    async def drain_outbound(self) -> None:
        queue = self._outbound_queue
        if queue is None:
            return
        await queue.join()
        await queue.put(None)
        if self._outbound_worker and not self._outbound_worker.done():
            await self._outbound_worker
        self._outbound_worker = None
        self._outbound_queue = None

    async def send_notice(self, text: str) -> None:
        await self._send_outbound(text)

    async def send_tool_progress(self, tool_name: str, detail: str = "") -> None:
        label = (tool_name or "tool").strip()
        extra = f": {detail[:200]}" if detail else ""
        try:
            await self._send_outbound(f"🔧 {label}{extra}")
            logger.info("MAX tool progress sent (%s)", label)
        except Exception:
            logger.exception("MAX tool progress send failed")

    async def send_tool_result_notice(self, tool_name: str, body: str) -> None:
        label = (tool_name or "tool").strip()
        preview = (body or "").strip()
        if not preview:
            return
        if len(preview) > 1200:
            preview = preview[:1180] + "…"
        try:
            await self._send_outbound(f"📋 {label}\n{preview}")
            logger.info("MAX tool result sent (%s, %d chars)", label, len(preview))
        except Exception:
            logger.exception("MAX tool result send failed")

    def note_final_content(self, content: str) -> None:
        text = (content or "").strip()
        if text:
            self._final_content = text
            logger.info("MAX final answer noted (%d chars)", len(text))

    async def deliver_final_answer(self, content: str) -> None:
        if self._final_delivered:
            return
        content = (content or "").strip()
        if not content:
            return
        try:
            sent = await self.send_final_answer_split(content)
            if sent > 0:
                self._final_delivered = True
                logger.info(
                    "MAX final answer delivered (%d chunk(s), target=%s)",
                    sent,
                    self._reply_kwargs(),
                )
            else:
                logger.error("MAX final answer delivery sent 0 chunks")
        except Exception:
            logger.exception("MAX final answer delivery failed")

    async def send_final_answer_split(self, content: str) -> int:
        if not content or not content.strip():
            return 0
        html = plain_to_max_html(content)
        chunks = split_max_html(html)
        if not chunks:
            chunks = [prepare_max_html(content)]
        sent = 0
        for chunk in chunks:
            if await self._send_final_chunk(chunk, raw_fallback=content):
                sent += 1
            await asyncio.sleep(0.08)
        return sent

    async def _send_final_chunk(self, chunk: str, *, raw_fallback: str = "") -> bool:
        body = (chunk or "").strip()
        if not body:
            return False

        variants: list[tuple[str, str | None]] = [
            (body, "html"),
            (prepare_max_markdown(raw_fallback or body), "markdown"),
            (truncate_max_text(raw_fallback or body), None),
        ]
        seen: set[str] = set()
        last_error: Exception | None = None

        for text, fmt in variants:
            payload = (text or "").strip()
            if not payload or payload in seen:
                continue
            seen.add(payload)
            for attempt in range(4):
                try:
                    await self._send_outbound(payload, fmt=fmt)
                    return True
                except MaxApiError as exc:
                    last_error = exc
                    if exc.status == 429 and attempt < 3:
                        await asyncio.sleep(min(2**attempt, 8))
                        continue
                    break
                except Exception as exc:
                    last_error = exc
                    break

        if last_error is not None:
            logger.error("MAX final chunk delivery failed: %s", last_error)
        return False

    def _content_for_final_delivery(self) -> str:
        if self._final_content:
            return self._final_content
        buf = self._buffer
        if buf is None or buf.status != "done":
            return ""
        answer = (buf.answer or "").strip()
        if answer in {"", "✓ Done — full answer below."}:
            return ""
        return answer

    async def ensure_final_delivered(self) -> None:
        if self._final_delivered:
            logger.debug("MAX final delivery skipped (already delivered)")
            return
        content = self._content_for_final_delivery()
        if content:
            await self.deliver_final_answer(content)
            if not self._final_delivered:
                try:
                    await self.send_notice(
                        "✗ Не удалось доставить ответ в MAX. Попробуйте ещё раз."
                    )
                    self._final_delivered = True
                except Exception:
                    logger.exception("MAX delivery failure notice failed")
            return
        logger.warning(
            "MAX final delivery: no content (final_content=%s, buffer_status=%s)",
            bool(self._final_content),
            self._buffer.status if self._buffer is not None else None,
        )
        buf = self._buffer
        if buf is not None and buf.status == "error":
            err = self._error_message(buf)
            try:
                await self.send_notice(f"✗ Ошибка: {err}")
                self._final_delivered = True
            except Exception:
                logger.exception("MAX error notice failed")

    @staticmethod
    def _error_message(buf) -> str:
        answer = (buf.answer or "").strip()
        if answer:
            return answer
        for note in reversed(buf.notes):
            text = (note or "").strip()
            if text.lower().startswith("error:"):
                return text.split(":", 1)[1].strip() or "неизвестная ошибка"
        if buf.notes:
            return str(buf.notes[-1]).strip()
        return "неизвестная ошибка"

    async def finish(self) -> None:
        logger.info(
            "MAX presenter finish (has_final=%s, delivered=%s)",
            bool(self._final_content),
            self._final_delivered,
        )
        self.stop_heartbeat()
        if self._edit_task and not self._edit_task.done():
            try:
                await self._edit_task
            except Exception:
                pass
        await self.drain_outbound()
        await self.ensure_final_delivered()