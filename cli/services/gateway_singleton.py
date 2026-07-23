"""Ensure at most one Holix gateway process runs on the host."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from cli.services.gateway_state import is_process_alive, list_running_states


@dataclass(frozen=True)
class GatewayConflict:
    profile: str
    pid: int
    host: str | None = None
    port: int | None = None
    source: str = "state"

    def describe(self) -> str:
        loc = ""
        if self.host is not None and self.port is not None:
            loc = f" http://{self.host}:{self.port}"
        return f"profile='{self.profile}' pid={self.pid}{loc} ({self.source})"


def find_all_gateway_worker_entries() -> list[tuple[int, str | None]]:
    """Return (pid, profile) for live ``gateway_worker`` processes."""
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return []

    if proc.returncode != 0:
        return []

    out: list[tuple[int, str | None]] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if "gateway_worker" not in stripped:
            continue
        match = re.match(r"^(\d+)\s+(.*)$", stripped)
        if not match:
            continue
        pid = int(match.group(1))
        cmd = match.group(2)
        profile_match = re.search(r"--profile\s+(\S+)", cmd)
        profile = profile_match.group(1) if profile_match else None
        if is_process_alive(pid):
            out.append((pid, profile))
    return out


def list_conflicting_gateways(
    *,
    exclude_profile: str | None = None,
    exclude_pid: int | None = None,
) -> list[GatewayConflict]:
    """Gateways that would conflict with starting a new process."""
    conflicts: list[GatewayConflict] = []
    seen_pids: set[int] = set()

    for state in list_running_states():
        if exclude_pid is not None and state.pid == exclude_pid:
            continue
        if exclude_profile is not None and state.profile == exclude_profile:
            continue
        if not is_process_alive(state.pid):
            continue
        seen_pids.add(state.pid)
        conflicts.append(
            GatewayConflict(
                profile=state.profile,
                pid=state.pid,
                host=state.host,
                port=state.port,
                source="state",
            )
        )

    for pid, profile in find_all_gateway_worker_entries():
        if exclude_pid is not None and pid == exclude_pid:
            continue
        if pid in seen_pids:
            continue
        if exclude_profile is not None and profile == exclude_profile:
            continue
        conflicts.append(
            GatewayConflict(
                profile=profile or "unknown",
                pid=pid,
                source="process",
            )
        )
    return conflicts


def assert_can_start_gateway(
    profile: str,
    *,
    exclude_pid: int | None = None,
) -> None:
    """Raise ``RuntimeError`` if any gateway is already running on this host.

    At most one gateway process is allowed (any profile). Callers that restart
    must stop the existing process first. ``exclude_pid`` skips the current
    worker (used at process entry).
    """
    del profile  # signature kept for call-site clarity
    conflicts = list_conflicting_gateways(exclude_profile=None, exclude_pid=exclude_pid)
    if not conflicts:
        return
    details = "; ".join(c.describe() for c in conflicts)
    raise RuntimeError(
        "Only one Holix gateway may run at a time. "
        f"Already running: {details}. Stop it first (gateway stop)."
    )


def other_gateway_summaries(profile: str) -> list[dict]:
    """JSON-friendly list of other gateways (for status payloads)."""
    return [
        {
            "profile": c.profile,
            "pid": c.pid,
            "host": c.host,
            "port": c.port,
            "url": f"http://{c.host}:{c.port}" if c.host is not None and c.port is not None else None,
            "source": c.source,
        }
        for c in list_conflicting_gateways(exclude_profile=profile)
    ]
