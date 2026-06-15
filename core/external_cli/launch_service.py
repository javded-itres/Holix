"""Shared external CLI launch operations (TUI, REST API, agent tools)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.external_cli.assignment import (
    assign_cli_to_subagent,
    list_cli_assignment_rows,
    unassign_cli_subagent,
)
from core.external_cli.platform import ensure_launch_platform, launch_supported
from core.external_cli.registry import get_cli_spec, list_cli_specs
from core.external_cli.store import LaunchedSession


class LaunchServiceError(RuntimeError):
    """User-visible launch failure."""


def _resolve_binary(spec) -> str | None:
    from cli.launch.setup_wizard import _binary_installed

    return _binary_installed(spec)


def _load_profile_config(profile: str) -> Any:
    from cli.core import ProfileManager

    manager = ProfileManager()
    if not manager.profile_exists(profile):
        raise LaunchServiceError(f"Profile not found: {profile}")
    return manager.load_profile(profile)


def _session_dict(session: LaunchedSession) -> dict[str, Any]:
    return session.to_dict()


def _require_platform() -> None:
    if not launch_supported():
        raise LaunchServiceError("External CLI launch is available only on Linux and macOS.")
    ensure_launch_platform()


def list_clis(profile: str) -> list[dict[str, Any]]:
    rows = list_cli_assignment_rows(profile, resolve_binary=_resolve_binary)
    return [
        {
            "cli_id": row.cli_id,
            "display_name": row.display_name,
            "description": row.description,
            "enabled": row.enabled,
            "agent_slot": row.agent_slot,
            "model_slot": row.model_slot,
            "binary": row.binary,
            "assigned": row.assigned,
        }
        for row in rows
    ]


def list_sessions(profile: str) -> list[dict[str, Any]]:
    from cli.services.tmux_launcher import prune_dead_sessions

    return [_session_dict(s) for s in prune_dead_sessions(profile)]


def launch_external_cli(
    profile: str,
    cli_id: str,
    *,
    task: str = "",
    cwd: str | Path | None = None,
    model_slot: str | None = None,
    restart: bool = False,
) -> dict[str, Any]:
    """Start or restart an external CLI in tmux (always detached)."""
    _require_platform()
    spec = get_cli_spec(cli_id)
    if spec is None:
        known = ", ".join(s.cli_id for s in list_cli_specs())
        raise LaunchServiceError(f"Unknown CLI '{cli_id}'. Supported: {known}")

    config = _load_profile_config(profile)
    workdir = Path(cwd).expanduser() if cwd else None

    from cli.services.tmux_launcher import TmuxError, launch_cli_by_id, restart_cli_by_id

    launcher = restart_cli_by_id if restart else launch_cli_by_id
    try:
        session = launcher(
            profile=profile,
            cli_id=cli_id,
            profile_config=config,
            cwd=workdir,
            task=task.strip(),
            model_slot=model_slot,
        )
    except TmuxError as exc:
        raise LaunchServiceError(str(exc)) from exc
    return _session_dict(session)


def send_session_message(
    profile: str,
    session_ref: str,
    message: str,
    *,
    enter: bool = True,
) -> dict[str, Any]:
    _require_platform()
    from cli.services.tmux_launcher import (
        find_launched_session,
        send_text,
        tmux_session_alive,
    )

    from core.external_cli.store import ExternalCliStore

    found = find_launched_session(profile, session_ref)
    target = found.tmux_session if found else session_ref
    if not tmux_session_alive(target):
        raise LaunchServiceError(f"tmux session not found: {session_ref}")

    text = (message or "").strip()
    if not text:
        raise LaunchServiceError("message is required")

    window = found.window_index if found else 0
    send_text(target, text, window_index=window, enter=enter)
    if found:
        ExternalCliStore(profile).touch_session_output(found.session_id)
    return {
        "tmux_session": target,
        "window_index": window,
        "session_id": found.session_id if found else None,
    }


def capture_session_output(
    profile: str,
    session_ref: str,
    *,
    lines: int = 40,
) -> dict[str, Any]:
    _require_platform()
    from cli.services.tmux_launcher import (
        capture_pane,
        find_launched_session,
        tmux_session_alive,
    )

    from core.external_cli.store import ExternalCliStore

    found = find_launched_session(profile, session_ref)
    target = found.tmux_session if found else session_ref
    if not tmux_session_alive(target):
        raise LaunchServiceError(f"tmux session not found: {session_ref}")

    window = found.window_index if found else 0
    text = capture_pane(target, window_index=window, lines=max(1, lines))
    if found:
        ExternalCliStore(profile).touch_session_output(found.session_id)
    return {
        "tmux_session": target,
        "window_index": window,
        "session_id": found.session_id if found else None,
        "output": text or "",
    }


def kill_launch_session(profile: str, session_ref: str) -> dict[str, Any]:
    _require_platform()
    from cli.services.tmux_launcher import find_launched_session, kill_session, tmux_session_alive

    from core.external_cli.store import ExternalCliStore

    found = find_launched_session(profile, session_ref)
    target = found.tmux_session if found else session_ref
    if not tmux_session_alive(target):
        raise LaunchServiceError(f"tmux session not found: {session_ref}")

    kill_session(target)
    if found:
        ExternalCliStore(profile).remove_session(found.session_id)
    return {"tmux_session": target, "session_id": found.session_id if found else None}


def assign_cli(profile: str, cli_id: str, agent_type: str) -> dict[str, Any]:
    try:
        binding = assign_cli_to_subagent(profile, cli_id, agent_type)
    except ValueError as exc:
        raise LaunchServiceError(str(exc)) from exc
    return binding.to_dict()


def unassign_cli(profile: str, cli_id: str) -> dict[str, Any] | None:
    try:
        binding = unassign_cli_subagent(profile, cli_id)
    except ValueError as exc:
        raise LaunchServiceError(str(exc)) from exc
    return binding.to_dict() if binding else None