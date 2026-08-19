from __future__ import annotations

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.skills.dedup import (
    find_duplicate_skill,
    is_transient_failure_lesson,
    is_trivial_session,
    names_are_near_duplicate,
)
from core.skills.manager import SkillsManager, tool_names_from_messages


def test_names_are_near_duplicate() -> None:
    assert names_are_near_duplicate("excel-budget-recalculator", "excel-budget-recalculation")
    assert names_are_near_duplicate("subagent-research-delegation", "sub-agent-research-delegation")
    assert not names_are_near_duplicate("holix-cron", "holix-subagents")


def test_find_duplicate_skill() -> None:
    existing = {
        "fastapi-dishka-catalog-service": {
            "name": "fastapi-dishka-catalog-service",
            "description": "Build FastAPI catalog services with Dishka DI",
        }
    }
    hit = find_duplicate_skill(
        existing,
        name="fastapi-dishka-sqlite-catalog",
        description="FastAPI catalog with Dishka and sqlite",
    )
    assert hit is not None
    assert hit["name"] == "fastapi-dishka-catalog-service"


def test_transient_timeout_is_not_a_skill() -> None:
    assert is_transient_failure_lesson(
        [
            {"role": "tool", "content": "timed out"},
            {"role": "assistant", "content": "avoid using the tool"},
        ],
        "avoid using the tool after timeout",
    )


def test_trivial_session_skipped() -> None:
    assert is_trivial_session(
        [{"role": "user", "content": "привет"}],
        "Привет! Чем помочь?",
    )
    assert is_trivial_session(
        [{"role": "user", "content": "ping"}],
        "pong",
    )
    assert not is_trivial_session(
        [
            {"role": "user", "content": "Собери FastAPI каталог адресов с Dishka и pytest"},
            {"role": "assistant", "content": "ok"},
        ],
        "Создал app/main.py и прогнал тесты.",
    )


def _mgr(tmp_path) -> SkillsManager:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        skills_dir=str(tmp_path / "skills"),
        vector_db_path=str(tmp_path / "vector"),
    )
    return SkillsManager(cfg)


@pytest.mark.asyncio
async def test_should_create_skill_rejects_short_sessions(tmp_path) -> None:
    ok = await _mgr(tmp_path).should_create_skill(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "tool", "content": "x"},
            {"role": "tool", "content": "y"},
        ],
        "done",
    )
    assert ok is False


def test_tool_names_from_subagent_messages() -> None:
    names = tool_names_from_messages(
        [
            {"role": "user", "content": "build"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "1", "function": {"name": "write_file"}},
                    {"id": "2", "function": {"name": "read_file"}},
                ],
            },
            {"role": "tool", "tool_call_id": "1", "content": "ok"},
            {"role": "tool", "tool_call_id": "2", "content": "ok"},
        ]
    )
    assert names == {"write_file", "read_file"}


@pytest.mark.asyncio
async def test_should_create_skill_accepts_subagent_tool_rows(tmp_path) -> None:
    ok = await _mgr(tmp_path).should_create_skill(
        [
            {"role": "user", "content": "Собери FastAPI каталог адресов с Dishka и pytest"},
            {
                "role": "assistant",
                "content": "пишу",
                "tool_calls": [
                    {"id": "1", "function": {"name": "write_file"}},
                    {"id": "2", "function": {"name": "read_file"}},
                    {"id": "3", "function": {"name": "write_file"}},
                    {"id": "4", "function": {"name": "run_terminal_command"}},
                ],
            },
            {"role": "tool", "tool_call_id": "1", "content": "wrote"},
            {"role": "assistant", "content": "дальше"},
            {"role": "tool", "tool_call_id": "2", "content": "ok"},
            {"role": "assistant", "content": "тесты"},
            {"role": "tool", "tool_call_id": "3", "content": "wrote"},
            {"role": "assistant", "content": "прогон"},
            {"role": "tool", "tool_call_id": "4", "content": "pytest 3 passed"},
        ],
        "Готово: CRUD и тесты зелёные.",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_save_skill_reuses_near_duplicate(tmp_path) -> None:
    mgr = _mgr(tmp_path)
    first = mgr.save_skill(
        name="fastapi-dishka-catalog-service",
        description="Build FastAPI catalog services with Dishka DI",
        content="v1",
        tags=["fastapi", "dishka"],
    )
    second = mgr.save_skill(
        name="fastapi-dishka-sqlite-catalog",
        description="FastAPI catalog service with Dishka and sqlite",
        content="v2 should not create a new file",
        tags=["fastapi", "dishka"],
    )
    assert second.resolve() == first.resolve()
    assert not (mgr.skills_dir / "fastapi-dishka-sqlite-catalog.md").exists()
