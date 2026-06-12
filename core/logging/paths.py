"""Log file locations under HOLIX_HOME."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cli.core import HOLIX_HOME, LOGS_DIR

from core.cron.store import runs_log_path


class LogSource(StrEnum):
    ALL = "all"
    AGENT = "agent"
    GATEWAY = "gateway"
    CRON = "cron"
    SUBAGENT = "subagent"
    SYSTEM = "system"


def logging_state_path() -> Path:
    return LOGS_DIR / "logging.json"


def agent_events_log() -> Path:
    return LOGS_DIR / "agent.jsonl"


def agent_debug_log() -> Path:
    return LOGS_DIR / "agent.debug.jsonl"


def system_log() -> Path:
    return LOGS_DIR / "holix.log"


def subagent_log() -> Path:
    return LOGS_DIR / "subagent.jsonl"


def gateway_log() -> Path:
    return HOLIX_HOME / "gateway" / "gateway.log"


@dataclass(frozen=True, slots=True)
class LogFileInfo:
    source: LogSource
    path: Path
    label: str

    @property
    def size_bytes(self) -> int:
        if not self.path.exists():
            return 0
        return self.path.stat().st_size


def discover_log_files(profile: str = "default") -> list[LogFileInfo]:
    """Return known Holix log files (existing or expected paths)."""
    files = [
        LogFileInfo(LogSource.AGENT, agent_events_log(), "Agent events (JSONL)"),
        LogFileInfo(LogSource.AGENT, agent_debug_log(), "Agent debug (JSONL)"),
        LogFileInfo(LogSource.SYSTEM, system_log(), "Holix system log"),
        LogFileInfo(LogSource.SUBAGENT, subagent_log(), "Sub-agent events (JSONL)"),
        LogFileInfo(LogSource.GATEWAY, gateway_log(), "Gateway / uvicorn"),
        LogFileInfo(LogSource.CRON, runs_log_path(profile), f"Cron runs ({profile})"),
    ]
    hub_log = LOGS_DIR / "hub-autoupdate.log"
    if hub_log.exists():
        files.append(LogFileInfo(LogSource.SYSTEM, hub_log, "Hub autoupdate"))
    return files


def files_for_source(source: LogSource, profile: str = "default") -> list[Path]:
    if source == LogSource.ALL:
        return [f.path for f in discover_log_files(profile) if f.path.exists()]
    mapping = {
        LogSource.AGENT: [agent_events_log(), agent_debug_log()],
        LogSource.GATEWAY: [gateway_log()],
        LogSource.CRON: [runs_log_path(profile)],
        LogSource.SUBAGENT: [subagent_log()],
        LogSource.SYSTEM: [system_log(), LOGS_DIR / "hub-autoupdate.log"],
    }
    return [p for p in mapping.get(source, []) if p.exists()]