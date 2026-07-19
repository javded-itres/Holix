"""Sub-agent handle status serialization for Studio monitoring."""

from core.subagents.base import (
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)


def test_record_activity_and_to_status_dict() -> None:
    handle = SubAgentHandle(
        name="researcher-1",
        config=SubAgentConfig(name="researcher-1", process_mode=ProcessMode.ASYNC, max_steps=8),
        status=SubAgentStatus.RUNNING,
        agent_type="researcher",
        task_preview="Find API docs",
        max_steps=8,
    )
    handle.record_activity("step", "Reasoning step 1/8", steps_taken=1)
    handle.record_activity(
        "tool_start",
        "Calling web_search",
        tool_name="web_search",
        details='{"q":"docs"}',
        steps_taken=1,
    )

    payload = handle.to_status_dict()
    assert payload["name"] == "researcher-1"
    assert payload["running"] is True
    assert payload["steps_taken"] == 1
    assert payload["max_steps"] == 8
    assert payload["last_tool"] == "web_search"
    assert payload["current_activity"] == "Calling web_search"
    assert len(payload["activity_log"]) == 2
    assert "result" not in payload

    handle.status = SubAgentStatus.COMPLETED
    handle.result = SubAgentResult(
        name="researcher-1",
        success=True,
        response="Found three endpoints",
        steps_taken=2,
        tool_calls=[{"name": "web_search"}],
    )
    done = handle.to_status_dict()
    assert done["done"] is True
    assert done["result"]["success"] is True
    assert "Found three endpoints" in done["result"]["response"]
