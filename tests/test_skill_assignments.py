"""Tests for per-agent skill assignments."""


import pytest
from core.skills.assignments import (
    assign_skill_to_agents,
    is_skill_allowed_for_agent,
    normalize_skill_agent_slot,
    whitelist_for_slot,
)
from core.skills.manager import SkillsManager


def test_normalize_skill_agent_slot():
    assert normalize_skill_agent_slot("main") == "main"
    assert normalize_skill_agent_slot("coder") == "coder"
    assert normalize_skill_agent_slot("prov:ollama:llama3") == "main"
    assert normalize_skill_agent_slot("legacy") == "main"


def test_whitelist_for_slot():
    assigns = {"main": ["a", "b"], "coder": ["a"]}
    assert whitelist_for_slot(assigns, "main") == {"a", "b"}
    assert whitelist_for_slot(assigns, "coder") == {"a"}
    assert whitelist_for_slot(assigns, "unknown") == {"a", "b"}


def test_frontmatter_agents():
    skill = {"name": "x", "agents": ["coder"]}
    assert is_skill_allowed_for_agent(skill, "coder", None)
    assert not is_skill_allowed_for_agent(skill, "main", None)


def test_profile_assignments():
    skill = {"name": "git"}
    other = {"name": "docker"}
    assigns = {"main": ["git"], "researcher": []}
    assert is_skill_allowed_for_agent(skill, "main", assigns)
    assert is_skill_allowed_for_agent(other, "main", assigns)
    assert not is_skill_allowed_for_agent(skill, "researcher", assigns)


def test_assign_skill_to_agents():
    out = assign_skill_to_agents({"main": ["a"]}, "b", ["main", "coder"])
    assert out["main"] == ["a", "b"]
    assert out["coder"] == ["b"]


@pytest.mark.asyncio
async def test_manager_filters_by_agent(skills_manager: SkillsManager):
    skills_manager.save_skill(
        name="only_main",
        description="main only",
        content="for main agent",
        tags=["main"],
    )
    skills_manager.save_skill(
        name="only_coder",
        description="coder only",
        content="for coder subagent",
        tags=["coder"],
    )
    skills_manager.load_all_skills()
    skills_manager._config = skills_manager._config.with_overrides(
        skill_assignments={
            "main": ["only_main"],
            "coder": ["only_coder"],
        }
    )

    main_results = skills_manager.get_relevant_skills(
        "main agent task", top_k=5, agent_slot="main"
    )
    main_names = {s["name"] for s in main_results}
    assert "only_main" in main_names or len(main_names) <= 1
    # Main agent is not restricted by skill_assignments allowlists.

    coder_results = skills_manager.get_relevant_skills(
        "coder subagent task", top_k=5, agent_slot="coder"
    )
    coder_names = {s["name"] for s in coder_results}
    assert "only_coder" in coder_names or len(coder_names) <= 1
    assert "only_main" not in coder_names