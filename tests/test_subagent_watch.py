"""Live sub-agent watch text and job listing."""

from __future__ import annotations

from integrations.messenger.subagent_watch import (
    format_list_text,
    format_watch_text,
    last_activity_steps,
    map_job_tokens,
    resolve_job_token,
)


def test_last_activity_steps_keeps_five() -> None:
    job = {
        "activity_log": [
            {"kind": "status", "message": f"step {i}", "steps_taken": i} for i in range(1, 9)
        ]
    }
    steps = last_activity_steps(job, limit=5)
    assert [e["steps_taken"] for e in steps] == [4, 5, 6, 7, 8]


def test_format_watch_text_includes_steps_and_name() -> None:
    job = {
        "name": "coder",
        "status": "running",
        "steps_taken": 4,
        "max_steps": 10,
        "task_preview": "fix gateway",
        "current_activity": "writing files",
        "activity_log": [
            {"kind": "tool", "message": "write_file", "tool_name": "write_file", "steps_taken": 3},
            {"kind": "thinking", "message": "Reasoning step 4", "steps_taken": 4},
        ],
    }
    text = format_watch_text(job, html=False, locale="en")
    assert "coder" in text
    assert "write_file" in text
    assert "Reasoning step 4" in text
    html = format_watch_text(job, html=True, locale="ru")
    assert "<b>" in html
    assert "coder" in html


def test_format_list_empty() -> None:
    assert "No sub-agents" in format_list_text([], html=False, locale="en")


def test_map_job_tokens_roundtrip() -> None:
    mapping: dict[str, str] = {}
    tokens = map_job_tokens(mapping, ["telegram-1::coder", "studio-2::researcher"])
    assert len(tokens) == 2
    assert resolve_job_token(mapping, tokens["telegram-1::coder"]) == "telegram-1::coder"
    map_job_tokens(mapping, ["only"])
    assert "telegram-1::coder" not in mapping.values()
