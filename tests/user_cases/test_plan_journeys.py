"""P1 plan_and_execute user cases (scripted plan JSON + step tools)."""

from __future__ import annotations

import json

import pytest

from tests.user_cases.scripted_llm import Final, ToolCall

# ≥3 substantive steps — plan quality gate rejects single-step plans.
_MINIMAL_PLAN = {
    "analysis": {
        "task_summary": "Create and verify a workspace note",
        "complexity": "simple",
        "clarifying_questions": [],
        "constraints": [],
    },
    "architecture": {
        "approach": "Direct file tools",
        "tech_stack": ["filesystem"],
        "structure": "workspace files",
        "risks": [],
    },
    "plan": [
        {
            "step": 1,
            "description": "Write note.txt with hello-plan",
            "tools_needed": ["write_file"],
            "expected_output": "file created",
            "success_criteria": "file exists",
            "depends_on": [],
            "parallel_group": None,
            "subagent_type": None,
        },
        {
            "step": 2,
            "description": "Read note.txt to verify content",
            "tools_needed": ["read_file"],
            "expected_output": "hello-plan",
            "success_criteria": "content matches",
            "depends_on": [1],
            "parallel_group": None,
            "subagent_type": None,
        },
        {
            "step": 3,
            "description": "Summarize success for the user",
            "tools_needed": [],
            "expected_output": "summary",
            "success_criteria": "user informed",
            "depends_on": [2],
            "parallel_group": None,
            "subagent_type": None,
        },
    ],
}


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc10_plan_and_execute_write_verify(harness):
    """UC-10: plan JSON → auto-approve (review off) → step tools → PlanCompleted."""
    harness.script(
        [
            Final(json.dumps(_MINIMAL_PLAN)),
            ToolCall(
                "write_file",
                {"path": "note.txt", "content": "hello-plan"},
            ),
            Final("Step 1 done: wrote note.txt"),
            ToolCall("read_file", {"path": "note.txt"}),
            Final("Step 2 done: verified hello-plan"),
            Final("All plan steps complete. note.txt contains hello-plan."),
        ]
    )

    result = await harness.run(
        "Create note.txt with hello-plan and verify it",
        mode="plan_and_execute",
        conversation_id="uc10_plan",
    )

    result.assert_no_error_events()
    result.assert_plan_generated(min_steps=3)
    result.assert_plan_completed()
    result.assert_tools_called("write_file", "read_file")
    assert harness.workspace.exists("note.txt")
    assert harness.workspace.read("note.txt") == "hello-plan"
    assert "hello-plan" in result.tool_result_text("read_file")
    result.assert_final_contains("hello-plan")


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc11_hybrid_write_verify(harness):
    """UC-11: hybrid mode — plan + step tools (same orchestration as plan mode)."""
    harness.script(
        [
            Final(json.dumps(_MINIMAL_PLAN)),
            ToolCall(
                "write_file",
                {"path": "hybrid.txt", "content": "hello-hybrid"},
            ),
            Final("Step 1 done: wrote hybrid.txt"),
            ToolCall("read_file", {"path": "hybrid.txt"}),
            Final("Step 2 done: verified hello-hybrid"),
            Final("All hybrid steps complete. hybrid.txt contains hello-hybrid."),
        ]
    )

    result = await harness.run(
        "Create hybrid.txt with hello-hybrid and verify it",
        mode="hybrid",
        conversation_id="uc11_hybrid",
    )

    result.assert_no_error_events()
    result.assert_plan_generated(min_steps=3)
    result.assert_plan_completed()
    result.assert_tools_called("write_file", "read_file")
    assert harness.workspace.exists("hybrid.txt")
    assert harness.workspace.read("hybrid.txt") == "hello-hybrid"
    result.assert_final_contains("hello-hybrid")
