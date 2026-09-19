"""Slash command token parsing (/mode vs /models)."""

from cli.shared.slash_input import (
    is_mode_slash,
    is_models_slash,
    is_stop_command,
    slash_command_token,
)


def test_models_not_treated_as_mode() -> None:
    assert slash_command_token("/models") == "/models"
    assert is_models_slash("/models")
    assert not is_mode_slash("/models")
    assert is_mode_slash("/mode")
    assert not is_models_slash("/mode")
    assert is_models_slash("/model")
    assert not is_mode_slash("/model")
    assert is_mode_slash("/mode hybrid")
    assert is_models_slash("/models@MyHolixBot")


def test_stop_command_slash_and_words() -> None:
    assert is_stop_command("/stop")
    assert is_stop_command("/stop@holix_studio_bot")
    assert is_stop_command("стоп")
    assert is_stop_command("Стоп!")
    assert is_stop_command("stop")
    assert is_stop_command("STOP")
    assert not is_stop_command("stop the tests")
    assert not is_stop_command("не стоп")
