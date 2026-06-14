"""Single Telegram message updated via editMessageText."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from core.presenters.final_content import is_placeholder_final

from integrations.telegram.markdown import (
    escape_html,
    markdown_to_telegram_html,
    plain_to_telegram_html,
    split_telegram_html,
    truncate_telegram_html,
)
from integrations.telegram.render import buffer_to_telegram_html

if TYPE_CHECKING:
    from integrations.telegram.session import ChatSession

logger = logging.getLogger(__name__)


def _is_not_modified(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "message is not modified" in text or "message_not_modified" in text


class TelegramLivePresenter:
    def __init__(self, bot: Any, session: ChatSession, *, edit_interval_ms: int = 500) -> None:
        self._bot = bot
        self.session = session
        self._edit_interval = edit_interval_ms / 1000.0
        self._last_edit = 0.0
        self._edit_task: asyncio.Task | None = None
        self._buffer = session.live_buffer
        self._final_delivered = False
        self._final_content: str | None = None
        self._outbound_queue: asyncio.Queue[Coroutine[Any, Any, Any] | None] | None = None
        self._outbound_worker: asyncio.Task | None = None

    @property
    def buffer(self):
        return self.session.live_buffer

    @property
    def final_delivered(self) -> bool:
        return self._final_delivered

    async def start(self) -> None:
        self.session.bump_live_buffer()
        self._buffer = self.session.live_buffer
        self._buffer.publish_answer_separately = True
        self._final_delivered = False
        self._final_content = None
        self._outbound_queue = asyncio.Queue()
        self._outbound_worker = asyncio.create_task(self._outbound_worker_loop())
        text = buffer_to_telegram_html(self._buffer)
        msg = await self._bot.send_message(
            self.session.chat_id,
            text,
            parse_mode="HTML",
        )
        self.session.live_message_id = msg.message_id

    def schedule_edit(self, *, force: bool = False) -> None:
        if self._edit_task and not self._edit_task.done():
            if not force:
                return
            self._edit_task.cancel()
        self._edit_task = asyncio.create_task(self._throttled_edit(force=force))

    async def _throttled_edit(self, *, force: bool = False) -> None:
        now = time.monotonic()
        wait = 0.0 if force else max(0.0, self._edit_interval - (now - self._last_edit))
        if wait:
            await asyncio.sleep(wait)
        await self._do_edit()
        self._last_edit = time.monotonic()

    async def _do_edit(self) -> None:
        if self.session.live_message_id is None or self._buffer is None:
            return
        text = buffer_to_telegram_html(self._buffer)
        try:
            await self._edit_html(text)
        except Exception as exc:
            if _is_not_modified(exc):
                return
            if self._buffer.status == "done":
                fallback = "<i>✓ Готово</i>"
            elif self._buffer.status == "error":
                fallback = "<b>✗ Ошибка</b>"
            else:
                answer = (self._buffer.answer or "").strip()
                if answer:
                    fallback = markdown_to_telegram_html(answer) or escape_html(answer)
                else:
                    fallback = "<i>⏳ Working…</i>"
            try:
                await self._edit_html(truncate_telegram_html(fallback))
            except Exception as retry_exc:
                if not _is_not_modified(retry_exc):
                    logger.debug("Telegram live edit fallback failed: %s", retry_exc)

    async def _edit_html(self, text: str) -> None:
        await self._bot.edit_message_text(
            text,
            chat_id=self.session.chat_id,
            message_id=self.session.live_message_id,
            parse_mode="HTML",
        )

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
                    logger.exception("Telegram outbound delivery failed")
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass

    def enqueue_outbound(self, coro: Coroutine[Any, Any, Any]) -> None:
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
        await self._bot.send_message(
            self.session.chat_id,
            plain_to_telegram_html(text),
            parse_mode="HTML",
        )

    def note_final_content(self, content: str) -> None:
        text = (content or "").strip()
        if text and not is_placeholder_final(text):
            self._final_content = text

    async def deliver_result(self, content: str) -> None:
        """Post the final agent/work result as one or more new chat messages."""
        await self.deliver_final_answer(content)

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
        except Exception:
            logger.exception("Telegram final answer delivery failed")

    async def send_final_answer_split(self, content: str) -> int:
        """Send a (potentially long) final assistant response as 1+ messages.

        Splits after converting to Telegram HTML so each chunk respects the
        4096 char limit.
        """
        if not content or not content.strip():
            return 0
        try:
            html = markdown_to_telegram_html(content)
            chunks = split_telegram_html(html)
            sent = 0
            for chunk in chunks:
                await self._bot.send_message(
                    self.session.chat_id,
                    chunk,
                    parse_mode="HTML",
                )
                sent += 1
                await asyncio.sleep(0.08)
            return sent
        except Exception:
            try:
                fallback = truncate_telegram_html(
                    plain_to_telegram_html(content[:3800])
                )
                await self._bot.send_message(
                    self.session.chat_id,
                    fallback,
                    parse_mode="HTML",
                )
                return 1
            except Exception:
                logger.exception("Telegram final answer fallback failed")
                return 0

    def _content_for_final_delivery(self) -> str:
        if self._final_content and not is_placeholder_final(self._final_content):
            return self._final_content
        buf = self._buffer
        if buf is None or buf.status != "done":
            return ""
        answer = (buf.answer or "").strip()
        if answer in {"", "✓ Done — full answer below."} or is_placeholder_final(answer):
            return ""
        return answer

    async def ensure_final_delivered(self) -> None:
        if self._final_delivered:
            return
        content = self._content_for_final_delivery()
        if content:
            await self.deliver_final_answer(content)
            if not self._final_delivered:
                try:
                    await self.send_notice(
                        "✗ Не удалось доставить ответ в Telegram. Попробуйте ещё раз."
                    )
                    self._final_delivered = True
                except Exception:
                    logger.exception("Telegram delivery failure notice failed")
            return
        buf = self._buffer
        if buf is not None and buf.status == "error":
            err = self._error_message(buf)
            try:
                await self.send_notice(f"✗ Ошибка: {err}")
                self._final_delivered = True
            except Exception:
                logger.exception("Telegram error notice failed")
            return
        if buf is not None and buf.status == "running":
            buf.mark_error("агент завершился без ответа")
            try:
                await self.send_notice(
                    "✗ Агент завершился без ответа. "
                    "Проверьте модель (/models) или повторите запрос."
                )
                self._final_delivered = True
            except Exception:
                logger.exception("Telegram incomplete-run notice failed")

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
        if self._edit_task and not self._edit_task.done():
            try:
                await self._edit_task
            except Exception:
                pass
        await self._do_edit()
        await self.drain_outbound()
        await self.ensure_final_delivered()