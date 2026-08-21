"""Custom markdown slash commands (.holix/commands and ~/.holix/commands)."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.commands.expand import parse_slash_line, resolve_custom_slash
from core.commands.parse import expand_arguments, parse_command_file, split_frontmatter
from core.commands.paths import command_name_from_rel
from core.commands.reserved import RESERVED_SLASH_NAMES


def test_command_name_from_rel() -> None:
    assert command_name_from_rel("review.md") == "review"
    assert command_name_from_rel("test/unit.md") == "test:unit"
    assert command_name_from_rel("git/commit.md") == "git:commit"
    assert command_name_from_rel("README.md") is None
    assert command_name_from_rel("_hidden.md") is None


def test_expand_arguments_placeholders() -> None:
    template = "Review $ARGUMENTS ($1) extra=$2 dollar=$$end"
    out = expand_arguments(template, "src/auth.py --strict")
    assert out == "Review src/auth.py --strict (src/auth.py) extra=--strict dollar=$end"


def test_expand_arguments_missing_positional_is_empty() -> None:
    assert expand_arguments("a=$1 b=$2", "only") == "a=only b="


def test_split_frontmatter() -> None:
    meta, body = split_frontmatter(
        "---\ndescription: Review\nargument-hint: '[file]'\n---\n\nHello $ARGUMENTS\n"
    )
    assert meta["description"] == "Review"
    assert meta["argument-hint"] == "[file]"
    assert "Hello $ARGUMENTS" in body


def test_parse_command_file_tools_and_model(tmp_path: Path) -> None:
    path = tmp_path / "review.md"
    path.write_text(
        "---\n"
        "description: Strict review\n"
        "allowed-tools: [Read, Grep, Bash]\n"
        "model: gpt-test\n"
        "---\n"
        "Check $1\n",
        encoding="utf-8",
    )
    parsed = parse_command_file(path, name="review", source="project")
    assert parsed is not None
    assert parsed.description == "Strict review"
    assert parsed.model == "gpt-test"
    assert "read_file" in parsed.allowed_tools
    assert "run_terminal_command" in parsed.allowed_tools


def test_loader_project_overrides_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_root = tmp_path / "home" / "commands"
    project_root = tmp_path / "repo" / ".holix" / "commands"
    user_root.mkdir(parents=True)
    project_root.mkdir(parents=True)
    (user_root / "review.md").write_text("user body $ARGUMENTS", encoding="utf-8")
    (project_root / "review.md").write_text("project body $ARGUMENTS", encoding="utf-8")
    (user_root / "explain.md").write_text("explain $1", encoding="utf-8")
    nested = project_root / "test"
    nested.mkdir()
    (nested / "unit.md").write_text("unit $ARGUMENTS", encoding="utf-8")

    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path / "repo")

    from core.commands.loader import CommandLoader

    loader = CommandLoader(project_dir=project_root, user_dir=user_root)
    review = loader.get("review")
    assert review is not None
    assert review.source == "project"
    assert review.body.startswith("project body")
    explain = loader.get("explain")
    assert explain is not None
    assert explain.source == "user"
    unit = loader.get("test:unit")
    assert unit is not None
    names = {c.name for c in loader.list_commands()}
    assert names == {"review", "explain", "test:unit"}


def test_resolve_custom_slash_skips_builtins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / ".holix" / "commands"
    project.mkdir(parents=True)
    (project / "help.md").write_text("custom help", encoding="utf-8")
    (project / "review.md").write_text("Review $ARGUMENTS", encoding="utf-8")
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "empty-home"))
    monkeypatch.chdir(tmp_path)

    assert resolve_custom_slash("/help now") is None
    inv = resolve_custom_slash("/review src/a.py")
    assert inv is not None
    assert inv.prompt == "Review src/a.py"
    assert inv.source == "project"


def test_hot_reload_picks_up_new_file(tmp_path: Path) -> None:
    from core.commands.loader import CommandLoader

    project = tmp_path / "commands"
    project.mkdir()
    loader = CommandLoader(project_dir=project, user_dir=tmp_path / "none")
    assert loader.list_commands() == []
    (project / "fix.md").write_text("Fix $ARGUMENTS", encoding="utf-8")
    assert loader.get("fix") is not None


def test_parse_slash_line_namespace() -> None:
    assert parse_slash_line("/test:unit foo") == ("test:unit", "foo")
    assert parse_slash_line("not a slash") is None


def test_reserved_covers_static_registry() -> None:
    from cli.shared.commands.registry import _STATIC_SLASH_COMMANDS

    missing = []
    for cmd, _desc in _STATIC_SLASH_COMMANDS:
        token = cmd.split()[0].lstrip("/").lower()
        if token not in RESERVED_SLASH_NAMES:
            missing.append(token)
    assert missing == []


@pytest.mark.asyncio
async def test_agent_commands_dispatches_custom_slash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli.shared.commands.agent_commands import AgentCommands

    from tests.user_cases.fake_host import FakeAgentHost

    repo = tmp_path / "proj"
    cmds = repo / ".holix" / "commands"
    cmds.mkdir(parents=True)
    (cmds / "review.md").write_text("Review please $ARGUMENTS", encoding="utf-8")
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(repo)

    sent: list[str] = []

    class Host(FakeAgentHost):
        async def _send_message(self, message: str) -> None:
            sent.append(message)

    host = Host()
    await AgentCommands(host).handle("/review src/a.py")
    assert sent == ["Review please src/a.py"]
    assert any("review" in line.lower() for line in host.transcript)


def test_get_command_loader_uses_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "app"
    cmds = repo / ".holix" / "commands"
    cmds.mkdir(parents=True)
    (cmds / "review.md").write_text("ok $1", encoding="utf-8")
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "holix-home"))
    from core.commands.expand import _loader_cache

    _loader_cache.clear()
    inv = resolve_custom_slash("/review auth.py", cwd=repo)
    assert inv is not None
    assert inv.prompt == "ok auth.py"
