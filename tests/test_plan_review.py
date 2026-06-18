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
import tempfile
from pathlib import Path

import pytest
from core.agent_events import (
    AgentEventBus,
    EventType,
    PlanCompletedEvent,
    PlanGeneratedEvent,
    PlanStepCompletedEvent,
)
from core.plan_review.plan_storage import (
    PLAN_DIR,
    InvalidPlanIdError,
    _format_plan_markdown,
    list_plans,
    load_plan,
    resolve_plan_path,
    save_plan,
)
from core.plan_review.review_events import (
    PlanReviewEventType,
    PlanReviewRequestEvent,
    PlanReviewResponseEvent,
)
from core.plan_review.review_guard import (
    PlanReviewChoice,
    PlanReviewGuard,
    get_plan_review_guard,
    init_plan_review_guard,
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

        md_path = save_plan(
            plan_steps,
            conversation_id="test_conv",
            metadata={"mode": "auto_execute"},
            plan_report={"title": "Dev plan", "summary": {"goal": "Build API"}},
            user_input="Build API",
            plan_id="plan_test123",
        )
        assert md_path.exists()
        assert md_path.suffix == ".md"
        assert "plans" in str(PLAN_DIR) or md_path.parent == Path(self._tmpdir)

        data = load_plan(str(md_path))
        assert data["conversation_id"] == "test_conv"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["description"] == "Create project"
        assert data["plan_id"] == "plan_test123"
        assert data["plan_report"]["title"] == "Dev plan"

    def test_plans_dir_under_holix(self):
        from core.config_utils import get_local_holix_dir, get_local_plan_dir

        plan_dir = get_local_plan_dir()
        assert plan_dir.name == "plans"
        assert plan_dir.parent == get_local_holix_dir()

    def test_load_latest_plan(self):
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir)

        save_plan([{"step": 1, "description": "older"}], conversation_id="conv1")
        save_plan([{"step": 1, "description": "newer"}], conversation_id="conv2")

        latest = ps.load_latest_plan()
        assert latest is not None
        assert latest["steps"][0]["description"] == "newer"

    def test_format_saved_plans_context(self):
        import core.plan_review.plan_storage as ps
        ps._TEST_PLAN_DIR = Path(self._tmpdir)

        save_plan(
            [{"step": 1, "description": "Do thing"}],
            conversation_id="conv1",
            plan_report={"title": "RAG service plan"},
        )
        context = ps.format_saved_plans_context()
        assert "RAG service plan" in context
        assert "plans" in context

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

    def test_load_plan_rejects_path_outside_plan_dir(self):
        import core.plan_review.plan_storage as ps

        ps._TEST_PLAN_DIR = Path(self._tmpdir)
        outside = Path(self._tmpdir).parent / "outside_plan.json"
        outside.write_text("{}", encoding="utf-8")
        with pytest.raises(InvalidPlanIdError):
            load_plan(str(outside))


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
    """Tests for the new plan_review fields in HolixGraphState."""

    def test_state_has_plan_review_fields(self):
        from core.graph.state import HolixGraphState
        state = HolixGraphState(
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
        assert "Execution Plan" in md
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

    def test_russian_locale_labels(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[{"step": 1, "description": "Создать API"}],
            step_count=1,
            locale="ru",
        )
        assert "План выполнения" in md
        assert "Шаг 1" in md
        assert "Создать API" in md

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

    def test_development_report_markdown_russian(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[
                {
                    "step": 1,
                    "description": "Инициализировать проект",
                    "tools_needed": ["terminal"],
                    "expected_output": "Структура создана",
                    "success_criteria": "Проект запускается",
                }
            ],
            step_count=1,
            user_input="Сервис RAG",
            plan_report={
                "title": "План разработки: Сервис RAG (rag-agent)",
                "summary": {
                    "goal": "Разработать микросервис rag-agent",
                    "key_decisions": ["FastAPI + Celery + Redis"],
                    "critical_risks": ["SQLite database is locked"],
                },
                "development_stages": [
                    {
                        "stage": 0,
                        "title": "Подготовка инфраструктуры",
                        "items": ["docker-compose.yml", "pyproject.toml"],
                        "duration_hours": "4-6",
                    }
                ],
                "priorities": {
                    "mvp": ["Этап 0: инфраструктура"],
                    "important_later": ["Alias swap"],
                    "optional": ["Prometheus метрики"],
                },
                "dependencies": [
                    {"task": "Этап 0", "depends_on": "—", "unblocks": "Все остальные этапы"}
                ],
                "blockers": [
                    {
                        "risk": "SQLite + Celery",
                        "probability": "Высокая",
                        "impact": "Высокое",
                        "mitigation": "Redis result backend",
                    }
                ],
                "manual_actions": [
                    {"action": "Проверить TEI", "when": "Перед этапом 5", "who": "DevOps"}
                ],
                "estimates": {
                    "stages": [{"stage": 0, "title": "Инфраструктура", "hours": 5, "story_points": 5}],
                    "total_hours": 78,
                    "total_story_points": 78,
                    "calendar_time": "2-2.5 недели",
                    "buffer_note": "+20%",
                },
                "stack": {
                    "technologies": [{"component": "Фреймворк", "choice": "FastAPI"}],
                    "patterns": ["API Gateway + Async Task Queue"],
                    "critical_fixes": ["SQLite → Celery result backend"],
                },
            },
            locale="ru",
        )
        assert "План разработки: Сервис RAG (rag-agent)" in md
        assert "1. Общее резюме" in md
        assert "Цель:" in md
        assert "2. Этапы разработки" in md
        assert "Этап 0" in md
        assert "3. Приоритеты" in md
        assert "4. Зависимости между задачами" in md
        assert "5. Блокеры и риски" in md
        assert "6. Ручные действия" in md
        assert "7. Оценка стоимости/времени" in md
        assert "8. Рекомендуемый стек и архитектура" in md
        assert "Шаги выполнения" in md
        assert "Инициализировать проект" in md
        assert "да** для запуска разработки" in md

    def test_truncated_json_detection(self):
        from core.plan_review.parser import is_truncated_json

        assert is_truncated_json('{"plan": [{"step": 1') is True
        assert is_truncated_json('{"plan": [{"step": 1}]}') is False

    def test_development_report_completeness(self):
        from core.plan_review.parser import is_development_report_complete

        assert is_development_report_complete(None) is False
        assert is_development_report_complete({
            "summary": {"goal": "Build API"},
            "development_stages": [{"stage": 0, "title": "Setup"}],
            "priorities": {"mvp": ["Stage 0"]},
            "dependencies": [{"task": "Stage 0", "depends_on": "—", "unblocks": "All"}],
            "blockers": [{"risk": "X", "mitigation": "Y"}],
            "estimates": {"stages": [{"stage": 0, "hours": 5}]},
        }) is True

    def test_development_report_markdown_english(self):
        from core.plan_review.markdown_builder import build_plan_markdown

        md = build_plan_markdown(
            plan_steps=[{"step": 1, "description": "Bootstrap"}],
            step_count=1,
            plan_report={
                "title": "Development Plan: API",
                "summary": {"goal": "Build API", "key_decisions": ["FastAPI"], "critical_risks": []},
                "development_stages": [],
                "priorities": {"mvp": [], "important_later": [], "optional": []},
                "dependencies": [],
                "blockers": [],
                "manual_actions": [],
                "estimates": {"stages": [], "total_hours": 10, "total_story_points": 10},
                "stack": {"technologies": [], "patterns": [], "critical_fixes": []},
            },
            locale="en",
        )
        assert "Development Plan: API" in md
        assert "1. Executive Summary" in md
        assert "Execution Steps" in md