"""Shared hub catalog search (CLI interactive + TUI browser)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from core.hub.claude_marketplace import (
    MARKETPLACES,
    MarketplacePlugin,
    plugin_install_spec,
    search_plugins,
)
from core.hub.clawhub import ClawHubClient
from core.hub.hermes_hub import list_hermes_skills, search_hermes_skills
from core.hub.skills_sh import search_skills_sh

logger = logging.getLogger(__name__)

# Short TTL so Studio auto-browse / refresh does not hammer remote registries.
_CATALOG_CACHE_TTL_SEC = 90.0
_catalog_cache: dict[tuple[str, str, int, bool], tuple[float, list["CatalogRow"]]] = {}


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
    use_cache: bool = True,
) -> list[CatalogRow]:
    """Load catalog rows for a source id (clawhub, hermes, claude-official, …)."""
    q = query.strip()
    lim = max(1, min(int(limit or 20), 80))
    cache_key = (source, q.lower(), lim, skills_sh_requires_query)
    if use_cache:
        hit = _catalog_cache.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CATALOG_CACHE_TTL_SEC:
            return list(hit[1])

    rows: list[CatalogRow] = []

    try:
        if source in MARKETPLACES:
            # browse_only: no git clone; raw JSON or local cache only
            plugins = search_plugins(source, q, limit=lim, browse_only=True)
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
        elif source == "hermes":
            hits = search_hermes_skills(q, limit=lim) if q else list_hermes_skills(limit=lim)
            for h in hits:
                rows.append(
                    CatalogRow(
                        install_spec=h.install_spec,
                        title=h.slug,
                        category=h.category,
                        summary=(h.description or h.slug)[:72],
                    )
                )
        elif source == "clawhub":
            client = ClawHubClient()
            hits = client.search(q, limit=lim) if q else client.browse(limit=lim)
            for h in hits:
                # Prefer @owner/slug so install avoids AMBIGUOUS_SKILL_SLUG (HTTP 409)
                title = h.qualified_slug if h.owner_handle else h.slug
                rows.append(
                    CatalogRow(
                        install_spec=h.install_spec,
                        title=title,
                        category="clawhub",
                        summary=(h.summary or h.display_name)[:72],
                    )
                )
        elif source == "skills-sh":
            # Allow empty query = browse top skill dirs (code-search needs a query)
            for h in search_skills_sh(q, limit=lim):
                rows.append(
                    CatalogRow(
                        install_spec=h.install_spec,
                        title=h.skill_name,
                        category=h.repo,
                        summary=h.path[:72],
                    )
                )
            if skills_sh_requires_query and not q and not rows:
                rows = []
    except Exception as exc:
        # Never let a hung/broken registry poison Studio; caller may show warning.
        logger.warning("hub catalog fetch failed source=%s: %s", source, exc)
        rows = []

    if use_cache and rows:
        _catalog_cache[cache_key] = (time.monotonic(), list(rows))
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