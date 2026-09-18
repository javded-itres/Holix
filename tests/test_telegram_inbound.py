"""Telegram inbound: quotes, replies, and in-flight file gate."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from integrations.telegram.inbound import (
    InboundFileGate,
    compose_telegram_inbound_text,
    telegram_quote_text,
    telegram_reply_body,
)


def test_quote_and_reply_body() -> None:
    msg = SimpleNamespace(
        quote=SimpleNamespace(text="  selected rows  "),
        reply_to_message=SimpleNamespace(text="full original", caption=None),
    )
    assert telegram_quote_text(msg) == "selected rows"
    assert telegram_reply_body(msg) == "full original"
    cap = SimpleNamespace(
        quote=None,
        reply_to_message=SimpleNamespace(text=None, caption="doc caption"),
    )
    assert telegram_quote_text(cap) == ""
    assert telegram_reply_body(cap) == "doc caption"


def test_compose_includes_quote_and_user_text() -> None:
    msg = SimpleNamespace(
        quote=SimpleNamespace(text="Актив 1: 1000000"),
        reply_to_message=SimpleNamespace(text="Актив 1: 1000000\nАктив 2: 50000", caption=None),
    )
    out = compose_telegram_inbound_text(msg, user_text="Сделай вот это", locale="ru")
    assert "Актив 1: 1000000" in out
    assert "Сделай вот это" in out
    assert "Цитата" in out
    assert "Сообщение пользователя" in out
    assert "Актив 2: 50000" in out


def test_compose_reply_without_quote() -> None:
    msg = SimpleNamespace(
        quote=None,
        reply_to_message=SimpleNamespace(text=None, caption="ТЗ Мухин.docx"),
    )
    out = compose_telegram_inbound_text(msg, user_text="Видишь документ?", locale="ru")
    assert "ТЗ Мухин.docx" in out
    assert "Видишь документ?" in out
    assert "на которое отвечают" in out


def test_compose_plain_text_unchanged() -> None:
    msg = SimpleNamespace(quote=None, reply_to_message=None)
    assert compose_telegram_inbound_text(msg, user_text="привет", locale="ru") == "привет"


@pytest.mark.asyncio
async def test_file_gate_text_waits_for_inflight_save() -> None:
    gate = InboundFileGate(timeout_s=5)
    order: list[str] = []
    chat_id = 73327391
    started = asyncio.Event()

    async def save_file() -> None:
        gate.begin(chat_id)
        started.set()
        await asyncio.sleep(0.05)
        order.append("saved")
        gate.end(chat_id)

    async def follow_up_text() -> None:
        await started.wait()
        await gate.wait_idle(chat_id)
        order.append("text")

    await asyncio.gather(save_file(), follow_up_text())
    assert order == ["saved", "text"]
    assert gate.pending(chat_id) == 0
