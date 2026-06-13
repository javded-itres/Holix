"""Slash command token parsing (/mode vs /models)."""

from cli.shared.slash_input import is_mode_slash, is_models_slash, slash_command_token


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