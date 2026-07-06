"""Tests for Studio agent event bridge."""

from __future__ import annotations

from core.agent_events import ToolCallResultEvent
from core.tools.file_diff import DIFF_SEPARATOR, format_write_file_result
from integrations.desktop.event_bridge import agent_event_to_studio_message


def test_write_file_diff_extracted() -> None:
    result = format_write_file_result("src/a.py", "old\n", "new\n")
    event = ToolCallResultEvent(tool_name="write_file", tool_id="1", result=result)
    msg = agent_event_to_studio_message(event)
    assert msg["type"] == "tool_call_result"
    assert "file_diff" in msg
    assert msg["file_diff"]["path"] == "src/a.py"
    assert DIFF_SEPARATOR not in msg["file_diff"]["unified"] or msg["file_diff"]["unified"]