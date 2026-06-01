from datetime import datetime
from typing import Dict, List
from collections import defaultdict
import time


class MetricsCollector:
    """Collect and track agent metrics."""

    def __init__(self):
        self.metrics: Dict[str, List] = defaultdict(list)
        self.counters: Dict[str, int] = defaultdict(int)
        self.timers: Dict[str, float] = {}

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

    def get_metrics(self) -> Dict:
        """Get all collected metrics.

        Returns:
            Dictionary of metrics
        """
        return {
            "counters": dict(self.counters),
            "metrics": {k: v[-100:] for k, v in self.metrics.items()},  # Last 100 values
            "timestamp": datetime.now().isoformat()
        }

    def get_summary(self) -> Dict:
        """Get metrics summary.

        Returns:
            Summary statistics
        """
        summary = {
            "total_requests": self.counters.get("requests", 0),
            "total_tool_calls": self.counters.get("tool_calls", 0),
            "total_errors": self.counters.get("errors", 0),
            "skills_created": self.counters.get("skills_created", 0),
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


# Global metrics instance
metrics = MetricsCollector()
