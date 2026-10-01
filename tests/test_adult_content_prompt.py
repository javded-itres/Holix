"""Adult content is opt-in per profile and never covers minors."""

from core.prompt_builder import build_system_prompt


def _prompt(**kwargs) -> str:
    return build_system_prompt(
        tools_description="tools",
        active_skills=[],
        profile_name="default",
        **kwargs,
    )


def test_adult_content_off_by_default() -> None:
    text = _prompt()
    assert "Adult content" not in text
    assert "generate_image" not in text


def test_adult_content_flag_allows_adults_and_blocks_minors() -> None:
    text = _prompt(allow_adult_content=True)
    assert "generate_image" in text
    assert "17 or under" in text
    assert "forbidden" in text
