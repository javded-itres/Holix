"""Append-only session trajectory log."""

from __future__ import annotations

from core.agent_events import FinalResponseEvent, ToolCallStartEvent
from core.runtime.trajectory import (
    TrajectoryLog,
    attach_trajectory_logger,
    event_to_record,
    format_trace_line,
    format_trace_report,
)


def test_event_to_record_redacts_and_skips_deltas() -> None:
    start = ToolCallStartEvent(
        conversation_id="tui_1",
        tool_name="write_file",
        arguments={"path": "a.py", "api_key": "sk-secret"},
        arguments_raw='{"api_key":"sk-secret"}',
    )
    rec = event_to_record(start)
    assert rec is not None
    assert rec["tool_name"] == "write_file"
    dumped = str(rec)
    assert "sk-secret" not in dumped
    assert "***" in dumped

    from core.agent_events import AssistantDeltaEvent

    assert event_to_record(AssistantDeltaEvent(content="tok")) is None


def test_trajectory_tail_and_search(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    log = TrajectoryLog("default")
    log.append(
        ToolCallStartEvent(conversation_id="sess_a", tool_name="read_file", arguments={"path": "x"})
    )
    log.append(FinalResponseEvent(conversation_id="sess_a", content="done with read_file"))
    rows = log.tail("sess_a", limit=10)
    assert len(rows) == 2
    text = format_trace_report(rows, conversation_id="sess_a")
    assert "read_file" in text
    hits = log.search("sess_a", "read_file")
    assert hits
    assert format_trace_line(hits[0])


def test_attach_trajectory_logger_is_idempotent() -> None:
    from core.agent_events import AgentEventBus

    class _Agent:
        def __init__(self) -> None:
            self.events = AgentEventBus(name="t")
            self.config = type("c", (), {"profile_name": "default"})()

    agent = _Agent()
    attach_trajectory_logger(agent)
    attach_trajectory_logger(agent)
    assert agent._trajectory_attached is True
    assert len(agent.events._handlers) == 1
