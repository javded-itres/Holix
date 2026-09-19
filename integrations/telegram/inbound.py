"""Flatten Telegram quotes, replies, and in-flight file saves for the agent."""

from __future__ import annotations

import asyncio
from typing import Any


def telegram_quote_text(message: Any) -> str:
    """Selected excerpt when the user replies with a quote (Bot API TextQuote)."""
    quote = getattr(message, "quote", None)
    if quote is None:
        return ""
    return str(getattr(quote, "text", None) or "").strip()


def telegram_reply_body(message: Any) -> str:
    """Text or caption of the message being replied to (not the current message)."""
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return ""
    return (getattr(reply, "text", None) or getattr(reply, "caption", None) or "").strip()


def compose_telegram_inbound_text(
    message: Any,
    *,
    user_text: str,
    locale: str = "ru",
) -> str:
    """User turn the agent should see: quote and/or replied-to body + current text."""
    from core.i18n.messages import t

    quote = telegram_quote_text(message)
    reply_body = telegram_reply_body(message)
    user = (user_text or "").strip()
    parts: list[str] = []
    if quote:
        parts.append(t("msg.inbound.quote", locale))
        parts.append(quote)
        if reply_body and reply_body != quote:
            parts.append(t("msg.inbound.reply", locale))
            parts.append(reply_body)
    elif reply_body:
        parts.append(t("msg.inbound.reply", locale))
        parts.append(reply_body)
    if user:
        if parts:
            parts.append(t("msg.inbound.user", locale))
        parts.append(user)
    return "\n\n".join(parts).strip()


class InboundFileGate:
    """Per-chat barrier so follow-up text waits until in-flight file saves finish."""

    def __init__(self, *, timeout_s: float = 90.0) -> None:
        self._timeout_s = max(1.0, float(timeout_s))
        self._counts: dict[int, int] = {}
        self._events: dict[int, asyncio.Event] = {}

    def _event(self, chat_id: int) -> asyncio.Event:
        cid = int(chat_id)
        ev = self._events.get(cid)
        if ev is None:
            ev = asyncio.Event()
            ev.set()
            self._events[cid] = ev
        return ev

    def begin(self, chat_id: int) -> None:
        cid = int(chat_id)
        self._counts[cid] = self._counts.get(cid, 0) + 1
        self._event(cid).clear()

    def end(self, chat_id: int) -> None:
        cid = int(chat_id)
        n = max(0, self._counts.get(cid, 0) - 1)
        self._counts[cid] = n
        if n == 0:
            self._event(cid).set()

    def pending(self, chat_id: int) -> int:
        return int(self._counts.get(int(chat_id), 0))

    async def wait_idle(self, chat_id: int) -> None:
        try:
            await asyncio.wait_for(
                self._event(int(chat_id)).wait(),
                timeout=self._timeout_s,
            )
        except TimeoutError:
            pass
