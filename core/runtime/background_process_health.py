"""Health checks for background project processes (alive + log scan)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.runtime.port_verify import PortCheckResult, format_port_checks

_MAX_LOG_BYTES = 48_000
_MAX_LOG_LINES = 80
_MAX_ERROR_SNIPPETS = 6
_SNIPPET_MAX_CHARS = 400

# Strong signals — avoid bare "error" to limit false positives.
_ERROR_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\)", re.I),
    re.compile(r"^(?:ERROR|Error:|FATAL|CRITICAL)\b", re.M),
    re.compile(
        r"\b(ModuleNotFoundError|ImportError|SyntaxError|NameError|"
        r"FileNotFoundError|AttributeError|TypeError|ValueError|RuntimeError)\b"
    ),
    re.compile(r"\b(EADDRINUSE|Address already in use)\b", re.I),
    re.compile(r"npm ERR!", re.I),
    re.compile(r"\bnpm error\b", re.I),
    re.compile(r"\bpnpm ERR!", re.I),
    re.compile(r"\byarn run\b.*\berror\b", re.I),
    re.compile(r"ELIFECYCLE", re.I),
    re.compile(r"failed to compile", re.I),
    re.compile(r"Cannot find module", re.I),
    re.compile(r"exited with (?:code|status) [1-9]", re.I),
    re.compile(r"^AssertionError\b", re.M),
)

_READY_HINTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(listening on|Uvicorn running|Application startup complete)\b", re.I),
    re.compile(r"\b(ready on|compiled successfully|Local:\s*http)\b", re.I),
    re.compile(r"\b(Started server process|Watching for file changes)\b", re.I),
)


@dataclass(slots=True)
class ProcessHealthReport:
    process_id: str = ""
    label: str = ""
    pid: int = 0
    log_path: str = ""
    running: bool = False
    exit_code: int | None = None
    status: str = "not_found"  # healthy | crashed | error_in_log | starting | exited | not_found
    error_snippets: list[str] = field(default_factory=list)
    log_tail: str = ""
    recommendation: str = ""
    port_checks: list[PortCheckResult] = field(default_factory=list)
    expected_ports: list[int] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.status == "healthy"

    def format_text(self) -> str:
        if self.status == "not_found":
            return "No matching background process found."

        lines = [
            f"Background process health: {self.status.upper()}",
            f"- id: {self.process_id}",
            f"- label: {self.label}",
            f"- pid: {self.pid}",
            f"- running: {self.running}",
        ]
        if self.exit_code is not None:
            lines.append(f"- exit_code: {self.exit_code}")
        if self.log_path:
            lines.append(f"- log: {self.log_path}")
        if self.error_snippets:
            lines.append("- errors:")
            for snippet in self.error_snippets:
                lines.append(f"  · {snippet}")
        if self.log_tail:
            lines.append("- log tail:")
            for line in self.log_tail.splitlines()[-12:]:
                lines.append(f"  {line}")
        if self.expected_ports:
            lines.append(f"- expected_ports: {', '.join(str(p) for p in self.expected_ports)}")
        if self.port_checks:
            lines.append("- port listeners:")
            lines.extend(format_port_checks(self.port_checks))
        if self.recommendation:
            lines.append(f"- action: {self.recommendation}")
        return "\n".join(lines)


def tail_log_file(path: str | Path, *, max_bytes: int = _MAX_LOG_BYTES, max_lines: int = _MAX_LOG_LINES) -> str:
    log_path = Path(path)
    if not log_path.is_file():
        return ""
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            raw = handle.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)


def scan_log_for_errors(log_text: str) -> list[str]:
    if not (log_text or "").strip():
        return []

    snippets: list[str] = []
    seen: set[str] = set()

    def _add(snippet: str) -> None:
        cleaned = " ".join(snippet.split())
        if len(cleaned) > _SNIPPET_MAX_CHARS:
            cleaned = cleaned[: _SNIPPET_MAX_CHARS - 1] + "…"
        key = cleaned[:120]
        if key and key not in seen:
            seen.add(key)
            snippets.append(cleaned)

    lines = log_text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in _ERROR_LINE_PATTERNS:
            if pattern.search(stripped):
                if "Traceback" in stripped and idx + 1 < len(lines):
                    block = "\n".join(lines[idx : min(idx + 8, len(lines))])
                    _add(block)
                else:
                    _add(stripped)
                break

    return snippets[:_MAX_ERROR_SNIPPETS]


def log_shows_ready(log_text: str) -> bool:
    if not log_text.strip():
        return False
    return any(pattern.search(log_text) for pattern in _READY_HINTS)


def log_shows_port_in_use(log_text: str) -> bool:
    if not log_text.strip():
        return False
    return bool(re.search(r"\b(EADDRINUSE|Address already in use)\b", log_text, re.I))


def _port_conflict_recommendation(error_snippets: list[str]) -> str:
    from core.platform_compat import port_check_hint

    port_match = re.search(r":(\d{2,5})\b", " ".join(error_snippets))
    port = port_match.group(1) if port_match else ""
    hint = port_check_hint(int(port)) if port.isdigit() else "lsof -i :PORT"
    return (
        "Port is already in use (EADDRINUSE). Call restart_background_process with the "
        f"**same** command/port after fixing the issue, or stop_background_process first "
        f"({hint}). Do not switch to another port."
    )


def _wrong_process_recommendation(ports: list[int]) -> str:
    port_text = ", ".join(str(p) for p in ports) if ports else "expected"
    return (
        f"Wrong or foreign process on port(s) {port_text}. "
        "Call restart_background_process with the same command (same port) — "
        "it stops foreign listeners, frees the port, and starts again."
    )


def _no_listener_recommendation(ports: list[int]) -> str:
    port_text = ", ".join(str(p) for p in ports)
    return (
        f"Process is running but port(s) {port_text} are not listening yet. "
        "Wait and call check_background_process again. If still empty, read the log "
        "and restart_background_process with the same command."
    )


def apply_port_checks(
    report: ProcessHealthReport,
    *,
    port_checks: list[PortCheckResult],
    expected_ports: list[int],
) -> ProcessHealthReport:
    """Merge port listener verification into an existing health report."""
    report.port_checks = port_checks
    report.expected_ports = expected_ports
    if not expected_ports or not port_checks:
        return report

    foreign = [c.port for c in port_checks if c.issue == "foreign_listener"]
    missing = [c.port for c in port_checks if c.issue == "no_listener"]

    if foreign and report.status not in ("crashed", "exited", "port_in_use"):
        report.status = "wrong_process_on_port"
        report.recommendation = _wrong_process_recommendation(foreign)
    elif (
        missing
        and report.running
        and report.status == "healthy"
        and not log_shows_ready(report.log_tail)
    ):
        report.status = "port_not_listening"
        report.recommendation = _no_listener_recommendation(missing)

    return report


def build_health_report(
    *,
    process_id: str,
    label: str,
    pid: int,
    log_path: str,
    running: bool,
    exit_code: int | None,
    log_tail: str,
) -> ProcessHealthReport:
    error_snippets = scan_log_for_errors(log_tail)
    port_conflict = log_shows_port_in_use(log_tail) or any(
        re.search(r"\b(EADDRINUSE|Address already in use)\b", s, re.I)
        for s in error_snippets
    )

    if not running:
        if port_conflict:
            status = "port_in_use"
            recommendation = _port_conflict_recommendation(error_snippets)
        elif exit_code == 0 and not error_snippets:
            status = "exited"
            recommendation = (
                "Process exited with code 0 (normal for one-shot commands). "
                "For dev servers the command must keep running — use a long-lived "
                "entry (e.g. `npm run dev`, `uvicorn …`) or run one-shots via "
                "run_terminal_command."
            )
        else:
            status = "crashed"
            recommendation = (
                "Process is not running. Read the log tail, fix the root cause in code or "
                "config, then restart with start_background_process and check again."
            )
    elif error_snippets:
        status = "port_in_use" if port_conflict else "error_in_log"
        recommendation = (
            _port_conflict_recommendation(error_snippets)
            if port_conflict
            else (
                "Errors found in the process log. Fix the issue, restart the process, and "
                "call check_background_process until status is healthy."
            )
        )
    elif running and not log_shows_ready(log_tail) and len(log_tail.strip()) < 40:
        status = "starting"
        recommendation = (
            "Process is alive but still starting (log is short). Wait a few seconds and "
            "call check_background_process again with a longer wait_seconds."
        )
    else:
        status = "healthy"
        recommendation = (
            "Process looks healthy. Optionally hit the HTTP endpoint or run a smoke test."
        )

    return ProcessHealthReport(
        process_id=process_id,
        label=label,
        pid=pid,
        log_path=log_path,
        running=running,
        exit_code=exit_code,
        status=status,
        error_snippets=error_snippets,
        log_tail=log_tail,
        recommendation=recommendation,
    )