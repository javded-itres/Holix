"""
Tests for step orchestration and enriched planning.

Covers:
- step_orchestrate_node: step injection, step advancement, finalization
- route_after_react_plan: tool calls, step completion, final
- route_after_step_orchestrate: next step, finalize
- plan_node: detailed prompt with analysis/architecture
- New state fields: is_step_complete, current_step_start_count
- config: max_steps_per_plan_step
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.graph.state import HelixGraphState


# ─── Step Orchestrate Node ──────────────────────────────────────────────────

class TestStepOrchestrateNode:
    """Tests for step_orchestrate_node."""

    @pytest.mark.asyncio
    async def test_no_plan_steps_signals_finalize(self):
        """When no plan steps exist, signal finalization."""
        from core.graph.nodes.step_orchestrate_node import step_orchestrate_node

        state = HelixGraphState(
            plan_steps=[],
            current_plan_step=0,
            is_step_complete=False,
            step_count=5,
        )
        config = {"configurable": {"_agent": None}}

        result = await step_orchestrate_node(state, config)
        assert result["is_final"] is True

    @pytest.mark.asyncio
    async def test_all_steps_complete_signals_finalize(self):
        """When current_plan_step >= len(plan_steps), signal finalization."""
        from core.graph.nodes.step_orchestrate_node import step_orchestrate_node

        state = HelixGraphState(
            plan_steps=[{"step": 1, "description": "test"}],
            current_plan_step=1,  # Past the last step
            is_step_complete=False,
            step_count=5,
        )
        config = {"configurable": {"_agent": None}}

        result = await step_orchestrate_node(state, config)
        assert result["is_final"] is True

    @pytest.mark.asyncio
    async def test_step_complete_advances_to_next_step(self):
        """When is_step_complete=True, advance to next step."""
        from core.graph.nodes.step_orchestrate_node import step_orchestrate_node

        state = HelixGraphState(
            plan_steps=[
                {"step": 1, "description": "Step 1", "tools_needed": ["terminal"], "expected_output": "done", "success_criteria": "ok"},
                {"step": 2, "description": "Step 2", "tools_needed": ["write_file"], "expected_output": "done2", "success_criteria": "ok2"},
            ],
            current_plan_step=0,  # Step 1 is complete
            is_step_complete=True,
            step_count=3,
            messages=[],
        )
        config = {"configurable": {"_agent": None}}

        result = await step_orchestrate_node(state, config)
        assert result["current_plan_step"] == 1  # Advanced to step 2
        assert result["is_step_complete"] is False  # Reset for next step
        assert "messages" in result  # Step 2 context injected

    @pytest.mark.asyncio
    async def test_first_step_injects_context(self):
        """When starting the first step, inject step context."""
        from core.graph.nodes.step_orchestrate_node import step_orchestrate_node

        state = HelixGraphState(
            plan_steps=[
                {"step": 1, "description": "Create project", "tools_needed": ["terminal"], "expected_output": "project created", "success_criteria": "directory exists"},
            ],
            current_plan_step=0,
            is_step_complete=False,
            step_count=0,
            messages=[],
        )
        config = {"configurable": {"_agent": None}}

        result = await step_orchestrate_node(state, config)
        assert result["is_step_complete"] is False
        assert result["current_step_start_count"] == 0
        # Should have injected a user message with step context
        messages = result.get("messages", [])
        assert len(messages) > 0
        assert "[Plan Step 1/" in messages[-1]["content"]


# ─── Route After React Plan ──────────────────────────────────────────────────

class TestRouteAfterReactPlan:
    """Tests for route_after_react_plan router."""

    def test_tool_calls_routes_to_tool_execution(self):
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[{"id": "tc1", "function": {"name": "terminal", "arguments": "{}"}}],
            is_step_complete=False,
            is_final=False,
            step_count=1,
            max_steps=15,
        )
        assert route_after_react_plan(state) == "tool_execution"

    def test_is_final_routes_to_finalize(self):
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=False,
            is_final=True,
            step_count=5,
            max_steps=15,
        )
        assert route_after_react_plan(state) == "finalize"

    def test_step_complete_routes_to_orchestrate(self):
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=True,
            is_final=False,
            step_count=3,
            max_steps=15,
        )
        assert route_after_react_plan(state) == "step_orchestrate"

    def test_continue_react_loop(self):
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=False,
            is_final=False,
            step_count=1,
            max_steps=15,
        )
        assert route_after_react_plan(state) == "react"


# ─── Route After Step Orchestrate ────────────────────────────────────────────

class TestRouteAfterStepOrchestrate:
    """Tests for route_after_step_orchestrate router."""

    def test_has_steps_routes_to_react(self):
        from core.graph.nodes.step_orchestrate_node import route_after_step_orchestrate

        state = HelixGraphState(
            plan_steps=[{"step": 1, "description": "test"}],
            current_plan_step=0,
            is_final=False,
        )
        assert route_after_step_orchestrate(state) == "react"

    def test_final_routes_to_finalize(self):
        from core.graph.nodes.step_orchestrate_node import route_after_step_orchestrate

        state = HelixGraphState(
            plan_steps=[{"step": 1, "description": "test"}],
            current_plan_step=1,  # Past all steps
            is_final=True,
        )
        assert route_after_step_orchestrate(state) == "finalize"

    def test_no_steps_routes_to_finalize(self):
        from core.graph.nodes.step_orchestrate_node import route_after_step_orchestrate

        state = HelixGraphState(
            plan_steps=[],
            current_plan_step=0,
            is_final=False,
        )
        assert route_after_step_orchestrate(state) == "finalize"


# ─── Enriched Plan Node ──────────────────────────────────────────────────────

class TestPlanNodeParsing:
    """Tests for _parse_detailed_plan and _extract_plan_data."""

    def test_parse_detailed_plan(self):
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        json_text = '''{
            "analysis": {
                "task_summary": "Build a REST API",
                "complexity": "complex",
                "clarifying_questions": ["Which framework?"],
                "constraints": ["Must use Python"]
            },
            "architecture": {
                "approach": "FastAPI backend with PostgreSQL",
                "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
                "structure": "api/ models/ tests/",
                "risks": [{"risk": "DB migration issues", "mitigation": "Use Alembic"}]
            },
            "plan": [
                {
                    "step": 1,
                    "description": "Set up project structure",
                    "tools_needed": ["terminal"],
                    "expected_output": "Project directory created",
                    "success_criteria": "Directory exists",
                    "depends_on": [],
                    "parallel_group": null,
                    "subagent_type": null
                }
            ],
            "reasoning": "Standard project setup"
        }'''

        plan, analysis, architecture = _parse_detailed_plan(json_text)
        assert len(plan) == 1
        assert plan[0]["description"] == "Set up project structure"
        assert plan[0]["success_criteria"] == "Directory exists"
        assert analysis is not None
        assert analysis["complexity"] == "complex"
        assert architecture is not None
        assert "FastAPI" in architecture["tech_stack"]
        assert len(architecture["risks"]) == 1

    def test_parse_fallback_on_error(self):
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        # Invalid JSON returns empty
        plan, analysis, architecture = _parse_detailed_plan("not json at all")
        assert plan == []
        assert analysis is None
        assert architecture is None

    def test_parse_with_markdown_wrapping(self):
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        json_text = '```json\n{"plan": [{"step": 1, "description": "test", "tools_needed": [], "expected_output": "done", "success_criteria": "ok", "depends_on": [], "parallel_group": null, "subagent_type": null}], "reasoning": "test"}\n```'
        plan, analysis, architecture = _parse_detailed_plan(json_text)
        assert len(plan) == 1
        assert plan[0]["description"] == "test"


# ─── New State Fields ─────────────────────────────────────────────────────────

class TestNewStateFields:
    """Tests for new plan orchestration state fields."""

    def test_step_orchestrate_fields(self):
        state = HelixGraphState(
            is_step_complete=True,
            current_step_start_count=5,
        )
        assert state.get("is_step_complete") is True
        assert state.get("current_step_start_count") == 5

    def test_enriched_plan_fields(self):
        state = HelixGraphState(
            plan_analysis={"task_summary": "test", "complexity": "medium"},
            plan_architecture={"approach": "direct"},
        )
        assert state.get("plan_analysis") == {"task_summary": "test", "complexity": "medium"}
        assert state.get("plan_architecture") == {"approach": "direct"}


# ─── Config ────────────────────────────────────────────────────────────────────

class TestMaxStepsPerPlanStep:
    """Test max_steps_per_plan_step config."""

    def test_default_value(self):
        from config import Settings
        s = Settings()
        assert s.max_steps_per_plan_step == 5


class TestPlanGenerationConfig:
    """Test plan generation timeout and retry config."""

    def test_plan_generation_timeout_default(self):
        from config import Settings
        s = Settings()
        assert s.plan_generation_timeout == 300.0

    def test_plan_generation_retries_default(self):
        from config import Settings
        s = Settings()
        assert s.plan_generation_retries == 2


# ─── Plan Node Retry & Timeout Logic ──────────────────────────────────────────

class TestPlanNodeRetryLogic:
    """Tests for plan_node timeout and retry behavior (unit tests without LLM)."""

    @pytest.mark.asyncio
    async def test_plan_node_no_agent_fallback(self):
        """When no agent is available, create a single-step fallback plan."""
        from core.graph.nodes.plan_node import plan_node

        state = HelixGraphState(user_input="test task", conversation_id="test")
        config = {"configurable": {"_agent": None}}

        result = await plan_node(state, config)
        assert len(result["plan_steps"]) == 1
        assert result["plan_status"] == "pending_review"
        assert result["plan_steps"][0]["description"] == "test task"

    @pytest.mark.asyncio
    async def test_plan_node_with_mock_llm(self):
        """Plan node calls LLM and parses the response."""
        import json as _json
        from core.graph.nodes.plan_node import plan_node
        from unittest.mock import AsyncMock, MagicMock

        # Create a mock agent
        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = _json.dumps({
            "analysis": {"task_summary": "Test task", "complexity": "simple",
                         "clarifying_questions": ["What tech?"], "constraints": []},
            "architecture": {"approach": "Direct", "tech_stack": ["Python"],
                             "structure": "single file", "risks": []},
            "plan": [
                {"step": 1, "description": "Do the thing", "tools_needed": ["terminal"],
                 "expected_output": "done", "success_criteria": "ok",
                 "depends_on": [], "parallel_group": None, "subagent_type": None},
            ],
        })
        mock_agent.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_agent.model = "test-model"
        mock_agent.emit = MagicMock()
        mock_agent.memory = MagicMock()
        mock_agent.tools = MagicMock()
        mock_agent.tools.list_tools = MagicMock(return_value=[])
        mock_agent._runtime_config = {"max_steps": 15}

        state = HelixGraphState(
            user_input="Do the thing",
            conversation_id="test",
        )
        config = {"configurable": {"_agent": mock_agent}}

        result = await plan_node(state, config)
        assert len(result["plan_steps"]) == 1
        assert result["plan_analysis"]["complexity"] == "simple"
        assert len(result["plan_analysis"]["clarifying_questions"]) == 1


# ─── Enhanced Plan Parsing ────────────────────────────────────────────────────

class TestEnhancedPlanParsing:
    """Tests for improved _parse_detailed_plan with multiple strategies."""

    def test_parse_embedded_json_in_text(self):
        """JSON surrounded by explanatory text should be extracted."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        text = 'Here is my plan:\n{"analysis": {"task_summary": "Build API", "complexity": "medium"}, "plan": [{"step": 1, "description": "Create app", "tools_needed": ["terminal"], "expected_output": "done", "success_criteria": "ok"}]}\nLet me know if this works.'
        plan, analysis, arch = _parse_detailed_plan(text)
        assert len(plan) == 1
        assert plan[0]["description"] == "Create app"
        assert analysis is not None
        assert analysis["complexity"] == "medium"

    def test_parse_trailing_commas(self):
        """JSON with trailing commas (common LLM error) should be fixed."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        text = '{"plan": [{"step": 1, "description": "test", "tools_needed": ["terminal",], "expected_output": "done", "success_criteria": "ok",},], "analysis": {"task_summary": "test", "complexity": "simple",}}'
        plan, analysis, arch = _parse_detailed_plan(text)
        assert len(plan) == 1

    def test_parse_numbered_text_list(self):
        """Plain text with numbered items should become plan steps."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        text = "1. Create project structure\n2. Set up database\n3. Implement API\n4. Write tests\n5. Deploy"
        plan, analysis, arch = _parse_detailed_plan(text)
        assert len(plan) == 5
        assert plan[0]["step"] == 1
        assert "project" in plan[0]["description"].lower()
        assert analysis is not None
        assert analysis["complexity"] == "medium"

    def test_parse_step_pattern(self):
        """Step N: pattern should be recognized."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        text = "Step 1: Initialize the project\nStep 2: Add routes\nStep 3: Test"
        plan, analysis, arch = _parse_detailed_plan(text)
        assert len(plan) == 3
        assert "Initialize" in plan[0]["description"]

    def test_parse_bullet_list(self):
        """Bulleted list should become plan steps."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        text = "- Create project\n- Set up database\n- Build API"
        plan, analysis, arch = _parse_detailed_plan(text)
        assert len(plan) == 3

    def test_parse_empty_returns_empty(self):
        """Empty input returns empty results."""
        from core.plan_review.parser import parse_detailed_plan as _parse_detailed_plan

        plan, analysis, arch = _parse_detailed_plan("")
        assert plan == []
        assert analysis is None

    def test_infer_tools_from_text(self):
        """Tool inference from step descriptions."""
        from core.plan_review.parser import infer_tools_from_text as _infer_tools_from_text

        assert "terminal" in _infer_tools_from_text("Run the build command")
        assert "write_file" in _infer_tools_from_text("Create a new file")
        assert "database" in _infer_tools_from_text("Query the database")
        assert "web_search" in _infer_tools_from_text("Search the web")
        assert "read_file" in _infer_tools_from_text("Read the config file")
        assert _infer_tools_from_text("Think about the problem") == []


# ─── Per-Step Limit Enforcement ────────────────────────────────────────────────

class TestPerStepLimitEnforcement:
    """Tests for max_steps_per_plan_step enforcement in route_after_react_plan."""

    def test_step_limit_forces_advance(self):
        """When a single step exceeds max_steps_per_plan_step, force advance."""
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=False,
            is_final=False,
            step_count=8,
            max_steps=15,
            max_steps_per_plan_step=5,
            plan_steps=[
                {"step": 1, "description": "Step 1"},
                {"step": 2, "description": "Step 2"},
            ],
            current_plan_step=0,
            current_step_start_count=3,  # 8 - 3 = 5 steps in current step → exceeds limit of 5
        )
        # With default max_steps_per_plan_step=5, steps_in_current = 5 → should advance
        result = route_after_react_plan(state)
        assert result == "step_orchestrate"

    def test_step_limit_not_yet_reached(self):
        """When within per-step limit, continue react loop."""
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=False,
            is_final=False,
            step_count=3,
            max_steps=15,
            plan_steps=[
                {"step": 1, "description": "Step 1"},
            ],
            current_plan_step=0,
            current_step_start_count=0,  # 3 - 0 = 3 steps → under limit of 5
        )
        result = route_after_react_plan(state)
        assert result == "react"

    def test_no_plan_uses_global_limit(self):
        """Without plan steps, use global max_steps for finalize."""
        from core.graph.nodes.step_orchestrate_node import route_after_react_plan

        state = HelixGraphState(
            tool_calls=[],
            is_step_complete=False,
            is_final=False,
            step_count=15,
            max_steps=15,
            plan_steps=[],
            current_plan_step=0,
            current_step_start_count=0,
        )
        result = route_after_react_plan(state)
        assert result == "finalize"