"""Slash autocomplete: skills only under /skill, not in general / menu."""

from __future__ import annotations

from cli.tui.shared.slash_suggestions import (
    is_skill_invoke_line,
    match_skill_invoke_commands,
    match_slash_commands,
)


def _static_pool() -> list[tuple[str, str]]:
    from cli.shared.commands.registry import slash_commands_for_locale

    return slash_commands_for_locale("en")


def _skill_pool() -> list[tuple[str, str]]:
    return [
        ("/skill pptx", "Presentation skill"),
        ("/skill docx", "Word document skill"),
        ("/skill xlsx", "Spreadsheet skill"),
    ]


class TestSkillInvokeSlash:
    def test_static_pool_has_skill_not_individual_skills(self):
        cmds = [c for c, _ in _static_pool()]
        assert "/skill" in cmds
        assert "/pptx" not in cmds

    def test_general_slash_uses_static_pool_only(self):
        pool = _static_pool() + [("/pptx", "should not appear")]
        matches = match_slash_commands("/", pool)
        cmds = [c for c, _ in matches]
        assert "/pptx" not in cmds

    def test_skill_prefix_shows_command_not_skill_names(self):
        pool = _static_pool() + [("/pptx", "should not appear")]
        matches = match_slash_commands("/sk", pool)
        cmds = [c for c, _ in matches]
        assert "/skill" in cmds
        assert "/skills" in cmds
        assert "/pptx" not in cmds

    def test_skill_invoke_line_detection(self):
        assert is_skill_invoke_line("/skill")
        assert is_skill_invoke_line("/skill pptx")
        assert not is_skill_invoke_line("/skills")
        assert not is_skill_invoke_line("/help")

    def test_skill_autocomplete_empty_query(self):
        matches = match_skill_invoke_commands("/skill", _skill_pool())
        assert len(matches) == 3
        assert matches[0][0].startswith("/skill ")

    def test_skill_autocomplete_prefix(self):
        matches = match_skill_invoke_commands("/skill pp", _skill_pool())
        assert len(matches) == 1
        assert matches[0][0] == "/skill pptx"