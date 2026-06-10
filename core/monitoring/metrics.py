import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional


class MetricsCollector:
    """Collect and track agent metrics."""

    def __init__(self):
        self.metrics: dict[str, list] = defaultdict(list)
        self.counters: dict[str, int] = defaultdict(int)
        self.timers: dict[str, float] = {}

    def increment(self, metric_name: str, value: int = 1):
        """Increment a counter metric.

        Args:
            metric_name: Name of the metric
            value: Amount to increment
        """
        self.counters[metric_name] += value

    def record(self, metric_name: str, value: float):
        """Record a metric value.

        Args:
            metric_name: Name of the metric
            value: Metric value
        """
        self.metrics[metric_name].append({
            "value": value,
            "timestamp": datetime.now().isoformat()
        })

    def start_timer(self, timer_name: str):
        """Start a timer.

        Args:
            timer_name: Name of the timer
        """
        self.timers[timer_name] = time.time()

    def stop_timer(self, timer_name: str) -> float:
        """Stop a timer and record the elapsed time.

        Args:
            timer_name: Name of the timer

        Returns:
            Elapsed time in seconds
        """
        if timer_name not in self.timers:
            return 0.0

        elapsed = time.time() - self.timers[timer_name]
        self.record(f"{timer_name}_duration", elapsed)
        del self.timers[timer_name]
        return elapsed

    def get_metrics(self) -> dict:
        """Get all collected metrics.

        Returns:
            Dictionary of metrics
        """
        return {
            "counters": dict(self.counters),
            "metrics": {k: v[-100:] for k, v in self.metrics.items()},  # Last 100 values
            "timestamp": datetime.now().isoformat()
        }

    def get_summary(self) -> dict:
        """Get metrics summary.

        Returns:
            Summary statistics
        """
        summary = {
            "total_requests": self.counters.get("requests", 0),
            "total_tool_calls": self.counters.get("tool_calls", 0),
            "total_errors": self.counters.get("errors", 0),
            "skills_created": self.counters.get("skills_created", 0),
            "context_compressions": self.counters.get("context_compressions", 0),
            "confirmation_denials": self.counters.get("confirmation_deny", 0),
            "plan_reviews": sum(
                v for k, v in self.counters.items() if k.startswith("plan_review.")
            ),
        }

        # Average response time
        if "request_duration" in self.metrics and self.metrics["request_duration"]:
            durations = [m["value"] for m in self.metrics["request_duration"]]
            summary["avg_response_time"] = sum(durations) / len(durations)
            summary["max_response_time"] = max(durations)
            summary["min_response_time"] = min(durations)

        return summary

    def reset(self):
        """Reset all metrics."""
        self.metrics.clear()
        self.counters.clear()
        self.timers.clear()


def format_metrics_message(summary: dict) -> str:
    """Human-readable metrics for Telegram, CLI, and shared slash commands."""
    lines = [
        "**Helix metrics**",
        "",
        f"• Requests: {summary.get('total_requests', 0)}",
        f"• Tool calls: {summary.get('total_tool_calls', 0)}",
        f"• Skills created: {summary.get('skills_created', 0)}",
        f"• Errors: {summary.get('total_errors', 0)}",
        f"• Context compressions: {summary.get('context_compressions', 0)}",
        f"• Confirmation denials: {summary.get('confirmation_denials', 0)}",
        f"• Plan reviews: {summary.get('plan_reviews', 0)}",
    ]
    if "avg_response_time" in summary:
        lines.append(f"• Avg response: {summary['avg_response_time']:.2f}s")
        lines.append(
            f"• Min / max: {summary.get('min_response_time', 0):.2f}s / "
            f"{summary.get('max_response_time', 0):.2f}s"
        )
    return "\n".join(lines)


# Global metrics instance
metrics = MetricsCollector()


def create_metrics_subscriber(collector: Optional["MetricsCollector"] = None) -> Callable[[Any], None]:
    """
    Returns an event handler that updates the given (or global) MetricsCollector
    based on AgentEvents.

    This turns the previously passive metrics into a real-time observer.
    """
    collector = collector or metrics
    start_times: dict[str, float] = {}  # per conversation or per step

    def handler(event: Any) -> None:
        try:
            from core.agent_events import (
                ContextCompressedEvent,
                ContextWarningEvent,
                ErrorEvent,
                FinalResponseEvent,
                SkillCreatedEvent,
                ToolCallResultEvent,
                ToolCallStartEvent,
            )
            from core.monitoring.event_fields import correlation_fields

            ctx = correlation_fields(event)
            if ctx.get("event_type"):
                collector.increment(f"events.{ctx['event_type']}")
            if ctx.get("run_id"):
                collector.increment("runs_with_correlation")

            if isinstance(event, ToolCallStartEvent):
                collector.increment("tool_calls")
                collector.increment(f"tool.{event.tool_name}")
                key = f"{event.conversation_id}:{event.tool_id or event.tool_name}"
                start_times[key] = time.time()

            elif isinstance(event, ToolCallResultEvent):
                key = f"{event.conversation_id}:{event.tool_id or event.tool_name}"
                if key in start_times:
                    duration = (time.time() - start_times.pop(key)) * 1000
                    collector.record("tool_execution_time", duration)

            elif isinstance(event, FinalResponseEvent):
                collector.increment("requests")

            elif isinstance(event, ErrorEvent):
                collector.increment("errors")

            elif isinstance(event, SkillCreatedEvent):
                collector.increment("skills_created")

            elif isinstance(event, ContextCompressedEvent):
                collector.increment("context_compressions")
                if event.original_tokens > 0:
                    ratio = event.compressed_tokens / event.original_tokens
                    collector.record("context_compression_ratio", ratio)

            elif isinstance(event, ContextWarningEvent):
                collector.record("context_usage_percent", event.usage_percent)

            else:
                from core.plan_review.review_events import PlanReviewResponseEvent
                from core.security.confirmation_events import ConfirmationResponseEvent

                if isinstance(event, ConfirmationResponseEvent):
                    collector.increment(f"confirmation.{event.choice}")
                    if event.choice == "deny":
                        collector.increment("confirmation_deny")
                elif isinstance(event, PlanReviewResponseEvent):
                    collector.increment(f"plan_review.{event.choice}")

        except Exception:
            # Never let metrics break the agent
            pass

    return handler
