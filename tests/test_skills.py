
import pytest


@pytest.mark.asyncio
async def test_save_and_load_skill(skills_manager):
    """Test saving and loading skills."""
    # Save a skill
    filepath = skills_manager.save_skill(
        name="test_skill",
        description="A test skill",
        content="This is a test skill for testing purposes.",
        tags=["test", "example"],
        examples=["Example 1", "Example 2"]
    )

    assert filepath.exists()

    # Load skills
    skills_manager.load_all_skills()

    assert "test-skill" in skills_manager.all_skills
    skill = skills_manager.all_skills["test-skill"]

    assert skill["description"] == "A test skill"
    assert "test" in skill["tags"]


def test_skill_search(skills_manager):
    """Test semantic skill search."""
    # Create some skills
    skills_manager.save_skill(
        name="fastapi_skill",
        description="Create FastAPI endpoints",
        content="Guide for creating FastAPI endpoints",
        tags=["fastapi", "web", "api"]
    )

    skills_manager.save_skill(
        name="python_skill",
        description="Python programming tips",
        content="General Python programming advice",
        tags=["python", "programming"]
    )

    # Search for relevant skills
    results = skills_manager.get_relevant_skills("How to create an API with FastAPI?", top_k=3)

    # Should find the FastAPI skill
    assert len(results) > 0
