"""Append structured JSONL event lines."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging.paths import agent_debug_log, agent_events_log, subagent_log
from core.logging.state import load_logging_state

logger = logging.getLogger(__name__)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def append_agent_event(
    level: str,
    message: str,
    *,
    category: str = "agent",
    **fields: Any,
) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level.upper(),
        "category": category,
        "message": message,
        **fields,
    }
    _append_jsonl(agent_events_log(), payload)
    if load_logging_state().debug_enabled or level.upper() == "DEBUG":
        _append_jsonl(agent_debug_log(), payload)


def log_subagent_event(
    level: str,
    message: str,
    *,
    subagent: str = "",
    **fields: Any,
) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level.upper(),
        "category": "subagent",
        "subagent": subagent,
        "message": message,
        **fields,
    }
    _append_jsonl(subagent_log(), payload)
    if load_logging_state().debug_enabled:
        _append_jsonl(agent_debug_log(), payload)
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn("[%s] %s", subagent or "subagent", message)