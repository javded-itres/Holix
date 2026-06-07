"""Ship default skills with Helix and seed them into new profiles."""

from __future__ import annotations

from pathlib import Path

_BUNDLED_ROOT = Path(__file__).resolve().parent / "bundled"


def bundled_skills_root() -> Path:
    return _BUNDLED_ROOT


def bundled_skill_names() -> list[str]:
    """Names of skills packaged under ``core/skills/bundled/``."""
    from core.hub.normalize import parse_skill_file

    root = bundled_skills_root()
    if not root.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        parsed = parse_skill_file(skill_md)
        names.append(parsed.get("name") if parsed else entry.name)
    return names


def ensure_bundled_assigned_to_main(
    assignments: dict[str, list[str]] | None,
    skill_names: list[str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Add bundled skills to the main agent allowlist (creates whitelist if needed).

    Returns updated assignments and names that were newly added to ``main``.
    """
    from core.skills.assignments import assign_skill_to_agents

    names = skill_names if skill_names is not None else bundled_skill_names()
    if not names:
        return dict(assignments or {}), []

    out = {k: list(v) for k, v in (assignments or {}).items()}
    before = set(out.get("main", []))
    for name in names:
        out = assign_skill_to_agents(out, name, ["main"])
    added = [n for n in names if n not in before and n in out.get("main", [])]
    return out, added


def seed_bundled_skills(skills_dir: Path, *, overwrite: bool = False) -> list[str]:
    """Copy packaged bundled skills into ``<profile>/data/skills/`` as flat ``{name}.md``.

    Returns names of skills that were installed.
    """
    from core.hub.normalize import parse_skill_file, write_flat_skill
    from core.hub.slash_registry import rebuild_slash_registry

    root = bundled_skills_root()
    if not root.is_dir():
        return []

    dest_dir = Path(skills_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        parsed = parse_skill_file(skill_md)
        if not parsed:
            continue
        name = parsed.get("name") or entry.name
        flat = dest_dir / f"{name}.md"
        if flat.exists() and not overwrite:
            continue
        write_flat_skill(flat, parsed)
        installed.append(name)

    if installed:
        try:
            rebuild_slash_registry(dest_dir)
        except Exception:
            pass

    return installed