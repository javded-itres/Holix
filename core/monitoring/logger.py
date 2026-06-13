import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.logging.events import append_agent_event
from core.logging.setup import configure_holix_logging


class StructuredLogger:
    """Structured JSON logger for agent/sub-agent observability."""

    def __init__(self, name: str = "holix.agent"):
        configure_holix_logging()
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            self.logger.addHandler(console_handler)

    def info(self, message: str, **kwargs):
        self.logger.info(message)
        append_agent_event("INFO", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.logger.error(message)
        append_agent_event("ERROR", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self.logger.warning(message)
        append_agent_event("WARNING", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self.logger.debug(message)
        append_agent_event("DEBUG", message, **kwargs)


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "pathname", "process", "processName",
                    "relativeCreated", "thread", "threadName",
                ]:
                    log_data[key] = value

        return json.dumps(log_data)


logger = StructuredLogger()


def create_logger_subscriber(structured_logger: StructuredLogger | None = None) -> Callable[[Any], None]:
    """Forward AgentEvents to structured JSONL logs."""
    log = structured_logger or logger

    def handler(event: Any) -> None:
        try:
            from core.agent_events import (
                ContextCompressedEvent,
                ContextWarningEvent,
                ErrorEvent,
                FinalResponseEvent,
                SkillCreatedEvent,
                ThinkingEvent,
                ToolCallResultEvent,
                ToolCallStartEvent,
            )
            from core.monitoring.event_fields import correlation_fields

            ctx = correlation_fields(event)

            if isinstance(event, ToolCallStartEvent):
                log.info(
                    f"Tool call started: {event.tool_name}",
                    tool=event.tool_name,
                    tool_id=event.tool_id,
                    **ctx,
                )
            elif isinstance(event, ToolCallResultEvent):
                log.info(
                    f"Tool call completed: {event.tool_name}",
                    tool=event.tool_name,
                    duration_ms=event.duration_ms,
                    **ctx,
                )
            elif isinstance(event, FinalResponseEvent):
                log.info(
                    "Agent produced final response",
                    steps=event.steps_taken,
                    **ctx,
                )
            elif isinstance(event, ErrorEvent):
                log.error(
                    f"Agent error: {event.error}",
                    error_type=event.error_type,
                    **ctx,
                )
            elif isinstance(event, SkillCreatedEvent):
                log.info(
                    f"New skill created: {event.skill_name}",
                    skill=event.skill_name,
                    filepath=event.filepath,
                    **ctx,
                )
            elif isinstance(event, ContextCompressedEvent):
                log.info(
                    f"Context compressed: {event.original_tokens} → {event.compressed_tokens} tokens",
                    original_tokens=event.original_tokens,
                    compressed_tokens=event.compressed_tokens,
                    messages_before=event.messages_before,
                    messages_after=event.messages_after,
                    **ctx,
                )
            elif isinstance(event, ContextWarningEvent):
                log.warning(
                    f"Context usage at {event.usage_percent:.0f}% ({event.level})",
                    usage_percent=event.usage_percent,
                    tokens_used=event.tokens_used,
                    tokens_total=event.tokens_total,
                    level=event.level,
                    **ctx,
                )
            elif isinstance(event, ThinkingEvent) and "Initializing" in event.message:
                log.info(event.message, **ctx)

        except Exception:
            pass

    return handler