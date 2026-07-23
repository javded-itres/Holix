""" /spec slash command handler. """

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.shared.commands.spec_commands import (
    _looks_like_project_path,
    _parse_spec_args,
    _resolve_create_fill_args,
    _workspace,
    run_spec_command,
)


class _Host:
    def __init__(self, root: Path):
        self.workspace_root = root
        self.lines: list[str] = []
        self.agent_messages: list[str] = []
        self.agent = None

    def transcript_write(self, text: str) -> None:
        self.lines.append(str(text))

    async def _send_message(self, message: str) -> None:
        self.agent_messages.append(message)


class _MessengerHost:
    """Telegram/MAX-like host: profile + agent config, no workspace_root attr."""

    def __init__(self, root: Path, profile: str = "user-a"):
        self.profile = profile
        self.lines: list[str] = []
        self.agent_messages: list[str] = []
        self.agent = SimpleNamespace(config=SimpleNamespace(workspace_root=str(root)))
        self._session = SimpleNamespace(profile=profile, agent=self.agent)

    def transcript_write(self, text: str) -> None:
        self.lines.append(str(text))

    async def _send_message(self, message: str) -> None:
        self.agent_messages.append(message)


@pytest.mark.asyncio
async def test_spec_init_and_propose(tmp_path: Path):
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    assert (tmp_path / "openspec" / "config.yaml").is_file()
    await run_spec_command(host, "/spec propose my-feat")
    assert (tmp_path / "openspec" / "changes" / "my-feat" / "tasks.md").is_file()
    await run_spec_command(host, "/spec")
    joined = "\n".join(host.lines)
    assert "my-feat" in joined or "SDD" in joined


@pytest.mark.asyncio
async def test_spec_create_show_archive(tmp_path: Path):
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(host, "/spec create demo-feat")
    host.lines.clear()
    await run_spec_command(host, "/spec show demo-feat")
    joined = "\n".join(host.lines)
    assert "demo-feat" in joined
    assert "proposal.md" in joined
    await run_spec_command(host, "/spec archive demo-feat")
    assert not (tmp_path / "openspec" / "changes" / "demo-feat").is_dir()
    archived = list((tmp_path / "openspec" / "changes" / "archive").glob("*-demo-feat"))
    assert archived, "expected archive folder *-demo-feat"


@pytest.mark.asyncio
async def test_spec_apply_dispatches_agent(tmp_path: Path):
    from core.sdd.store import SpecStore

    host = _Host(tmp_path)
    proj = "apps/web"
    await run_spec_command(host, f"/spec init {proj}")
    store = SpecStore(tmp_path / proj)
    assert store.is_initialized()
    store.create_change("feat-a", domain="web")
    store.write_artifact(
        "feat-a",
        "proposal",
        "# Proposal\n\n## Why\nNeed feature for users in the app.\n\n## What\nUI toggle.\n\n## Impact\nNone.\n",
    )
    store.write_artifact(
        "feat-a",
        "specs",
        "## ADDED Requirements\n\n### Requirement: Toggle\nThe system SHALL toggle.\n\n"
        "#### Scenario: Ok\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain="web",
    )
    store.write_artifact(
        "feat-a",
        "tasks",
        "# T\n\n- [ ] 1.1 Do it\n  - **assignee:** `main`\n  - **reason:** solo\n",
    )
    store.set_apply_mode("feat-a", "self")
    host.lines.clear()
    host.agent_messages.clear()
    await run_spec_command(host, f"/spec apply feat-a {proj}")
    joined = "\n".join(host.lines)
    assert "Apply plan" in joined or "feat-a" in joined
    assert "Cannot apply" not in joined
    assert "not found" not in joined.lower()
    assert host.agent_messages
    assert "feat-a" in host.agent_messages[-1]
    assert "sdd_apply" in host.agent_messages[-1]


@pytest.mark.asyncio
async def test_spec_create_with_request_dispatches_fill(tmp_path: Path):
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(
        host, "/spec create oauth -- add OAuth login for the mobile app"
    )
    assert (tmp_path / "openspec" / "changes" / "oauth" / "tasks.md").is_file()
    assert (tmp_path / "openspec" / "changes" / "oauth" / "request.md").is_file()
    assert host.agent_messages
    assert "oauth" in host.agent_messages[-1]
    assert "sdd_write_artifact" in host.agent_messages[-1]


@pytest.mark.asyncio
async def test_spec_create_with_request_keeps_clarifying_when_gate_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Gate ON: create must leave clarifying/0 so survey mode runs (not score=100)."""
    import cli.shared.commands.spec_commands as spec_cmd
    from core.sdd.prefs import SddPrefs
    from core.sdd.understanding import gate_blocks_propose, load_understanding

    monkeypatch.setattr(
        spec_cmd,
        "_sdd_prefs",
        lambda _host: SddPrefs(
            understanding_gate_enabled=True, understanding_threshold=80
        ),
    )
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(
        host, '/spec create company "Добавить раздел Компания и группы"'
    )
    und = load_understanding(tmp_path, "company")
    assert und is not None
    assert und.enabled is True
    assert und.status == "clarifying"
    assert und.score == 0
    assert gate_blocks_propose(tmp_path, "company") is not None
    assert host.agent_messages
    last = host.agent_messages[-1]
    assert "sdd_update_understanding" in last
    assert "sdd_confirm_understanding" in last
    assert "score=100 to skip" in last or "do NOT set score=100" in last


@pytest.mark.asyncio
async def test_spec_fill_unlocks_understanding_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Explicit /spec fill unlocks the gate so sdd_write_artifact can proceed."""
    import cli.shared.commands.spec_commands as spec_cmd
    from core.sdd.prefs import SddPrefs
    from core.sdd.understanding import gate_blocks_propose, load_understanding

    monkeypatch.setattr(
        spec_cmd,
        "_sdd_prefs",
        lambda _host: SddPrefs(
            understanding_gate_enabled=True, understanding_threshold=80
        ),
    )
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(
        host, '/spec create company "Добавить раздел Компания и группы"'
    )
    und = load_understanding(tmp_path, "company")
    assert und is not None and und.status == "clarifying"
    host.agent_messages.clear()
    await run_spec_command(host, "/spec fill company")
    und = load_understanding(tmp_path, "company")
    assert und is not None
    assert und.status == "confirmed"
    assert und.score >= und.threshold
    assert gate_blocks_propose(tmp_path, "company") is None
    assert host.agent_messages
    assert "sdd_write_artifact" in host.agent_messages[-1]


def test_parse_quoted_request_not_as_project():
    """Telegram: /spec create company \"long RU text…\" must not treat text as project."""
    rest = (
        'company "Добавить раздел Компания, где требуется пользователей '
        'распределять по компаниям"'
    )
    tokens, project, request = _parse_spec_args(rest)
    assert project == ""
    assert request == ""
    change_id, proj, req = _resolve_create_fill_args(tokens, project, request)
    assert change_id == "company"
    assert proj == ""
    assert "Компания" in req
    assert "пользователей" in req
    assert not _looks_like_project_path(req.split()[0])


def test_parse_create_unquoted_request_words():
    tokens, project, request = _parse_spec_args(
        "company Добавить раздел Компания с группами"
    )
    change_id, proj, req = _resolve_create_fill_args(tokens, project, request)
    assert change_id == "company"
    assert proj == ""
    assert req.startswith("Добавить раздел")


def test_parse_create_project_path_and_dash_request():
    tokens, project, request = _parse_spec_args(
        "oauth apps/web -- add OAuth login for mobile"
    )
    change_id, proj, req = _resolve_create_fill_args(tokens, project, request)
    assert change_id == "oauth"
    assert proj == "apps/web"
    assert "OAuth" in req


@pytest.mark.asyncio
async def test_spec_create_quoted_russian_dispatches_fill(tmp_path: Path):
    host = _Host(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(
        host,
        '/spec create company "Добавить раздел Компания, пользователи в группы"',
    )
    assert (tmp_path / "openspec" / "changes" / "company" / "tasks.md").is_file()
    joined = "\n".join(host.lines)
    assert "project `Добавить" not in joined
    assert "(project `.`)" in joined
    assert "Request:" in joined and "Компания" in joined
    assert host.agent_messages
    assert "company" in host.agent_messages[-1]
    assert "Компания" in host.agent_messages[-1]
    assert "sdd_write_artifact" in host.agent_messages[-1]


def test_workspace_from_agent_config(tmp_path: Path):
    host = _MessengerHost(tmp_path)
    assert _workspace(host) == tmp_path.resolve()


@pytest.mark.asyncio
async def test_messenger_host_spec_list(tmp_path: Path):
    host = _MessengerHost(tmp_path)
    await run_spec_command(host, "/spec init")
    await run_spec_command(host, "/spec create x")
    host.lines.clear()
    await run_spec_command(host, "/spec")
    joined = "\n".join(host.lines)
    assert "x" in joined
    assert str(tmp_path) in joined or "workspace" in joined.lower()
