"""Scan ``.holix/commands`` and ``$HOLIX_HOME/commands`` into a registry."""

from __future__ import annotations

import logging
from pathlib import Path

from core.commands.models import CustomCommand
from core.commands.parse import parse_command_file
from core.commands.paths import command_name_from_rel

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".holix",
        ".helix",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
    }
)
_MAX_DEPTH = 3


class CommandLoader:
    """Cached registry: project files override user files of the same name."""

    def __init__(self, *, project_dir: Path, user_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.user_dir = Path(user_dir)
        self._commands: dict[str, CustomCommand] = {}
        self._signature: tuple[tuple[str, int, int], ...] = ()

    def list_commands(self) -> list[CustomCommand]:
        self._refresh_if_stale()
        return sorted(self._commands.values(), key=lambda c: c.name)

    def get(self, name: str) -> CustomCommand | None:
        self._refresh_if_stale()
        key = (name or "").strip().lower().lstrip("/")
        return self._commands.get(key)

    def reload(self) -> None:
        self._signature = ()
        self._refresh_if_stale()

    def _refresh_if_stale(self) -> None:
        signature = self._scan_signature()
        if signature == self._signature:
            return
        commands: dict[str, CustomCommand] = {}
        self._load_tree(self.user_dir, source="user", into=commands)
        self._load_tree(self.project_dir, source="project", into=commands)
        self._commands = commands
        self._signature = signature

    def _scan_signature(self) -> tuple[tuple[str, int, int], ...]:
        found: list[tuple[str, int, int]] = []
        for directory in (self.user_dir, self.project_dir):
            if not directory.is_dir():
                continue
            for path in _iter_markdown(directory):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found.append((str(path), int(stat.st_mtime_ns), int(stat.st_size)))
        found.sort()
        return tuple(found)

    def _load_tree(self, root: Path, *, source: str, into: dict[str, CustomCommand]) -> None:
        if not root.is_dir():
            return
        for path in _iter_markdown(root):
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            name = command_name_from_rel(rel)
            if not name:
                continue
            parsed = parse_command_file(path, name=name, source=source)
            if parsed is None or not parsed.body:
                continue
            into[name] = parsed


def _iter_markdown(root: Path) -> list[Path]:
    out: list[Path] = []
    try:
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if len(rel.parts) - 1 > _MAX_DEPTH:
                continue
            if any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in rel.parts[:-1]):
                continue
            out.append(path)
    except OSError:
        logger.debug("custom commands scan failed under %s", root, exc_info=True)
    return out
