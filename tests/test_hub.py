"""Tests for external skill hub (normalize, sources, lockfile)."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.hub.lockfile import HubEntry, HubLockfile
from core.hub.normalize import discover_skill_files, parse_skill_file, write_flat_skill
from core.hub.sources import parse_install_source, skills_sh_to_git_url


def test_parse_clawhub_slug():
    p = parse_install_source("my-skill@1.2.0")
    assert p.kind == "clawhub"
    assert p.ref == "my-skill"
    assert p.version == "1.2.0"


def test_parse_skills_sh():
    p = parse_install_source("skills-sh/vercel-labs/agent-skills/demo")
    assert p.kind == "skills-sh"
    url, sub = skills_sh_to_git_url(p.ref)
    assert "github.com/vercel-labs/agent-skills" in url
    assert sub == "demo"


def test_discover_skill_md(tmp_path: Path):
    (tmp_path / "flat.md").write_text("---\nname: flat\ndescription: x\n---\n\nbody\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "SKILL.md").write_text(
        "---\nname: bundled\ndescription: y\n---\n\nUse {baseDir}\n",
        encoding="utf-8",
    )
    paths = discover_skill_files(tmp_path)
    assert len(paths) == 2
    skill = parse_skill_file(bundle / "SKILL.md")
    assert skill is not None
    assert str(bundle) in skill["content"]


def test_write_flat_skill(tmp_path: Path):
    skill = {"name": "demo", "description": "d", "tags": [], "content": "hello"}
    out = write_flat_skill(tmp_path / "demo.md", skill)
    assert out.exists()
    loaded = parse_skill_file(out)
    assert loaded and loaded["name"] == "demo"


def test_hub_lockfile_roundtrip(tmp_path: Path):
    lock = HubLockfile(tmp_path / "hub-lock.json")
    lock.upsert(
        HubEntry(
            id="clawhub:git",
            source="clawhub",
            slug="git",
            version="1.0.0",
            install_path=str(tmp_path / "_hub/git"),
            skill_name="git",
            installed_at=HubLockfile.now_iso(),
        )
    )
    assert lock.get("clawhub:git") is not None
    assert len(lock.list_entries()) == 1


def test_plugin_search_score_order():
    from core.hub.claude_marketplace import MarketplacePlugin, search_plugins

    plugins = [
        MarketplacePlugin("github", "GitHub MCP integration", "productivity", "", {}),
        MarketplacePlugin("commit-commands", "Git commits", "development", "", {}),
        MarketplacePlugin("my-git-helper", "misc", "dev", "", {}),
    ]

    import core.hub.claude_marketplace as mp

    mp._PLUGIN_LIST_CACHE["__test__"] = plugins
    try:
        hits = search_plugins("__test__", "git", limit=5)
        assert hits[0].name == "github"
    finally:
        mp._PLUGIN_LIST_CACHE.pop("__test__", None)


def test_parse_claude_source():
    from core.hub.sources import parse_install_source

    p = parse_install_source("claude:commit-commands@claude-official")
    assert p.kind == "claude"
    assert p.ref == "commit-commands"


def test_parse_hermes_source():
    p = parse_install_source("hermes:api-builder")
    assert p.kind == "hermes"
    assert p.ref == "api-builder"


def test_claude_mcp_inline_env(monkeypatch: pytest.MonkeyPatch):
    from core.hub.claude_mcp import parse_claude_mcp_json

    monkeypatch.setenv("TOKEN", "secret")
    raw = {
        "gh": {
            "type": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer ${TOKEN}"},
        }
    }
    out = parse_claude_mcp_json(raw)
    assert "MCP_HEADER_Authorization" in out["gh"]["env"]
    assert out["gh"]["env"]["MCP_HEADER_Authorization"] == "Bearer secret"


def test_claude_mcp_http():
    from core.hub.claude_mcp import parse_claude_mcp_json

    raw = {
        "github": {
            "type": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer ${TOKEN}"},
        }
    }
    out = parse_claude_mcp_json(raw)
    assert "github" in out
    assert out["github"]["transport"] == "sse"
    assert out["github"]["url"] == "https://example.com/mcp"


def test_slash_registry(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "demo.md").write_text(
        "---\nname: demo\ndescription: Test skill\nuser-invocable: true\n---\n\nDo demo.\n",
        encoding="utf-8",
    )
    from core.hub.slash_registry import load_skill_slash_commands, rebuild_slash_registry

    rebuild_slash_registry(skills)
    cmds = load_skill_slash_commands(skills)
    assert any(c == "/demo" for c, _ in cmds)


def test_hermes_skill_subpath():
    from core.hub.hermes_hub import hermes_skill_subpath

    assert hermes_skill_subpath("api-builder") == "skills/api-builder"


def test_installed_sections(tmp_path: Path):
    from core.hub.installed import installed_sections
    from core.hub.lockfile import HubEntry, HubLockfile

    skills = tmp_path / "skills"
    skills.mkdir()
    lock = HubLockfile(skills.parent / "hub-lock.json")
    lock.upsert(
        HubEntry(
            id="clawhub:git",
            source="clawhub",
            slug="git",
            version="1.0",
            install_path=str(skills / "_hub/git"),
            skill_name="git",
            installed_at=HubLockfile.now_iso(),
            marketplace=None,
        )
    )
    (skills / "local.md").write_text(
        "---\nname: local\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )

    class Cfg:
        skills_dir = str(skills)
        mcp_servers = {"fs": {"transport": "stdio", "_source": "manual"}}
        mcp_assignments = {"main": ["fs"]}

    sections = installed_sections(Cfg())
    assert sections[0].items[0].title == "git"
    assert sections[1].items[0].title == "fs"
    assert any(i.title == "local" for i in sections[2].items)


def test_remove_hub_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.hub.installed import remove_hub_install
    from core.hub.lockfile import HubEntry, HubLockfile

    skills = tmp_path / "skills"
    bundle = skills / "_hub" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "demo.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    (skills / "demo.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    lock = HubLockfile(skills.parent / "hub-lock.json")
    lock.upsert(
        HubEntry(
            id="clawhub:demo",
            source="clawhub",
            slug="demo",
            version=None,
            install_path=str(bundle),
            skill_name="demo",
            installed_at=HubLockfile.now_iso(),
        )
    )

    class Cfg:
        skills_dir = str(skills)
        skill_assignments = {"main": ["demo"]}

    cfg = Cfg()

    class _PM:
        def save_profile(self, profile: str, config: object) -> None:
            pass

    monkeypatch.setattr("cli.core.get_profile_manager", lambda: _PM())

    names = remove_hub_install("test", cfg, "clawhub:demo")
    assert "demo" in names
    assert not bundle.exists()
    assert HubLockfile(skills.parent / "hub-lock.json").get("clawhub:demo") is None
    assert cfg.skill_assignments == {}


def test_resolve_hub_source():
    from core.hub.catalog import resolve_hub_source

    assert resolve_hub_source("clawhub") == "clawhub"
    assert resolve_hub_source("claude") == "claude-official"
    assert resolve_hub_source("plugins") == "claude-official"
    assert resolve_hub_source("nope") is None


def test_catalog_parse_selection():
    from core.hub.catalog import parse_selection

    assert parse_selection("1, 3", 5) == [1, 3]
    assert parse_selection("9", 5) == []
    assert parse_selection("", 5) == []


def test_hub_autoupdate_disabled(tmp_path: Path):
    from core.hub.autoupdate import run_hub_autoupdate
    from core.hub.importer import SkillImporter

    skills = tmp_path / "skills"
    skills.mkdir()
    importer = SkillImporter(skills)
    result = run_hub_autoupdate(importer, enabled=False)
    assert not result.ran
    assert result.reason == "disabled"


def test_suggested_cron_line_unix(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.hub.autoupdate import suggested_cron_line

    monkeypatch.setattr("core.platform_compat.IS_WINDOWS", False)
    monkeypatch.setattr("core.platform_compat.holix_home_display", lambda: "/data/helix")
    line = suggested_cron_line("work")
    assert line.startswith("0 4 * * *")
    assert "holix hub autoupdate -p work" in line
    assert "/data/helix/logs/hub-autoupdate.log" in line


def test_suggested_cron_line_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.hub.autoupdate import suggested_cron_line

    monkeypatch.setattr("core.platform_compat.IS_WINDOWS", True)
    monkeypatch.setattr(
        "core.platform_compat.holix_home_display",
        lambda: r"C:\Users\me\AppData\Local\Holix",
    )
    line = suggested_cron_line("default")
    assert "Task Scheduler" in line
    assert "holix hub autoupdate -p default" in line
    assert "hub-autoupdate.log" in line
    assert r"C:\Users\me\AppData\Local\Holix" in line


def test_hub_agent_slot_options():
    from cli.tui.modals.hub_browser import _agent_slot_options

    class Cfg:
        skill_assignments = {"coder": ["git"]}
        agent_models = {"researcher": {}}

    opts = _agent_slot_options(Cfg())
    values = [v for _, v, _ in opts]
    assert "main" in values
    assert "coder" in values
    assert "researcher" in values
    assert next(o for o in opts if o[1] == "main")[2] is True


def test_importer_remove(tmp_path: Path):
    from core.hub.importer import SkillImporter
    from core.hub.lockfile import HubEntry, HubLockfile

    skills = tmp_path / "skills"
    skills.mkdir()
    bundle = skills / "_hub" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "demo.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    (skills / "demo.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    importer = SkillImporter(skills)
    importer.lock.upsert(
        HubEntry(
            id="clawhub:demo",
            source="clawhub",
            slug="demo",
            version=None,
            install_path=str(bundle),
            skill_name="demo",
            installed_at=HubLockfile.now_iso(),
        )
    )
    names = importer.remove("clawhub:demo")
    assert "demo" in names
    assert not bundle.exists()
    assert not (skills / "demo.md").exists()
    assert importer.lock.get("clawhub:demo") is None


@pytest.mark.integration
def test_clawhub_search_live():
    from urllib.error import HTTPError

    from core.hub.clawhub import ClawHubClient

    try:
        hits = ClawHubClient().search("git", limit=3)
    except HTTPError as exc:
        if 500 <= exc.code < 600:
            pytest.skip(f"ClawHub temporarily unavailable: HTTP {exc.code}")
        raise
    assert hits
    assert hits[0].slug