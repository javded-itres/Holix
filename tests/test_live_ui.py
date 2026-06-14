"""Tests for messenger live UI localization."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.i18n import LocaleStore
from core.i18n.live_ui import (
    live_holix_thinking_label,
    live_thinking_label,
    live_working_label,
)
from core.presenters.live_buffer import LiveTranscriptBuffer
from integrations.max.render import buffer_to_max_html
from integrations.telegram.render import buffer_to_telegram_html


def _patch_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))


def test_live_labels_ru_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("admin").set("ru")

    assert live_working_label("admin") == "Работаю…"
    assert live_holix_thinking_label("admin", "ReAct") == "Holix думает… (режим: ReAct)"
    assert live_thinking_label(
        "admin",
        fallback="Holix is thinking... (mode: ReAct)",
    ) == "Holix думает… (режим: ReAct)"
    assert live_thinking_label("admin", fallback="Thinking (step 2)…") == "Шаг 2: размышление…"
    assert live_thinking_label(
        "admin",
        fallback="Generating execution plan (timeout: 90s)...",
    ) == "Формирую план выполнения (таймаут: 90 с)…"


def test_render_hides_streamed_answer_when_published_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("admin").set("ru")

    buf = LiveTranscriptBuffer(profile="admin", mode="react")
    buf.publish_answer_separately = True
    buf.set_thinking("Model is reasoning…")
    buf.set_answer("The user wants an analysis on VK advertising.")

    html = buffer_to_max_html(buf)
    tg_html = buffer_to_telegram_html(buf)

    assert "The user wants" not in html
    assert "The user wants" not in tg_html
    assert "размышляет" in html
    assert "Working" not in html


def test_render_plain_hides_answer_when_published_separately() -> None:
    buf = LiveTranscriptBuffer(profile="admin", mode="react")
    buf.publish_answer_separately = True
    buf.set_answer("English preamble should not appear")
    text = buf.render_plain()
    assert "English preamble" not in text