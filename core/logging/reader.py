"""Read and filter Helix log files for ``helix logs``."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.logging.paths import LogSource, files_for_source

_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

_PLAIN_LEVEL_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?:\[(?P<logger>[^\]]+)\]\s+)?"
    r"(?P<message>.*)$"
)


@dataclass(slots=True)
class LogEntry:
    source: str
    level: str
    timestamp: str
    message: str
    raw_line: str
    path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def level_rank(self) -> int:
        return _LEVEL_ORDER.get(self.level.upper(), 20)


def _infer_source(path: Path) -> str:
    name = path.name.lower()
    if "gateway" in str(path):
        return LogSource.GATEWAY.value
    if "subagent" in name:
        return LogSource.SUBAGENT.value
    if "runs.log" in name or "cron" in str(path):
        return LogSource.CRON.value
    if "agent" in name:
        return LogSource.AGENT.value
    return LogSource.SYSTEM.value


def _parse_json_line(line: str, path: Path, source: str) -> LogEntry | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return LogEntry(
        source=source,
        level=str(data.get("level", "INFO")),
        timestamp=str(data.get("timestamp", "")),
        message=str(data.get("message", "")),
        raw_line=line,
        path=str(path),
        extra={k: v for k, v in data.items() if k not in ("level", "timestamp", "message")},
    )


def _parse_plain_line(line: str, path: Path, source: str) -> LogEntry:
    m = _PLAIN_LEVEL_RE.match(line)
    if m:
        return LogEntry(
            source=source,
            level=m.group("level"),
            timestamp=m.group("ts"),
            message=m.group("message"),
            raw_line=line,
            path=str(path),
            extra={"logger": m.group("logger") or ""},
        )
    if line.startswith("[") and "]" in line[:30]:
        ts_end = line.find("]")
        ts = line[1:ts_end]
        rest = line[ts_end + 1 :].strip()
        return LogEntry(
            source=source,
            level="INFO",
            timestamp=ts,
            message=rest,
            raw_line=line,
            path=str(path),
        )
    return LogEntry(
        source=source,
        level="INFO",
        timestamp="",
        message=line,
        raw_line=line,
        path=str(path),
    )


def parse_log_line(line: str, path: Path) -> LogEntry | None:
    stripped = line.rstrip("\n")
    if not stripped:
        return None
    source = _infer_source(path)
    if stripped.startswith("{") and stripped.endswith("}"):
        entry = _parse_json_line(stripped, path, source)
        if entry:
            return entry
    return _parse_plain_line(stripped, path, source)


def _min_level_rank(level_filter: str | None) -> int:
    if not level_filter:
        return 0
    return _LEVEL_ORDER.get(level_filter.upper(), 0)


def _entry_matches(entry: LogEntry, *, level_filter: str | None, grep: str | None) -> bool:
    if level_filter and entry.level_rank < _min_level_rank(level_filter):
        return False
    if grep and grep.lower() not in entry.raw_line.lower():
        return False
    return True


def read_log_entries(
    *,
    source: LogSource = LogSource.ALL,
    profile: str = "default",
    lines: int = 100,
    level: str | None = None,
    grep: str | None = None,
    include_debug: bool = False,
) -> list[LogEntry]:
    paths = files_for_source(source, profile)
    if not include_debug:
        paths = [p for p in paths if "debug" not in p.name.lower()]

    entries: list[LogEntry] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in content:
            entry = parse_log_line(line, path)
            if entry and _entry_matches(entry, level_filter=level, grep=grep):
                entries.append(entry)

    entries.sort(key=lambda e: e.timestamp or e.raw_line)
    if lines > 0:
        return entries[-lines:]
    return entries


def tail_log_entries(
    *,
    source: LogSource = LogSource.ALL,
    profile: str = "default",
    lines: int = 50,
    level: str | None = None,
    grep: str | None = None,
    follow: bool = False,
    poll_interval: float = 0.5,
) -> Iterator[LogEntry]:
    """Yield log entries; when follow=True, poll for new lines."""
    seen: set[tuple[str, str]] = set()
    paths = files_for_source(source, profile)

    def _poll() -> list[LogEntry]:
        out: list[LogEntry] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in content:
                key = (str(path), line)
                if key in seen:
                    continue
                entry = parse_log_line(line, path)
                if entry and _entry_matches(entry, level_filter=level, grep=grep):
                    seen.add(key)
                    out.append(entry)
        return out

    initial = read_log_entries(
        source=source,
        profile=profile,
        lines=lines,
        level=level,
        grep=grep,
    )
    for entry in initial:
        seen.add((entry.path, entry.raw_line))
        yield entry

    if not follow:
        return

    while True:
        for entry in _poll():
            yield entry
        time.sleep(poll_interval)


def format_entry(entry: LogEntry, *, verbose: bool = False) -> str:
    ts = entry.timestamp[:19] if entry.timestamp else "—"
    lvl = entry.level.upper().ljust(5)[:5]
    src = entry.source[:8].ljust(8)
    base = f"{ts} {lvl} {src} {entry.message}"
    if verbose and entry.extra:
        extra = " ".join(f"{k}={v}" for k, v in entry.extra.items() if v)
        if extra:
            return f"{base}  ({extra})"
    return base