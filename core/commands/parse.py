"""Parse command markdown (optional YAML frontmatter) and expand arguments."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import yaml

from core.commands.models import CustomCommand
from core.tools.aliases import resolve_tool_name

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_MAX_POSITIONAL = 32


def parse_command_file(path: Path, *, name: str, source: str) -> CustomCommand | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta, body = split_frontmatter(text)
    description = str(meta.get("description") or "").strip()
    hint = str(meta.get("argument-hint") or meta.get("argument_hint") or "").strip()
    model_raw = meta.get("model")
    model = str(model_raw).strip() if model_raw not in (None, "", "null") else None
    tools = _normalize_tools(meta.get("allowed-tools") or meta.get("allowed_tools"))
    return CustomCommand(
        name=name,
        path=path,
        source=source,
        description=description,
        argument_hint=hint,
        allowed_tools=tuple(tools),
        model=model,
        body=body.strip(),
    )


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    raw = text or ""
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    try:
        loaded = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(loaded, dict):
        return {}, raw
    return loaded, raw[match.end() :]


def expand_arguments(template: str, args: str) -> str:
    """Substitute ``$ARGUMENTS``, ``$1``… and ``$$`` (escaped dollar)."""
    arguments = args or ""
    try:
        positional = shlex.split(arguments)
    except ValueError:
        positional = arguments.split()
    sentinel = "\x00DOLLAR\x00"
    text = (template or "").replace("$$", sentinel)
    text = text.replace("$ARGUMENTS", arguments)
    for index in range(_MAX_POSITIONAL, 0, -1):
        value = positional[index - 1] if index <= len(positional) else ""
        text = text.replace(f"${index}", value)
    return text.replace(sentinel, "$")


def _normalize_tools(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(item).strip() for item in raw if str(item).strip()]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        resolved = resolve_tool_name(item) or item
        key = resolved.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out
