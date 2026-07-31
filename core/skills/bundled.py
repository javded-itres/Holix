"""Ship default skills with Holix and seed them into new profiles."""

from __future__ import annotations

from pathlib import Path

_BUNDLED_ROOT = Path(__file__).resolve().parent / "bundled"

# Always (re)seed + assign on profile create/refresh — platform workflow skills.
# Frontmatter ``required: true`` / ``platform: true`` also forces overwrite on seed.
_REQUIRED_BUNDLED_FALLBACK = frozenset(
    {
        "holix-studio-frontend-backend",
    }
)


def bundled_skills_root() -> Path:
    return _BUNDLED_ROOT


def _skill_is_required(parsed: dict | None, *, entry_name: str) -> bool:
    if not parsed:
        return entry_name in _REQUIRED_BUNDLED_FALLBACK
    name = str(parsed.get("name") or entry_name).strip()
    if name in _REQUIRED_BUNDLED_FALLBACK:
        return True
    for key in ("required", "platform"):
        val = parsed.get(key)
        if val is True or str(val).strip().lower() in {"1", "true", "yes"}:
            return True
    tags = parsed.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if any(str(t).strip().lower() in {"required", "platform"} for t in tags):
        return True
    return False


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


def required_bundled_skill_names() -> list[str]:
    """Bundled skills that must exist on every profile and stay assigned to main."""
    from core.hub.normalize import parse_skill_file

    root = bundled_skills_root()
    if not root.is_dir():
        return sorted(_REQUIRED_BUNDLED_FALLBACK)
    names: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        parsed = parse_skill_file(skill_md)
        name = (parsed.get("name") if parsed else None) or entry.name
        if _skill_is_required(parsed, entry_name=entry.name):
            names.append(name)
    return names or sorted(_REQUIRED_BUNDLED_FALLBACK)


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
    # Required platform skills must always appear on main even if allowlist was empty.
    for name in required_bundled_skill_names():
        out = assign_skill_to_agents(out, name, ["main"])
    added = [n for n in names if n not in before and n in out.get("main", [])]
    for name in required_bundled_skill_names():
        if name not in before and name in out.get("main", []) and name not in added:
            added.append(name)
    return out, added


def seed_bundled_skills(skills_dir: Path, *, overwrite: bool = False) -> list[str]:
    """Copy packaged bundled skills into ``<profile>/data/skills/`` as flat ``{name}.md``.

    Skills marked ``required`` / ``platform`` are always rewritten so Studio
    workflow updates reach existing profiles on next create/seed.

    Returns names of skills that were installed or refreshed.
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
        force = overwrite or _skill_is_required(parsed, entry_name=entry.name)
        if flat.exists() and not force:
            continue
        write_flat_skill(flat, parsed)
        installed.append(name)

    if installed:
        try:
            rebuild_slash_registry(dest_dir)
        except Exception:
            pass

    return installed