"""Metrics message formatting."""

from __future__ import annotations

from cli.shared.rich_text import content_to_plain_text
from core.monitoring.metrics import format_metrics_message
from rich.panel import Panel


def test_format_metrics_message_renders_counts() -> None:
    text = format_metrics_message(
        {
            "total_requests": 3,
            "total_tool_calls": 7,
            "total_errors": 1,
            "avg_response_time": 1.25,
            "min_response_time": 0.5,
            "max_response_time": 2.0,
        }
    )
    assert "**Holix metrics**" in text
    assert "Requests: 3" in text
    assert "Tool calls: 7" in text
    assert "1.25s" in text


def test_content_to_plain_text_from_panel() -> None:
    plain = content_to_plain_text(Panel("hello", title="metrics"))
    assert "hello" in plain
    assert "Panel object" not in plain