""" /spec slash command handler. """

from __future__ import annotations

from pathlib import Path

import pytest
from cli.shared.commands.spec_commands import run_spec_command


class _Host:
    def __init__(self, root: Path):
        self.workspace_root = root
        self.lines: list[str] = []

    def transcript_write(self, text: str) -> None:
        self.lines.append(str(text))


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
async def test_spec_apply_multi_project(tmp_path: Path):
    from core.sdd.store import SpecStore

    host = _Host(tmp_path)
    proj = "apps/web"
    await run_spec_command(host, f"/spec init {proj}")
    store = SpecStore(tmp_path / proj)
    assert store.is_initialized()
    store.create_change("feat-a", domain="web")
    # fill enough for apply-ready
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
    await run_spec_command(host, f"/spec apply feat-a {proj}")
    joined = "\n".join(host.lines)
    assert "Apply plan" in joined or "feat-a" in joined
    assert "Cannot apply" not in joined
    assert "not found" not in joined.lower()
