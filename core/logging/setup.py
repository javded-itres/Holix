"""Configure Python logging for Helix processes."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from cli.core import LOGS_DIR

from config import settings
from core.logging.paths import subagent_log, system_log
from core.logging.state import LoggingState, load_logging_state, save_logging_state

_CONFIGURED = False


def is_debug_enabled() -> bool:
    return load_logging_state().debug_enabled or settings.log_debug_enabled


def set_debug_enabled(enabled: bool, *, persist: bool = True) -> LoggingState:
    state = load_logging_state()
    state.debug_enabled = enabled
    if persist:
        save_logging_state(state)
    _apply_root_level(state)
    return state


def _level_from_state(state: LoggingState) -> int:
    if is_debug_enabled():
        return logging.DEBUG
    return getattr(logging, state.level.upper(), logging.INFO)


def _apply_root_level(state: LoggingState) -> None:
    logging.getLogger("helix").setLevel(_level_from_state(state))
    logging.getLogger().setLevel(_level_from_state(state))


def configure_helix_logging(*, force: bool = False) -> None:
    """Install rotating file handlers under HELIX_HOME/logs (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    state = load_logging_state()
    if settings.log_debug_enabled and not state.debug_enabled:
        state.debug_enabled = True
        save_logging_state(state)

    level = _level_from_state(state)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Avoid duplicate handlers on reconfigure
    helix_handler_ids = {id(h) for h in root.handlers}

    system_handler = RotatingFileHandler(
        system_log(),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    system_handler.setFormatter(formatter)
    system_handler.setLevel(level)
    if id(system_handler) not in helix_handler_ids:
        root.addHandler(system_handler)

    subagent_logger = logging.getLogger("core.subagents")
    subagent_logger.setLevel(level)
    sub_handler = RotatingFileHandler(
        subagent_log(),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    sub_handler.setFormatter(formatter)
    sub_handler.setLevel(level)
    if not subagent_logger.handlers:
        subagent_logger.addHandler(sub_handler)
    subagent_logger.propagate = True

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True