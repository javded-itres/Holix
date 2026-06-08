"""Persisted state for per-profile Helix gateway instances."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Self

from core.platform_compat import is_process_alive, resolve_helix_home


def gateway_dir(profile: str = "default") -> Path:
    return (resolve_helix_home() / "profiles" / profile / "gateway").resolve()


def state_path(profile: str = "default") -> Path:
    return gateway_dir(profile) / "state.json"


def log_path(profile: str = "default") -> Path:
    return gateway_dir(profile) / "gateway.log"


# Legacy aliases (default profile) — kept for older imports/tests.
GATEWAY_DIR = gateway_dir("default")
STATE_PATH = state_path("default")
LOG_PATH = log_path("default")


@dataclass(slots=True)
class GatewayState:
    pid: int
    host: str
    port: int
    profile: str
    reload: bool
    started_at: str
    log_file: str
    telegram_pid: Optional[int] = None
    docs_pid: Optional[int] = None
    docs_host: Optional[str] = None
    docs_port: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            pid=int(data["pid"]),
            host=str(data["host"]),
            port=int(data["port"]),
            profile=str(data["profile"]),
            reload=bool(data.get("reload", False)),
            started_at=str(data["started_at"]),
            log_file=str(data["log_file"]),
            telegram_pid=(
                int(data["telegram_pid"]) if data.get("telegram_pid") is not None else None
            ),
            docs_pid=int(data["docs_pid"]) if data.get("docs_pid") is not None else None,
            docs_host=str(data["docs_host"]) if data.get("docs_host") is not None else None,
            docs_port=int(data["docs_port"]) if data.get("docs_port") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_gateway_dir(profile: str = "default") -> Path:
    path = gateway_dir(profile)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_state_path() -> Path:
    return resolve_helix_home() / "gateway" / "state.json"


def _read_state_file(path: Path) -> Optional[GatewayState]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GatewayState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _collect_states(profile: str) -> list[GatewayState]:
    """Gather profile and legacy state files for the same profile name."""
    states: list[GatewayState] = []
    seen_pids: set[int] = set()

    for candidate in (_read_state_file(state_path(profile)), _read_state_file(_legacy_state_path())):
        if candidate is None or candidate.profile != profile or candidate.pid in seen_pids:
            continue
        states.append(candidate)
        seen_pids.add(candidate.pid)

    return states


def _migrate_state_to_profile(state: GatewayState) -> None:
    """Persist canonical per-profile state and remove matching legacy file."""
    ensure_gateway_dir(state.profile)
    state_path(state.profile).write_text(
        json.dumps(state.to_dict(), indent=2),
        encoding="utf-8",
    )
    legacy = _legacy_state_path()
    if not legacy.is_file():
        return
    legacy_state = _read_state_file(legacy)
    if legacy_state is not None and legacy_state.profile == state.profile:
        legacy.unlink()


def load_state(profile: str = "default") -> Optional[GatewayState]:
    states = _collect_states(profile)
    if not states:
        return None

    alive = [s for s in states if is_process_alive(s.pid)]
    if alive:
        best = max(alive, key=lambda s: s.started_at)
        _migrate_state_to_profile(best)
        return best

    profile_state = _read_state_file(state_path(profile))
    if profile_state is not None and profile_state.profile == profile:
        return profile_state

    legacy_state = _read_state_file(_legacy_state_path())
    if legacy_state is not None and legacy_state.profile == profile:
        return legacy_state

    return states[0]


def save_state(state: GatewayState) -> None:
    _migrate_state_to_profile(state)


def clear_state(profile: str = "default") -> None:
    path = state_path(profile)
    if path.exists():
        path.unlink()

    legacy = _legacy_state_path()
    if legacy.is_file():
        legacy_state = _read_state_file(legacy)
        if legacy_state is not None and legacy_state.profile == profile:
            legacy.unlink()


def _with_state(profile: str, **updates: Any) -> None:
    state = load_state(profile)
    if state is None:
        return
    data = state.to_dict()
    data.update(updates)
    save_state(GatewayState.from_dict(data))


def update_telegram_pid(pid: int, *, profile: str = "default") -> None:
    _with_state(profile, telegram_pid=pid)


def update_docs_info(*, pid: int, host: str, port: int, profile: str = "default") -> None:
    _with_state(profile, docs_pid=pid, docs_host=host, docs_port=port)


def new_state(
    *,
    pid: int,
    host: str,
    port: int,
    profile: str,
    reload: bool,
    telegram_pid: Optional[int] = None,
    docs_pid: Optional[int] = None,
    docs_host: Optional[str] = None,
    docs_port: Optional[int] = None,
) -> GatewayState:
    ensure_gateway_dir(profile)
    return GatewayState(
        pid=pid,
        host=host,
        port=port,
        profile=profile,
        reload=reload,
        started_at=datetime.now(timezone.utc).isoformat(),
        log_file=str(log_path(profile)),
        telegram_pid=telegram_pid,
        docs_pid=docs_pid,
        docs_host=docs_host,
        docs_port=docs_port,
    )


def docs_url(state: GatewayState) -> str | None:
    if state.docs_host is None or state.docs_port is None:
        return None
    bind = "127.0.0.1" if state.docs_host in ("0.0.0.0", "::") else state.docs_host
    return f"http://{bind}:{state.docs_port}/"


def health_url(state: GatewayState) -> str:
    bind = "127.0.0.1" if state.host in ("0.0.0.0", "::") else state.host
    return f"http://{bind}:{state.port}/health"


def list_running_states() -> list[GatewayState]:
    """Return alive gateway states across all profiles."""
    from cli.core import get_profile_manager

    out: list[GatewayState] = []
    manager = get_profile_manager()
    for name in manager.list_profiles():
        state = load_state(name)
        if state is not None and is_process_alive(state.pid):
            out.append(state)
    return out