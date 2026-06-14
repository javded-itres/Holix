"""LLM assistant text extraction."""

from __future__ import annotations

from types import SimpleNamespace

from core.llm.response_text import (
    assistant_message_parts,
    resolve_assistant_text,
    stream_delta_parts,
)


def test_stream_delta_reasoning_only() -> None:
    delta = SimpleNamespace(content=None, reasoning_content="Размышляю…")
    content, reasoning = stream_delta_parts(delta)
    assert content == ""
    assert reasoning == "Размышляю…"


def test_resolve_prefers_content_over_reasoning() -> None:
    text = resolve_assistant_text(
        content="Ответ",
        reasoning_content="Длинные размышления",
    )
    assert text == "Ответ"


def test_resolve_uses_reasoning_when_content_empty() -> None:
    text = resolve_assistant_text(
        content="",
        reasoning_content="Итог из reasoning",
    )
    assert text == "Итог из reasoning"


def test_resolve_length_finish_reason() -> None:
    text = resolve_assistant_text(content="", finish_reason="length")
    assert "лимитом токенов" in text


def test_assistant_message_parts() -> None:
    msg = SimpleNamespace(content=None, reasoning_content="Вывод модели")
    content, reasoning = assistant_message_parts(msg)
    assert content == ""
    assert reasoning == "Вывод модели"
    assert resolve_assistant_text(content=content, reasoning_content=reasoning) == "Вывод модели"