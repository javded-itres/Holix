"""Custom sub-agent type generation from a brief description."""

from __future__ import annotations

from core.subagents.from_description import (
    build_custom_type_from_brief,
    expand_system_prompt,
    normalize_model_slot,
    slug_from_brief,
    unique_type_name,
)
from core.subagents.registry import builtin_subagent_names


def test_build_from_python_dishka_brief():
    brief = (
        "Ты агент python сеньер разработчик который разрабатывает "
        "с использованием паттерна DI и библиотеки Dishka"
    )
    custom = build_custom_type_from_brief(brief, existing_names=builtin_subagent_names())
    assert custom.name.startswith("coder-")
    assert "python" in custom.name or "dishka" in custom.name
    assert "dishka" in custom.system_prompt.lower() or "DI" in custom.system_prompt
    assert "write_file" in custom.tools
    assert custom.description
    # Must expand into structured prompt — not only paste the brief
    assert "Операционные правила" in custom.system_prompt or "Operating rules" in custom.system_prompt
    assert custom.system_prompt.strip() != brief.strip()
    assert not custom.system_prompt.startswith(brief[:40])


def test_slug_follows_type_prefix():
    assert slug_from_brief("Senior Python FastAPI engineer").startswith("coder-")
    assert "python" in slug_from_brief("Senior Python FastAPI engineer")
    assert slug_from_brief("Security code review specialist").startswith("reviewer-")
    assert slug_from_brief("Research market and competitors").startswith("researcher-")
    assert slug_from_brief("Technical writer for API docs").startswith("writer-")


def test_expand_rewrites_english_brief():
    brief = "You are a senior FastAPI engineer using pydantic v2"
    prompt = expand_system_prompt(brief)
    assert "Role" in prompt or "specialized" in prompt.lower()
    assert "FastAPI" in prompt or "fastapi" in prompt.lower()
    assert "Operating rules" in prompt
    assert prompt.strip() != brief.strip()


def test_slug_avoids_builtin_collision():
    name = unique_type_name("coder", builtin_subagent_names())
    assert name != "coder"
    assert name not in builtin_subagent_names()


def test_preferred_name():
    custom = build_custom_type_from_brief(
        "Senior API engineer for FastAPI services",
        name="api-senior",
        existing_names=[],
    )
    assert custom.name == "api-senior"


def test_model_slot_default_empty():
    custom = build_custom_type_from_brief(
        "Senior API engineer for FastAPI services",
        existing_names=[],
    )
    assert custom.model_slot == ""
    custom2 = build_custom_type_from_brief(
        "Senior API engineer for FastAPI services",
        name="api2",
        existing_names=["api-senior"],
        model_slot="main",
    )
    assert custom2.model_slot == ""
    custom3 = build_custom_type_from_brief(
        "Senior API engineer for FastAPI services",
        name="api3",
        existing_names=["api-senior", "api2"],
        model_slot="coder",
    )
    assert custom3.model_slot == "coder"


def test_normalize_model_slot():
    assert normalize_model_slot(None) == ""
    assert normalize_model_slot("main") == ""
    assert normalize_model_slot(" inherit ") == ""
    assert normalize_model_slot("coder") == "coder"


def test_too_short_raises():
    import pytest

    with pytest.raises(ValueError, match="short"):
        build_custom_type_from_brief("hi")
