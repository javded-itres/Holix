"""LLM assistant text extraction."""

from __future__ import annotations

from pathlib import Path

import cli.core as cli_core
import pytest
from types import SimpleNamespace

from core.i18n import LocaleStore
from core.llm.response_text import (
    assistant_message_parts,
    resolve_assistant_text,
    stream_delta_parts,
)


def _patch_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)


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
    assert "The user is asking" not in text
    assert "размышление" in text.lower()


def test_resolve_reasoning_only_defaults_to_english() -> None:
    text = resolve_assistant_text(
        content="",
        reasoning_content="Internal chain of thought.",
    )
    assert "visible answer" in text.lower()


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
    assert "visible answer" in resolved.lower()