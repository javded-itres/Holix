"""Persisted logging preferences (debug mode, level)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Self

from core.logging.paths import logging_state_path


@dataclass(slots=True)
class LoggingState:
    debug_enabled: bool = False
    level: str = "INFO"

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            debug_enabled=bool(data.get("debug_enabled", False)),
            level=str(data.get("level", "INFO")).upper(),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def load_logging_state() -> LoggingState:
    path = logging_state_path()
    if not path.exists():
        return LoggingState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LoggingState.from_dict(data if isinstance(data, dict) else {})
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return LoggingState()


def save_logging_state(state: LoggingState) -> None:
    path = logging_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")