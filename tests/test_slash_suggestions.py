"""Slash command fuzzy matching."""

from cli.tui.shared.slash_suggestions import fuzzy_score, match_slash_commands


def test_fuzzy_score_substring() -> None:
    assert fuzzy_score("help", "help") > fuzzy_score("help", "metrics")


def test_match_slash_commands_empty_shows_many() -> None:
    matches = match_slash_commands("/", limit=30)
    assert len(matches) >= 10


def test_match_slash_commands_filters_by_prefix() -> None:
    matches = match_slash_commands("/mem")
    cmds = [c for c, _ in matches]
    assert cmds[0] == "/memory"
    assert "/memory-clear" in cmds
    assert not any(c == "/help" for c in cmds)


def test_match_slash_commands_non_slash() -> None:
    assert match_slash_commands("hello") == []