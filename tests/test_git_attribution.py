"""Agent commits carry a Holix co-author trailer."""

from __future__ import annotations

from core.git.attribution import COMMIT_TRAILER, attribute_agent_commit


def test_commit_message_gains_a_coauthor_trailer() -> None:
    command = attribute_agent_commit('git commit -m "fix the parser"')
    assert command.endswith(f" -m '{COMMIT_TRAILER}'")
    assert "Holix agent" in command


def test_trailer_is_not_added_twice() -> None:
    once = attribute_agent_commit('git commit -m "fix the parser"')
    assert attribute_agent_commit(once) == once


def test_trailer_stays_on_the_commit_before_push() -> None:
    command = attribute_agent_commit('git commit -m "fix the parser" && git push origin main')
    commit, _, push = command.partition("&&")
    assert COMMIT_TRAILER in commit
    assert "git push origin main" in push
    assert COMMIT_TRAILER not in push


def test_status_and_commit_without_a_message_are_unchanged() -> None:
    assert attribute_agent_commit("git status") == "git status"
    assert attribute_agent_commit("git commit") == "git commit"


def test_git_dash_c_commit_is_attributed() -> None:
    command = attribute_agent_commit('git -C /tmp/repo commit -m "save"')
    assert COMMIT_TRAILER in command
