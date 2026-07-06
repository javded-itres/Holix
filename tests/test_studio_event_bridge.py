"""Tests for Studio agent event bridge."""

from __future__ import annotations

from core.agent_events import ErrorEvent, ToolCallErrorEvent, ToolCallResultEvent
from core.security.confirmation_events import (
    ConfirmationRequestEvent,
    ConfirmationResponseEvent,
)
from core.subagents.interaction_events import SubAgentQuestionEvent
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


def test_confirmation_events_are_not_mapped_to_error() -> None:
    req = ConfirmationRequestEvent(
        confirmation_id="c1",
        tool_name="run_terminal_command",
        reason="Dangerous command",
    )
    msg = agent_event_to_studio_message(req)
    assert msg["type"] == "confirmation_request"
    assert "message" not in msg

    resp = ConfirmationResponseEvent(
        confirmation_id="c1",
        choice="deny",
        tool_name="run_terminal_command",
    )
    msg = agent_event_to_studio_message(resp)
    assert msg["type"] == "confirmation_response"
    assert "message" not in msg


def test_subagent_question_not_mapped_to_error() -> None:
    event = SubAgentQuestionEvent(
        request_id="q1",
        subagent_name="researcher",
        question="Continue?",
    )
    msg = agent_event_to_studio_message(event)
    assert msg["type"] == "subagent_question"
    assert "message" not in msg


def test_empty_error_event_has_no_message_field() -> None:
    event = ErrorEvent(error="")
    msg = agent_event_to_studio_message(event)
    assert msg["type"] == "error"
    assert "message" not in msg


def test_tool_call_error_maps_message() -> None:
    event = ToolCallErrorEvent(tool_name="read_file", tool_id="1", error="not found")
    msg = agent_event_to_studio_message(event)
    assert msg["type"] == "tool_call_error"
    assert msg["message"] == "not found"
    assert msg["tool_name"] == "read_file"