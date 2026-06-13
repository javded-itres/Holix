"""Prometheus text exposition for gateway metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.monitoring.metrics import MetricsCollector


def format_prometheus(metrics: MetricsCollector) -> str:
    lines: list[str] = []
    summary = metrics.get_summary()
    for name, value in summary.items():
        if isinstance(value, (int, float)):
            safe = str(name).replace("-", "_")
            lines.append(f"holix_{safe} {value}")
    for name, count in metrics.counters.items():
        safe = str(name).replace("-", "_").replace(" ", "_")
        lines.append(f'holix_{safe}_total {count}')
    if not lines:
        lines.append("holix_up 1")
    return "\n".join(lines) + "\n"