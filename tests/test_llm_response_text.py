"""LLM assistant text extraction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cli.core as cli_core
import pytest

from core.i18n import LocaleStore
from core.llm.response_text import (
    assistant_message_parts,
    collapse_repetitive_text,
    is_pathological_repetition,
    resolve_assistant_text,
    stream_delta_parts,
    strip_reasoning_markup,
)


def _patch_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)


def test_strip_reasoning_markup_removes_think_blocks() -> None:
    raw = "<think>\nПользователь просит версию.\n</think>\nHolix 1.0.4"
    assert strip_reasoning_markup(raw) == "Holix 1.0.4"
    assert "</think>" not in strip_reasoning_markup("Начинаю.</think>\n…Поняла. Ответ.")
    assert "Поняла" in strip_reasoning_markup("Начинаю.</think>\n…Поняла. Ответ.")


def test_resolve_strips_think_markup_from_content() -> None:
    text = resolve_assistant_text(
        content="<think>secret</think>\nГотово: версия 1.0.4",
    )
    assert text == "Готово: версия 1.0.4"
    assert "secret" not in text


def test_collapse_repetitive_loop_phrase() -> None:
    unit = "Сейчас проверю текущее состояние кода и процесса, а затем доделаю меню.…"
    looped = unit * 40
    assert is_pathological_repetition(looped)
    collapsed = collapse_repetitive_text(looped)
    assert collapsed.count("Сейчас проверю") <= 2
    assert len(collapsed) < 300
    resolved = resolve_assistant_text(content=looped)
    assert resolved.count("Сейчас проверю") <= 2


def test_collapse_alternating_mcp_monologue() -> None:
    """Real TG spam: short ack + same action phrase, glued ellipsis, different lead-in."""
    cycle = "Поняла. Проверяю статус бота через MCP.…"
    raw = "Проверяю статус бота через MCP-инструмент.…" + cycle * 60
    assert is_pathological_repetition(raw)
    collapsed = collapse_repetitive_text(raw)
    assert collapsed.count("Проверяю статус бота") <= 3
    assert collapsed.count("Поняла") <= 2
    assert len(collapsed) < 400
    assert "MCP" in collapsed


def test_collapse_pure_ab_cycle() -> None:
    cycle = "Поняла. Проверяю статус бота через MCP.…"
    raw = cycle * 50
    assert is_pathological_repetition(raw)
    collapsed = collapse_repetitive_text(raw)
    assert len(collapsed) < 200
    assert collapsed.count("Поняла") <= 2


def test_resolve_length_finish_stops_pathological_loop() -> None:
    """Modern pipeline: finish_reason=length adds truncation notice."""
    cycle = "Поняла. Проверяю статус бота через MCP.…"
    raw = cycle * 40
    text = resolve_assistant_text(content=raw, finish_reason="length", agent_pipeline="modern")
    assert "token" in text.lower() or "токен" in text.lower() or "обрезан" in text.lower()
    assert text.count("Поняла") <= 3
    assert len(text) < 500
    # Classic: collapsed text only, no truncation wall.
    classic = resolve_assistant_text(content=raw, finish_reason="length", agent_pipeline="classic")
    assert "обрезан" not in classic.lower()
    assert len(classic) < 200


def test_collapse_smotryu_mcp_server_loop() -> None:
    """Studio spam: «Да. Смотрю mcp_server.py…» glued many times."""
    unit = "Да. Смотрю mcp_server.py, чтобы добавить publish_news.…"
    raw = unit * 25
    assert is_pathological_repetition(raw, min_repeats=3)
    collapsed = collapse_repetitive_text(raw)
    assert collapsed.count("Смотрю mcp_server") <= 2
    assert len(collapsed) < 200


def test_collapse_bot_py_monologue_with_typo_variant() -> None:
    """Prod admin spam: «…Поняла. Запускаю bot.py…» × N + one bot_bot mutation.

    Dot inside ``bot.py`` must not break detection; one typo must not keep 18KB.
    """
    unit = "…Поняла. Запускаю бота `javded_content_bot.py` в фоновом процессе."
    mutant = "…Поняла. Запускаю бота `javded_content_bot_bot.py` в фоновом процессе."
    raw = unit * 47 + mutant + unit * 50
    assert len(raw) > 5000
    assert is_pathological_repetition(raw, min_repeats=3)
    collapsed = collapse_repetitive_text(raw)
    assert len(collapsed) < 300
    assert collapsed.count("Поняла") <= 2
    assert "Запускаю" in collapsed
    # Classic stop finish must not ship the multi-KB loop.
    resolved = resolve_assistant_text(content=raw, finish_reason="stop", agent_pipeline="classic")
    assert len(resolved) < 300
    assert resolved.count("Поняла") <= 2


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


def test_resolve_recovers_explicit_answer_from_reasoning() -> None:
    from core.llm.response_text import short_answer_from_reasoning

    assert short_answer_from_reasoning("I compute 17+25.\nAnswer: 42") == "42"
    assert short_answer_from_reasoning("thinking...\n42") == "42"
    text = resolve_assistant_text(
        content="",
        reasoning_content="User asked for sum.\nThe answer is 42",
        model="test",
    )
    assert text == "42"


def test_resolve_does_not_expose_reasoning_when_content_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("ru_profile").set("ru")
    text = resolve_assistant_text(
        content="",
        reasoning_content="The user is asking what I am doing.",
        profile_name="ru_profile",
    )
    # Empty → callers retry instead of painting "try again" mid-run.
    assert text == ""
    assert "The user is asking" not in text


def test_resolve_reasoning_only_is_empty_for_retry() -> None:
    text = resolve_assistant_text(
        content="",
        reasoning_content="Internal chain of thought.",
    )
    assert text == ""


def test_resolve_length_finish_reason_ru(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("ru_profile").set("ru")
    text = resolve_assistant_text(
        content="",
        finish_reason="length",
        profile_name="ru_profile",
    )
    assert "лимитом токенов" in text


def test_assistant_message_parts() -> None:
    msg = SimpleNamespace(content=None, reasoning_content="Вывод модели")
    content, reasoning = assistant_message_parts(msg)
    assert content == ""
    assert reasoning == "Вывод модели"
    resolved = resolve_assistant_text(content=content, reasoning_content=reasoning)
    assert resolved == ""
