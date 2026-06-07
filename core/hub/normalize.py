"""Parse and normalize AgentSkills / OpenClaw / Hermes SKILL.md for Helix."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_SKIP_FILENAMES = frozenset({"skill-card.md", "skill_card.md"})
_ECO_METADATA_KEYS = ("openclaw", "clawdbot", "hermes", "claude")


def is_skill_markdown(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    if path.name.lower() in _SKIP_FILENAMES:
        return False
    if path.name == "SKILL.md":
        return True
    return path.parent.name != path.stem  # flat *.md in skills root


def discover_skill_files(root: Path) -> list[Path]:
    """Find loadable skill markdown under a directory tree."""
    if not root.exists():
        return []
    found: list[Path] = []
    seen: set[Path] = set()
    for path in root.rglob("SKILL.md"):
        if path.name.lower() in _SKIP_FILENAMES:
            continue
        if path not in seen:
            found.append(path)
            seen.add(path)
    for path in root.glob("*.md"):
        if path.name.lower() in _SKIP_FILENAMES:
            continue
        if path not in seen:
            found.append(path)
            seen.add(path)
    return sorted(found)


def parse_skill_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(metadata, dict):
        return None

    body = parts[2].strip()
    bundle_dir = path.parent
    body = body.replace("{baseDir}", str(bundle_dir))

    name = metadata.get("name") or path.parent.name if path.name == "SKILL.md" else path.stem
    name = _slugify(str(name))

    meta = _normalize_metadata(metadata)
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    return {
        **{k: v for k, v in meta.items() if k not in ("metadata",)},
        "name": name,
        "description": str(meta.get("description") or "").strip(),
        "tags": tags if isinstance(tags, list) else [],
        "content": body,
        "filepath": str(path),
        "bundle_dir": str(bundle_dir),
    }


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out = dict(metadata)
    raw_meta = out.pop("metadata", None)
    external: dict[str, Any] = {}
    if isinstance(raw_meta, dict):
        for key in _ECO_METADATA_KEYS:
            if key in raw_meta:
                external[key] = raw_meta[key]
        # keep other neutral metadata keys
        for k, v in raw_meta.items():
            if k not in _ECO_METADATA_KEYS:
                external[k] = v
    if external:
        out["_external_metadata"] = external
    return out


def slugify_skill_name(name: str) -> str:
    """Normalize a skill id (``test_skill`` → ``test-skill``)."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "skill"


def _slugify(name: str) -> str:
    return slugify_skill_name(name)


def write_flat_skill(dest: Path, skill: dict[str, Any]) -> Path:
    """Write Helix flat {name}.md from parsed skill dict."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in skill.items() if k not in ("content", "filepath", "bundle_dir")}
    with dest.open("w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.dump(meta, default_flow_style=False, allow_unicode=True))
        f.write("---\n\n")
        f.write(skill.get("content", ""))
    return dest