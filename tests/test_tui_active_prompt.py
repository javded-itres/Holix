"""The top TUI bar shows the prompt the agent is working on."""

from cli.tui.code.widgets.active_prompt import _compact


def test_compact_keeps_short_prompt() -> None:
    assert _compact("  Проверь   что ключ работает ") == "Проверь что ключ работает"


def test_compact_truncates_long_prompt() -> None:
    text = "а" * 400
    shown = _compact(text)
    assert len(shown) == 280
    assert shown.endswith("…")
