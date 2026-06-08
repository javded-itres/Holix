"""Persisted state for per-profile Helix gateway instances."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Self

from cli.core import PROFILES_DIR
from core.platform_compat import is_process_alive


def gateway_dir(profile: str = "default") -> Path:
    return (PROFILES_DIR / profile / "gateway").resolve()


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


def load_state(profile: str = "default") -> Optional[GatewayState]:
    path = state_path(profile)
    if not path.exists():
        return _load_legacy_state(profile)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GatewayState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _load_legacy_state(profile: str) -> Optional[GatewayState]:
    """Read pre-migration global gateway state when it matches the profile."""
    from cli.core import HELIX_HOME

    legacy = HELIX_HOME / "gateway" / "state.json"
    if not legacy.is_file():
        return None
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        if str(data.get("profile", "default")) != profile:
            return None
        return GatewayState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_state(state: GatewayState) -> None:
    ensure_gateway_dir(state.profile)
    state_path(state.profile).write_text(
        json.dumps(state.to_dict(), indent=2),
        encoding="utf-8",
    )


def clear_state(profile: str = "default") -> None:
    path = state_path(profile)
    if path.exists():
        path.unlink()


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