"""``holix`` with no subcommand opens the terminal UI."""

from cli.main import app
from typer.testing import CliRunner


def test_bare_holix_launches_tui(monkeypatch) -> None:
    called: dict[str, str] = {}

    def _fake_run_tui(profile: str = "default") -> None:
        called["profile"] = profile

    monkeypatch.setattr("cli.tui.app.run_tui", _fake_run_tui)
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0
    assert called["profile"] == "default"


def test_holix_tui_still_launches_tui(monkeypatch) -> None:
    called: dict[str, str] = {}

    def _fake_run_tui(profile: str = "default") -> None:
        called["profile"] = profile

    monkeypatch.setattr("cli.tui.app.run_tui", _fake_run_tui)
    result = CliRunner().invoke(app, ["tui", "-p", "default"])
    assert result.exit_code == 0
    assert called["profile"] == "default"
