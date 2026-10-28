"""Pasted skill and MCP links install into the workspace .holix directory."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from core.hub.link_install import (
    classify_share_link,
    expand_user_message_for_share_link,
    install_share_link,
    share_link_to_install,
)
from core.mcp.installer import detect_command, detected_mcp_command


def test_classify_skill_and_mcp_links() -> None:
    skill = classify_share_link("https://github.com/acme/skills/blob/main/skills/review/SKILL.md")
    assert skill is not None
    assert skill.kind == "skill-spec"
    assert skill.spec == (
        "https://raw.githubusercontent.com/acme/skills/main/skills/review/SKILL.md"
    )

    tree = classify_share_link("https://github.com/acme/skills/tree/main/skills/review")
    assert tree is not None
    assert tree.kind == "skill-git"
    assert tree.git_url == "https://github.com/acme/skills.git"
    assert tree.ref == "main"
    assert tree.subpath == "skills/review"

    page = classify_share_link("https://skills.sh/vercel-labs/agent-skills/web-design")
    assert page is not None and page.spec == "skills-sh/vercel-labs/agent-skills/web-design"

    hub = classify_share_link("https://clawhub.ai/steipete/sleep")
    assert hub is not None and hub.spec == "clawhub:@steipete/sleep"

    remote = classify_share_link("https://mcp.context7.com/mcp?token=secret")
    assert remote is not None
    assert remote.kind == "mcp-http"
    assert remote.name == "context7"
    assert "token=secret" in remote.url

    sse = classify_share_link("http://127.0.0.1:3000/sse")
    assert sse is not None and sse.kind == "mcp-sse"

    git_mcp = classify_share_link("https://github.com/org/github-mcp-server")
    assert git_mcp is not None and git_mcp.kind == "mcp-git"

    assert classify_share_link("https://example.com/blog/post") is None
    assert classify_share_link("https://github.com/acme/demo/issues/4") is None


def test_bare_link_is_an_install_request_and_a_look_is_not() -> None:
    bare = "https://github.com/acme/widgets"
    assert share_link_to_install(bare) == bare
    hinted = expand_user_message_for_share_link(bare)
    assert "action=install_link" in hinted
    assert bare in hinted

    asked = "подключи https://skills.sh/acme/repo/demo"
    assert share_link_to_install(asked) is not None

    look = "посмотри https://github.com/acme/widgets"
    assert share_link_to_install(look) is None
    assert expand_user_message_for_share_link(look) == look

    article = "https://example.com/docs/guide"
    assert expand_user_message_for_share_link(article) == article


def test_empty_clone_is_not_detected_as_mcp(tmp_path: Path) -> None:
    assert detected_mcp_command(tmp_path) is None
    command, args, notes = detect_command(tmp_path)
    assert command == "node"
    assert args == [str(tmp_path / "dist" / "index.js")]
    assert "README" in notes


def test_repo_without_skill_becomes_stdio_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloned = tmp_path / "repo"
    cloned.mkdir()
    (cloned / "index.js").write_text("console.log('mcp')\n", encoding="utf-8")

    def _no_skill(self, *args, **kwargs):
        del self, args, kwargs
        raise ValueError("No SKILL.md found at repo")

    monkeypatch.setattr("core.hub.importer.SkillImporter._install_git", _no_skill)
    monkeypatch.setattr("core.mcp.installer.clone_or_update_git", lambda url, name: cloned)
    monkeypatch.setattr("core.mcp.installer.auto_prepare", lambda *args, **kwargs: None)

    result = install_share_link("https://github.com/acme/widgets", skills_dir=tmp_path / "skills")
    assert result.kind == "mcp"
    assert result.name == "widgets"
    assert result.mcp is not None
    assert result.mcp["command"] == "node"
    assert result.mcp["args"] == [str(cloned / "index.js")]


@pytest.mark.asyncio
async def test_install_link_saves_http_mcp_without_echoing_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    from core.tools.workspace_holix import WorkspaceHolixTool

    class Config:
        workspace_root = str(workspace)
        mcp_enabled = True
        mcp_servers: dict = {}
        mcp_assignments: dict = {"main": []}

        def with_overrides(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            return self

    class Agent:
        def __init__(self) -> None:
            self.config = Config()
            self.skills = None
            self.tools = self
            self.connected = None

        async def connect_workspace_mcp(self, name: str, data: dict) -> str:
            self.connected = (name, data)
            return "started"

    agent = Agent()
    tool = WorkspaceHolixTool()
    tool.bind_agent(agent)
    text = await tool.execute(
        action="install_link",
        link="https://mcp.context7.com/mcp?token=secret",
    )
    assert "context7" in text
    assert "secret" not in text
    raw = yaml.safe_load((workspace / ".holix" / "config.yaml").read_text(encoding="utf-8"))
    saved = raw["mcp_servers"]["context7"]
    assert saved["transport"] == "http"
    assert saved["url"] == "https://mcp.context7.com/mcp?token=secret"
    assert agent.connected[0] == "context7"
    assert agent.connected[1]["transport"] == "http"
