"""
Tests for the Plan Review system.

Covers:
- PlanReviewGuard: request_review, resolve_review, timeout, non-interactive mode
- PlanReviewChoice enum
- plan_storage: save_plan, load_plan, list_plans
- Plan review events
- Graph state plan_review fields
- Config settings
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.agent_events import (
    AgentEventBus,
    EventType,
    PlanGeneratedEvent,
    PlanStepCompletedEvent,
    PlanCompletedEvent,
)
from core.plan_review.review_guard import (
    PlanReviewChoice,
    PlanReviewGuard,
    init_plan_review_guard,
    get_plan_review_guard,
)
from core.plan_review.review_events import (
    PlanReviewEventType,
    PlanReviewRequestEvent,
    PlanReviewResponseEvent,
)
from core.plan_review.plan_storage import (
    InvalidPlanIdError,
    save_plan,
    load_plan,
    list_plans,
    PLAN_DIR,
    resolve_plan_path,
    _format_plan_markdown,
)


# ─── PlanReviewChoice ──────────────────────────────────────────────────────

class TestPlanReviewChoice:
    """Tests for the PlanReviewChoice enum."""

    def test_choice_values(self):
        assert PlanReviewChoice.CONFIRM_STEP.value == "confirm_step"
        assert PlanReviewChoice.AUTO_EXECUTE.value == "auto_execute"
        assert PlanReviewChoice.REFINE.value == "refine"
        assert PlanReviewChoice.REJECT.value == "reject"

    def test_choice_from_string(self):
        assert PlanReviewChoice("confirm_step") == PlanReviewChoice.CONFIRM_STEP
        assert PlanReviewChoice("auto_execute") == PlanReviewChoice.AUTO_EXECUTE
        assert PlanReviewChoice("refine") == PlanReviewChoice.REFINE
        assert PlanReviewChoice("reject") == PlanReviewChoice.REJECT


# ─── PlanReviewGuard ────────────────────────────────────────────────────────

class TestPlanReviewGuard:
    """Tests for the PlanReviewGuard."""

    def setup_method(self):
        """Reset global guard before each test."""
        import core.plan_review.review_guard as mod
        mod._plan_review_guard = None

    @pytest.mark.asyncio
    async def test_non_interactive_returns_auto_execute(self):
        """Non-interactive guard immediately returns AUTO_EXECUTE."""
        guard = PlanReviewGuard(interactive=False)
        choice, feedback = await guard.request_review(
            [{"step": 1, "description": "test"}]
        )
        assert choice == PlanReviewChoice.AUTO_EXECUTE
        assert feedback == ""

    @pytest.mark.asyncio
    async def test_request_and_resolve_review(self):
        """Full flow: request review → resolve from outside → get result."""
        guard = PlanReviewGuard(interactive=True, review_timeout=5)

        async def resolve_after_delay():
            await asyncio.sleep(0.1)
            review_id = list(guard._pending_reviews.keys())[-1]
            guard.resolve_review(review_id, PlanReviewChoice.CONFIRM_STEP)

        asyncio.create_task(resolve_after_delay())
        choice, feedback = await guard.request_review(
            [{"step": 1, "description": "test"}],
            conversation_id="test",
        )
        assert choice == PlanReviewChoice.CONFIRM_STEP
        assert feedback == ""

    @pytest.mark.asyncio
    async def test_resolve_with_feedback(self):
        """Resolve with refinement feedback."""
        guard = PlanReviewGuard(interactive=True, review_timeout=5)

        async def resolve_after_delay():
            await asyncio.sleep(0.1)
            review_id = list(guard._pending_reviews.keys())[-1]
            guard.resolve_review(review_id, PlanReviewChoice.REFINE, "Add more steps")

        asyncio.create_task(resolve_after_delay())
        choice, feedback = await guard.request_review(
            [{"step": 1, "description": "test"}],
            conversation_id="test",
        )
        assert choice == PlanReviewChoice.REFINE
        assert feedback == "Add more steps"

    def test_resolve_nonexistent_review(self):
        """Resolving a non-existent review returns False."""
        guard = PlanReviewGuard(interactive=True)
        result = guard.resolve_review("nonexistent_id", PlanReviewChoice.AUTO_EXECUTE)
        assert result is False

    @pytest.mark.asyncio
    async def test_event_bus_emits_request(self):
        """When event bus is set, request_review emits PlanReviewRequestEvent."""
        bus = AgentEventBus(name="test")
        received_events = []
        bus.subscribe(lambda e: received_events.append(e))

        guard = PlanReviewGuard(event_bus=bus, interactive=True, review_timeout=5)

        async def resolve_after_delay():
            await asyncio.sleep(0.1)
            review_id = list(guard._pending_reviews.keys())[-1]
            guard.resolve_review(review_id, PlanReviewChoice.AUTO_EXECUTE)

        asyncio.create_task(resolve_after_delay())
        await guard.request_review(
            [{"step": 1, "description": "test"}],
            conversation_id="test",
        )

        # Check that a PlanReviewRequestEvent was emitted
        assert len(received_events) >= 1
        event = received_events[0]
        assert isinstance(event, PlanReviewRequestEvent)
        assert event.step_count == 1

    def test_init_and_get_guard(self):
        """init_plan_review_guard sets the global instance."""
        bus = AgentEventBus(name="test")
        guard = init_plan_review_guard(bus, interactive=True, review_timeout=300)
        assert guard is not None
        assert guard._event_bus is bus

        retrieved = get_plan_review_guard()
        assert retrieved is guard


# ─── Plan Storage ───────────────────────────────────────────────────────────

class TestPlanStorage:
    """Tests for plan storage functions."""

    def setup_method(self):
        """Use a temp directory for plan files."""
        self._tmpdir = tempfile.mkdtemp()
        self._original_plan_dir = PLAN_DIR
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        import core.plan_review.plan_storage as ps
        ps.PLAN_DIR = self._original_plan_dir
        ps._TEST_PLAN_DIR = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load_plan(self):
        """Save a plan and load it back."""
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir)

        plan_steps = [
            {"step": 1, "description": "Create project", "tools_needed": ["terminal"], "expected_output": "Project created"},
            {"step": 2, "description": "Add tests", "tools_needed": ["write_file"], "expected_output": "Tests passing"},
        ]

        md_path = save_plan(plan_steps, conversation_id="test_conv", metadata={"mode": "auto_execute"})
        assert md_path.exists()
        assert md_path.suffix == ".md"

        # Load the JSON version
        data = load_plan(str(md_path))
        assert data["conversation_id"] == "test_conv"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["description"] == "Create project"

    def test_list_plans_empty(self):
        """list_plans returns empty when no plans exist."""
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir) / "nonexistent"
        plans = list_plans()
        assert plans == []

    def test_list_plans_with_data(self):
        """list_plans returns saved plans."""
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir)

        save_plan([{"step": 1, "description": "test"}], conversation_id="conv1")
        save_plan([{"step": 1, "description": "test2"}], conversation_id="conv2")

        plans = list_plans()
        assert len(plans) == 2

    def test_format_plan_markdown(self):
        """Markdown format includes step details."""
        steps = [
            {"step": 1, "description": "Setup", "tools_needed": ["terminal"], "expected_output": "Done"},
        ]
        md = _format_plan_markdown(steps, "test", {"mode": "auto"}, "confirmed")
        assert "Step 1: Setup" in md
        assert "terminal" in md
        assert "Done" in md

    def test_resolve_plan_path_accepts_valid_filename(self):
        plan_dir = Path(self._tmpdir)
        resolved = resolve_plan_path(plan_dir, "20260607_120000_default.json")
        assert resolved == (plan_dir / "20260607_120000_default.json").resolve()

    def test_resolve_plan_path_rejects_traversal(self):
        plan_dir = Path(self._tmpdir)
        with pytest.raises(InvalidPlanIdError):
            resolve_plan_path(plan_dir, "../secret.json")

    def test_resolve_plan_path_rejects_absolute_path(self):
        plan_dir = Path(self._tmpdir)
        with pytest.raises(InvalidPlanIdError):
            resolve_plan_path(plan_dir, "/etc/passwd.json")


# ─── Plan Review Events ─────────────────────────────────────────────────────

class TestPlanReviewEvents:
    """Tests for PlanReviewRequestEvent and PlanReviewResponseEvent."""

    def test_request_event_fields(self):
        event = PlanReviewRequestEvent(
            review_id="test_1",
            plan_steps=[{"step": 1}],
            step_count=1,
            reasoning="test reasoning",
            conversation_id="conv",
        )
        assert event.review_id == "test_1"
        assert event.step_count == 1
        assert event.reasoning == "test reasoning"

        d = event.to_dict()
        assert d["type"] == PlanReviewEventType.PLAN_REVIEW_REQUEST
        assert d["review_id"] == "test_1"

    def test_response_event_fields(self):
        event = PlanReviewResponseEvent(
            review_id="test_1",
            choice="confirm_step",
            feedback="",
            conversation_id="conv",
        )
        assert event.choice == "confirm_step"

        d = event.to_dict()
        assert d["type"] == PlanReviewEventType.PLAN_REVIEW_RESPONSE


# ─── Agent Events ───────────────────────────────────────────────────────────

class TestPlanEvents:
    """Tests for PlanGeneratedEvent, PlanStepCompletedEvent, PlanCompletedEvent."""

    def test_plan_generated_event(self):
        event = PlanGeneratedEvent(
            plan_steps=[{"step": 1}],
            step_count=1,
            conversation_id="test",
        )
        assert event.type == EventType.PLAN_GENERATED
        assert event.step_count == 1
        d = event._extra_fields()
        assert "plan_steps" in d

    def test_plan_step_completed_event(self):
        event = PlanStepCompletedEvent(
            step_number=1,
            total_steps=3,
            step_description="Do thing",
            conversation_id="test",
        )
        assert event.type == EventType.PLAN_STEP_COMPLETED
        assert event.step_number == 1

    def test_plan_completed_event(self):
        event = PlanCompletedEvent(total_steps=3, conversation_id="test")
        assert event.type == EventType.PLAN_COMPLETED
        assert event.total_steps == 3


# ─── Graph State ────────────────────────────────────────────────────────────

class TestGraphStatePlanReviewFields:
    """Tests for the new plan_review fields in HelixGraphState."""

    def test_state_has_plan_review_fields(self):
        from core.graph.state import HelixGraphState
        state = HelixGraphState(
            plan_status="pending_review",
            plan_review_id="",
            plan_refinement_feedback="",
        )
        assert state.get("plan_status") == "pending_review"
        assert state.get("plan_review_id") == ""
        assert state.get("plan_refinement_feedback") == ""


# ─── Config ─────────────────────────────────────────────────────────────────

class TestConfigPlanReview:
    """Tests for plan review config settings."""

    def test_default_config_values(self):
        from config import Settings
        s = Settings()
        assert s.plan_review_enabled is True
        assert s.plan_review_timeout == 600


# ─── Markdown Builder ────────────────────────────────────────────────────────

class TestBuildPlanMarkdown:
    """Tests for build_plan_markdown function."""

    def test_basic_plan(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[
                {"step": 1, "description": "Create project", "tools_needed": ["terminal"],
                 "expected_output": "Project created", "success_criteria": "Dir exists"},
            ],
            step_count=1,
            user_input="Build a REST API",
        )
        assert "📋 Execution Plan" in md
        assert "Build a REST API" in md
        assert "Step 1: Create project" in md
        assert "`terminal`" in md

    def test_with_analysis_and_architecture(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[{"step": 1, "description": "Do thing"}],
            step_count=1,
            analysis={"task_summary": "Build API", "complexity": "complex",
                       "clarifying_questions": ["Which framework?"], "constraints": ["Python only"]},
            architecture={"approach": "FastAPI", "tech_stack": ["Python", "FastAPI"],
                         "structure": "api/", "risks": [{"risk": "Migration issues", "mitigation": "Use Alembic"}]},
        )
        assert "📊 Analysis" in md
        assert "Complex" in md
        assert "❓ Clarifying Questions" in md
        assert "Which framework?" in md
        assert "🏗️ Architecture" in md
        assert "FastAPI" in md
        assert "⚡ Risks" in md
        assert "Migration issues" in md

    def test_empty_analysis(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[{"step": 1, "description": "Simple task"}],
            step_count=1,
        )
        assert "📊 Analysis" not in md
        assert "Step 1" in md

    def test_rendered_markdown_in_event(self):
        """PlanReviewRequestEvent includes rendered_markdown field."""
        from core.plan_review.review_events import PlanReviewRequestEvent

        event = PlanReviewRequestEvent(
            review_id="test_1",
            plan_steps=[{"step": 1}],
            step_count=1,
            rendered_markdown="# Test Markdown",
        )
        assert event.rendered_markdown == "# Test Markdown"
        d = event.to_dict()
        assert d["rendered_markdown"] == "# Test Markdown"