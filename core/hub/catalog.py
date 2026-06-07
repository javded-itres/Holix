"""Shared hub catalog search (CLI interactive + TUI browser)."""

from __future__ import annotations

from dataclasses import dataclass

from core.hub.clawhub import ClawHubClient
from core.hub.claude_marketplace import (
    MARKETPLACES,
    MarketplacePlugin,
    plugin_install_spec,
    search_plugins,
)
from core.hub.hermes_hub import list_hermes_skills, search_hermes_skills
from core.hub.skills_sh import search_skills_sh


@dataclass
class CatalogRow:
    install_spec: str
    title: str
    category: str
    summary: str
    has_mcp: bool = False


SOURCES: list[tuple[str, str, str]] = [
    ("1", "claude-official", "Claude official plugins (Anthropic)"),
    ("2", "claude-code", "Claude Code demo plugins"),
    ("3", "clawhub", "ClawHub skills (OpenClaw registry)"),
    ("4", "skills-sh", "skills.sh / GitHub agent-skills"),
    ("5", "hermes", "HermesHub (Nous Research, GitHub)"),
]

SOURCE_BY_KEY = {key: sid for key, sid, _ in SOURCES}
SOURCE_IDS = [sid for _, sid, _ in SOURCES]

HUB_SOURCE_ALIASES: dict[str, str] = {
    "clawhub": "clawhub",
    "hermes": "hermes",
    "claude-official": "claude-official",
    "claude-code": "claude-code",
    "skills-sh": "skills-sh",
    "skills": "skills-sh",
    "claude": "claude-official",
    "plugins": "claude-official",
    "marketplace": "claude-official",
    "official": "claude-official",
}


def resolve_hub_source(name: str) -> str | None:
    """Map slash arg or alias to catalog id (clawhub, hermes, …)."""
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in SOURCE_IDS:
        return key
    return HUB_SOURCE_ALIASES.get(key)


def fetch_catalog_rows(
    source: str,
    query: str,
    *,
    limit: int = 20,
    skills_sh_requires_query: bool = True,
) -> list[CatalogRow]:
    """Load catalog rows for a source id (clawhub, hermes, claude-official, …)."""
    q = query.strip()
    rows: list[CatalogRow] = []

    if source in MARKETPLACES:
        plugins = search_plugins(source, q, limit=limit)
        for p in plugins:
            rows.append(
                CatalogRow(
                    install_spec=plugin_install_spec(p, source),
                    title=p.name,
                    category=p.category or "plugin",
                    summary=(p.description or "")[:72],
                    has_mcp=_plugin_likely_has_mcp(p),
                )
            )
        return rows

    if source == "hermes":
        hits = search_hermes_skills(q, limit=limit) if q else list_hermes_skills(limit=limit)
        for h in hits:
            rows.append(
                CatalogRow(
                    install_spec=h.install_spec,
                    title=h.slug,
                    category=h.category,
                    summary=(h.description or h.slug)[:72],
                )
            )
        return rows

    if source == "clawhub":
        client = ClawHubClient()
        hits = client.search(q, limit=limit) if q else client.browse(limit=limit)
        for h in hits:
            spec = f"clawhub:{h.slug}"
            if h.version:
                spec = f"{spec}@{h.version}"
            rows.append(
                CatalogRow(
                    install_spec=spec,
                    title=h.slug,
                    category="clawhub",
                    summary=(h.summary or h.display_name)[:72],
                )
            )
        return rows

    if source == "skills-sh":
        if skills_sh_requires_query and not q:
            return []
        for h in search_skills_sh(q or "skill", limit=limit):
            rows.append(
                CatalogRow(
                    install_spec=h.install_spec,
                    title=h.skill_name,
                    category=h.repo,
                    summary=h.path[:72],
                )
            )
        return rows

    return rows


def _plugin_likely_has_mcp(plugin: MarketplacePlugin) -> bool:
    cat = (plugin.category or "").lower()
    if cat in ("productivity", "infrastructure", "monitoring", "design"):
        return True
    blob = f"{plugin.name} {plugin.description}".lower()
    return any(k in blob for k in ("mcp", "github", "gitlab", "slack", "jira", "notion"))


def parse_selection(choice: str, max_n: int) -> list[int]:
    choice = choice.strip().lower()
    if not choice:
        return []
    indices: list[int] = []
    for part in choice.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            continue
        if 1 <= idx <= max_n:
            indices.append(idx)
    return indices