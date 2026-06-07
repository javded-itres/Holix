"""Single Telegram message updated via editMessageText."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from integrations.telegram.markdown import (
    markdown_to_telegram_html,
    plain_to_telegram_html,
    split_telegram_html,
    truncate_telegram_html,
)
from integrations.telegram.render import buffer_to_telegram_html

if TYPE_CHECKING:
    from integrations.telegram.session import ChatSession


class TelegramLivePresenter:
    def __init__(self, bot: Any, session: ChatSession, *, edit_interval_ms: int = 500) -> None:
        self._bot = bot
        self.session = session
        self._edit_interval = edit_interval_ms / 1000.0
        self._last_edit = 0.0
        self._edit_task: asyncio.Task | None = None
        self._buffer = session.live_buffer

    @property
    def buffer(self):
        return self.session.live_buffer

    async def start(self) -> None:
        self.session.bump_live_buffer()
        self._buffer = self.session.live_buffer
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
        except Exception:
            answer = (self._buffer.answer or "").strip()
            fallback = plain_to_telegram_html(answer or "…")
            try:
                await self._edit_html(truncate_telegram_html(fallback))
            except Exception:
                pass

    async def _edit_html(self, text: str) -> None:
        await self._bot.edit_message_text(
            text,
            chat_id=self.session.chat_id,
            message_id=self.session.live_message_id,
            parse_mode="HTML",
        )

    async def send_notice(self, text: str) -> None:
        await self._bot.send_message(
            self.session.chat_id,
            plain_to_telegram_html(text),
            parse_mode="HTML",
        )

    async def send_final_answer_split(self, content: str) -> None:
        """Send a (potentially long) final assistant response as 1+ messages.

        Splits after converting to Telegram HTML so each chunk respects the
        4096 char limit.
        """
        if not content or not content.strip():
            return
        try:
            html = markdown_to_telegram_html(content)
            chunks = split_telegram_html(html)
            for chunk in chunks:
                await self._bot.send_message(
                    self.session.chat_id,
                    chunk,
                    parse_mode="HTML",
                )
                # tiny delay to preserve send order in Telegram
                await asyncio.sleep(0.08)
        except Exception:
            # Last resort: send a truncated version as one message
            try:
                fallback = truncate_telegram_html(
                    plain_to_telegram_html(content[:3800])
                )
                await self._bot.send_message(
                    self.session.chat_id,
                    fallback,
                    parse_mode="HTML",
                )
            except Exception:
                pass