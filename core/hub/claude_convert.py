"""Convert Claude Code plugin commands/*.md into AgentSkills SKILL.md."""

from __future__ import annotations

from pathlib import Path

import yaml

from core.hub.normalize import _slugify


def convert_command_file(path: Path, *, plugin_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    description = f"Claude plugin command from {plugin_name}"
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                meta = {}
            if isinstance(meta, dict):
                description = str(meta.get("description") or description)
            body = parts[2].strip()

    name = _slugify(path.stem)
    if plugin_name:
        name = f"{_slugify(plugin_name)}-{name}"

    front = {
        "name": name,
        "description": description[:500],
        "tags": ["claude-plugin", plugin_name],
        "_claude_command": path.name,
        "user-invocable": True,
    }
    return (
        "---\n"
        + yaml.dump(front, default_flow_style=False, allow_unicode=True)
        + "---\n\n"
        + body
        + "\n"
    )