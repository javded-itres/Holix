"""Tests for event correlation in monitoring."""

from core.agent_events import FinalResponseEvent, ToolCallStartEvent
from core.monitoring.event_fields import correlation_fields
from core.monitoring.metrics import MetricsCollector, create_metrics_subscriber
from core.security.confirmation_events import ConfirmationResponseEvent


def test_correlation_fields():
    event = FinalResponseEvent(
        content="ok",
        conversation_id="c1",
        run_id="run1",
        plan_id="plan1",
    )
    fields = correlation_fields(event)
    assert fields["conversation_id"] == "c1"
    assert fields["run_id"] == "run1"
    assert fields["plan_id"] == "plan1"
    assert fields["event_type"] == "final_response"


def test_metrics_subscriber_tracks_tool_and_confirmation():
    collector = MetricsCollector()
    handler = create_metrics_subscriber(collector)

    handler(
        ToolCallStartEvent(
            tool_name="read_file",
            conversation_id="c1",
            run_id="r1",
        )
    )
    handler(
        ConfirmationResponseEvent(
            choice="deny",
            tool_name="shell",
            conversation_id="c1",
            run_id="r1",
        )
    )

    assert collector.counters["tool_calls"] == 1
    assert collector.counters["tool.read_file"] == 1
    assert collector.counters["confirmation.deny"] == 1
    assert collector.counters["confirmation_deny"] == 1
    assert collector.counters["runs_with_correlation"] >= 2