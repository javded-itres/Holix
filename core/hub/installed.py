"""Summarize hub installs, profile MCP servers, and local skills for TUI/CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.hub.importer import SkillImporter
from core.hub.normalize import discover_skill_files, parse_skill_file


@dataclass
class InstalledItem:
    kind: str  # hub | mcp | skill
    title: str
    subtitle: str
    hub_entry_id: str | None = None


@dataclass
class InstalledSection:
    title: str
    items: list[InstalledItem]


def _hub_sections(config: Any) -> InstalledSection:
    skills_dir = Path(getattr(config, "skills_dir", "") or "")
    if not skills_dir.exists():
        return InstalledSection("Hub installs (plugins & skills)", [])

    entries = SkillImporter(skills_dir).lock.list_entries()
    items: list[InstalledItem] = []
    for e in sorted(entries, key=lambda x: (x.source, x.skill_name)):
        ver = f"@{e.version}" if e.version else ""
        mp = f" · {e.marketplace}" if e.marketplace else ""
        kind_label = "plugin" if e.source == "claude" or e.marketplace else e.source
        items.append(
            InstalledItem(
                kind="hub",
                title=e.skill_name,
                subtitle=f"{kind_label} · {e.slug}{ver}{mp}",
                hub_entry_id=e.id,
            )
        )
    title = f"Hub installs — plugins & skills ({len(items)})"
    return InstalledSection(title, items)


def _mcp_section(config: Any) -> InstalledSection:
    servers: dict[str, Any] = dict(getattr(config, "mcp_servers", {}) or {})
    assigns: dict[str, list[str]] = dict(getattr(config, "mcp_assignments", {}) or {})
    items: list[InstalledItem] = []
    for name in sorted(servers):
        data = servers[name] or {}
        transport = data.get("transport") or data.get("type") or "stdio"
        src = data.get("_source") or data.get("source") or ""
        assigned = [slot for slot, names in assigns.items() if name in names]
        extra = f" · agents: {', '.join(assigned)}" if assigned else ""
        src_bit = f" · {src}" if src else ""
        items.append(
            InstalledItem(
                kind="mcp",
                title=name,
                subtitle=f"{transport}{src_bit}{extra}",
            )
        )
    return InstalledSection(f"MCP servers ({len(items)})", items)


def _local_skills_section(config: Any, hub_skill_names: set[str]) -> InstalledSection:
    skills_dir = Path(getattr(config, "skills_dir", "") or "")
    if not skills_dir.exists():
        return InstalledSection("Local skills (profile)", [])

    hub_root = skills_dir / "_hub"
    items: list[InstalledItem] = []
    seen: set[str] = set()
    for path in discover_skill_files(skills_dir):
        if hub_root in path.parents:
            continue
        parsed = parse_skill_file(path)
        if not parsed:
            continue
        name = parsed.get("name") or path.stem
        if name in seen:
            continue
        seen.add(name)
        if name in hub_skill_names:
            continue
        items.append(
            InstalledItem(
                kind="skill",
                title=name,
                subtitle=str(path.relative_to(skills_dir)),
            )
        )
    items.sort(key=lambda x: x.title.lower())
    return InstalledSection(f"Local skills ({len(items)})", items)


def installed_sections(config: Any) -> list[InstalledSection]:
    """Grouped installed hub bundles, MCP servers, and non-hub skill files."""
    hub = _hub_sections(config)
    hub_names = {i.title for i in hub.items}
    return [
        hub,
        _mcp_section(config),
        _local_skills_section(config, hub_names),
    ]


def remove_hub_install(profile: str, config: Any, entry_id: str, *, drop_flat: bool = True) -> list[str]:
    """Remove hub lock entry, bundle, flat skills; clear skill_assignments."""
    from cli.core import get_profile_manager

    from core.skills.assignments import unassign_skill_from_agents

    skills_dir = Path(getattr(config, "skills_dir", "") or "")
    names = SkillImporter(skills_dir).remove(entry_id, drop_flat=drop_flat)
    manager = get_profile_manager()
    assigns = dict(getattr(config, "skill_assignments", {}) or {})
    for name in names:
        assigns = unassign_skill_from_agents(assigns, name, None)
    config.skill_assignments = assigns
    manager.save_profile(profile, config)
    return names


def installed_flat_rows(config: Any) -> list[tuple[str, InstalledItem]]:
    """Flatten sections for ListView: (row_kind, item) where row_kind is 'header' or 'item'."""
    rows: list[tuple[str, InstalledItem]] = []
    for section in installed_sections(config):
        rows.append(
            (
                "header",
                InstalledItem(kind="header", title=section.title, subtitle=""),
            )
        )
        if not section.items:
            rows.append(
                (
                    "item",
                    InstalledItem(kind="empty", title="(none)", subtitle=""),
                )
            )
        else:
            for item in section.items:
                rows.append(("item", item))
    return rows