"""Telegram inline keyboard helpers."""

from __future__ import annotations

import pytest

from integrations.telegram.keyboards import (
    MODE_LABELS,
    parse_callback,
    mode_picker_html,
)


def test_parse_callback_valid() -> None:
    assert parse_callback("hx:m:react") == ("m", "react")
    assert parse_callback("hx:pi:2") == ("pi", "2")
    assert parse_callback("bad") is None


def test_mode_callback_data_within_limit() -> None:
    for mode in MODE_LABELS:
        data = f"hx:m:{mode}"
        assert len(data) <= 64


def test_mode_picker_html_marks_current() -> None:
    html = mode_picker_html("react")
    assert "react" in html
    assert "✓" in html


def test_profile_model_summary_missing_profile() -> None:
    from integrations.telegram.interactive import profile_model_summary

    headline, rows = profile_model_summary("___nonexistent_profile_xyz___")
    assert headline == "—" or rows is not None