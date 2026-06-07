"""Claude Code plugin marketplace catalog and install materialization."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.hub.claude_convert import convert_command_file
from core.hub.claude_mcp import parse_claude_mcp_json
from core.mcp.installer import clone_or_update_git, _run
from core.platform_compat import resolve_helix_home

HUB_CACHE = resolve_helix_home() / "hub-cache"

MARKETPLACES: dict[str, dict[str, str]] = {
    "claude-official": {
        "repo": "https://github.com/anthropics/claude-plugins-official.git",
        "marketplace": ".claude-plugin/marketplace.json",
    },
    "claude-code": {
        "repo": "https://github.com/anthropics/claude-code.git",
        "marketplace": "plugins/.claude-plugin/marketplace.json",
    },
}


@dataclass
class MarketplacePlugin:
    name: str
    description: str
    category: str
    homepage: str
    source: Any


@dataclass
class ClaudeInstallBundle:
    plugin_name: str
    marketplace: str
    plugin_dir: Path
    skills_installed: list[str]
    mcp_servers: dict[str, dict[str, Any]]


def _cache_dir_for_repo(url: str) -> Path:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[:60]
    return HUB_CACHE / key


def ensure_marketplace_repo(marketplace_id: str) -> tuple[Path, dict[str, Any]]:
    if marketplace_id not in MARKETPLACES:
        raise ValueError(
            f"Unknown marketplace '{marketplace_id}'. Known: {', '.join(MARKETPLACES)}"
        )
    meta = MARKETPLACES[marketplace_id]
    repo = clone_or_update_git(meta["repo"], _cache_dir_for_repo(meta["repo"]).name)
    mp_path = repo / meta["marketplace"]
    if not mp_path.exists():
        raise FileNotFoundError(f"marketplace.json not found: {mp_path}")
    data = json.loads(mp_path.read_text(encoding="utf-8"))
    return repo, data


_PLUGIN_LIST_CACHE: dict[str, list[MarketplacePlugin]] = {}


def list_plugins(marketplace_id: str, *, use_cache: bool = True) -> list[MarketplacePlugin]:
    if use_cache and marketplace_id in _PLUGIN_LIST_CACHE:
        return _PLUGIN_LIST_CACHE[marketplace_id]

    _, data = ensure_marketplace_repo(marketplace_id)
    out: list[MarketplacePlugin] = []
    for p in data.get("plugins", []):
        if not isinstance(p, dict) or not p.get("name"):
            continue
        out.append(
            MarketplacePlugin(
                name=p["name"],
                description=(p.get("description") or "")[:300],
                category=p.get("category") or "",
                homepage=p.get("homepage") or "",
                source=p.get("source"),
            )
        )
    out.sort(key=lambda x: x.name.lower())
    if use_cache:
        _PLUGIN_LIST_CACHE[marketplace_id] = out
    return out


def _plugin_search_score(plugin: MarketplacePlugin, query: str) -> int:
    q = query.lower().strip()
    if not q:
        return 1
    name = plugin.name.lower()
    desc = (plugin.description or "").lower()
    cat = (plugin.category or "").lower()
    if name == q:
        return 1000
    if name.startswith(q):
        return 900 - len(name)
    if q in name:
        return 800 - name.find(q)
    if q in cat:
        return 500
    if q in desc:
        return 300 - min(desc.find(q), 200)
    return 0


def search_plugins(marketplace_id: str, query: str, *, limit: int = 15) -> list[MarketplacePlugin]:
    all_plugins = list_plugins(marketplace_id)
    q = (query or "").strip()
    if not q:
        return all_plugins[:limit]

    scored = [( _plugin_search_score(p, q), p) for p in all_plugins]
    scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
    return [p for _, p in scored[:limit]]


def plugin_install_spec(plugin: MarketplacePlugin, marketplace_id: str) -> str:
    return f"claude:{plugin.name}@{marketplace_id}"


def resolve_plugin_source(repo_root: Path, source: Any) -> Path:
    if isinstance(source, str):
        rel = source.lstrip("./")
        path = (repo_root / rel).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Plugin path not found: {path}")
        return path

    if isinstance(source, dict):
        kind = source.get("source", "")
        if kind == "git-subdir":
            url = source.get("url")
            sub = source.get("path", "")
            ref = source.get("ref") or source.get("sha")
            if not url:
                raise ValueError("git-subdir source missing url")
            cloned = clone_or_update_git(url, _cache_dir_for_repo(url).name)
            if ref:
                _run(["git", "-C", str(cloned), "fetch", "--depth", "1", "origin", ref], check=False)
                _run(["git", "-C", str(cloned), "checkout", ref], check=False)
            dest = (cloned / sub).resolve()
            if not dest.exists():
                raise FileNotFoundError(dest)
            return dest

    raise ValueError(f"Unsupported plugin source: {source!r}")


def materialize_plugin(
    repo_root: Path,
    plugin: MarketplacePlugin,
    dest_root: Path,
) -> ClaudeInstallBundle:
    src = resolve_plugin_source(repo_root, plugin.source)
    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(src, dest_root, ignore=shutil.ignore_patterns(".git"))

    skills_installed: list[str] = []

    skills_dir = dest_root / "skills"
    if skills_dir.is_dir():
        for skill_md in skills_dir.rglob("SKILL.md"):
            rel = skill_md.relative_to(dest_root)
            skills_installed.append(str(rel.parent or "skills"))

    commands_dir = dest_root / "commands"
    if commands_dir.is_dir():
        out_commands = dest_root / "_helix_commands"
        out_commands.mkdir(exist_ok=True)
        for cmd_file in commands_dir.glob("*.md"):
            skill_name = re.sub(r"[^a-z0-9]+", "-", f"{plugin.name}-{cmd_file.stem}".lower()).strip("-")
            bundle = out_commands / skill_name
            bundle.mkdir(exist_ok=True)
            (bundle / "SKILL.md").write_text(
                convert_command_file(cmd_file, plugin_name=plugin.name),
                encoding="utf-8",
            )
            skills_installed.append(str(bundle.relative_to(dest_root)))

    mcp_servers: dict[str, dict[str, Any]] = {}
    mcp_file = dest_root / ".mcp.json"
    if mcp_file.exists():
        raw = json.loads(mcp_file.read_text(encoding="utf-8"))
        mcp_servers = parse_claude_mcp_json(raw)

    return ClaudeInstallBundle(
        plugin_name=plugin.name,
        marketplace=repo_root.name,
        plugin_dir=dest_root,
        skills_installed=skills_installed,
        mcp_servers=mcp_servers,
    )