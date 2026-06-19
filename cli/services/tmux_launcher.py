"""tmux session management for external coding CLIs."""

from __future__ import annotations

import re
import secrets
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.external_cli.env import (
    build_cli_env,
    build_launch_args,
    env_export_shell,
    resolve_model_for_slot,
    task_passed_in_launch_args,
)
from core.external_cli.platform import ensure_launch_platform
from core.external_cli.registry import ExternalCliSpec, get_cli_spec
from core.external_cli.store import ExternalCliBinding, ExternalCliStore, LaunchedSession


class TmuxError(RuntimeError):
    pass


@dataclass(slots=True)
class TmuxSessionInfo:
    name: str
    windows: int
    attached: bool
    created: str = ""


def _run_tmux(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    ensure_launch_platform()
    cmd = ["tmux", *args]
    try:
        return subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        raise TmuxError(stderr or f"tmux failed: {' '.join(args)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TmuxError("tmux command timed out") from exc


def list_all_tmux_sessions() -> list[TmuxSessionInfo]:
    ensure_launch_platform()
    result = _run_tmux(["list-sessions", "-F", "#{session_name}\t#{session_windows}\t#{session_attached}"], check=False)
    if result.returncode != 0:
        return []
    sessions: list[TmuxSessionInfo] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        windows = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        attached = len(parts) > 2 and parts[2] == "1"
        sessions.append(TmuxSessionInfo(name=parts[0], windows=windows, attached=attached))
    return sessions


def tmux_session_alive(name: str) -> bool:
    result = _run_tmux(["has-session", "-t", name], check=False)
    return result.returncode == 0


def _sanitize_session_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]", "-", value.strip())[:24]
    return token or "session"


def build_tmux_session_name(profile: str, cli_id: str) -> str:
    suffix = secrets.token_hex(2)
    return f"holix-{_sanitize_session_token(profile)}-{_sanitize_session_token(cli_id)}-{suffix}"


def resolve_binary(binding: ExternalCliBinding, spec: ExternalCliSpec) -> str:
    import os
    import shutil

    if binding.command.strip():
        return binding.command.strip()
    for name in spec.binary_names:
        path = shutil.which(name)
        if path:
            return path
    for raw in spec.binary_paths:
        path = Path(raw).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return spec.binary_names[0]


def _shell_launch_command(env: dict[str, str], binary: str, args: tuple[str, ...]) -> str:
    exports = env_export_shell(env)
    quoted = " ".join(shlex.quote(a) for a in (binary, *args))
    return f"{exports}; exec {quoted}"


def create_cli_session(
    *,
    profile: str,
    spec: ExternalCliSpec,
    binding: ExternalCliBinding,
    profile_config: Any,
    cwd: Path,
    task: str = "",
    tmux_session: str | None = None,
    window_name: str | None = None,
    new_window: bool = False,
    target_session: str | None = None,
) -> LaunchedSession:
    """Create or extend a tmux session running an external CLI with Holix model env."""
    ensure_launch_platform()
    model_slot = binding.model_slot or spec.default_model_slot
    model = resolve_model_for_slot(profile_config, model_slot)
    if model is None:
        raise TmuxError(
            f"No model configured for slot '{model_slot}'. "
            f"Run: holix models setup -p {profile}"
        )

    env = build_cli_env(spec, model, profile=profile, extra_env=binding.extra_env)
    binary = resolve_binary(binding, spec)
    launch_args = build_launch_args(spec, model, task)
    launch_cmd = _shell_launch_command(env, binary, launch_args)
    session_name = tmux_session or build_tmux_session_name(profile, spec.cli_id)
    from core.profile.names import resolve_workspace_root

    cwd_str = str(resolve_workspace_root(cwd))

    if new_window and target_session:
        if not tmux_session_alive(target_session):
            raise TmuxError(f"tmux session not found: {target_session}")
        win_name = window_name or f"{spec.cli_id}-{secrets.token_hex(1)}"
        _run_tmux([
            "new-window",
            "-t", target_session,
            "-n", win_name,
            "-c", cwd_str,
            launch_cmd,
        ])
        target = target_session
        window_index = _window_count(target) - 1
    elif tmux_session_alive(session_name):
        win_name = window_name or f"{spec.cli_id}-{secrets.token_hex(1)}"
        _run_tmux([
            "new-window",
            "-t", session_name,
            "-n", win_name,
            "-c", cwd_str,
            launch_cmd,
        ])
        target = session_name
        window_index = _window_count(target) - 1
    else:
        _run_tmux([
            "new-session",
            "-d",
            "-s", session_name,
            "-n", window_name or spec.cli_id,
            "-c", cwd_str,
            launch_cmd,
        ])
        target = session_name
        window_index = 0

    if task.strip() and not task_passed_in_launch_args(spec, task):
        send_text_when_ready(target, task.strip(), window_index=window_index)

    session_id = secrets.token_hex(4)
    launched = LaunchedSession(
        session_id=session_id,
        tmux_session=target,
        cli_id=spec.cli_id,
        profile=profile,
        cwd=cwd_str,
        model_slot=model_slot,
        model_name=model.model,
        window_index=window_index,
        task_preview=task.strip()[:200],
        created_at=_utc_now(),
    )
    ExternalCliStore(profile).add_session(launched)
    return launched


def _window_count(session: str) -> int:
    result = _run_tmux(["list-windows", "-t", session, "-F", "#{window_index}"])
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    return max(1, len(lines))


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def send_keys(
    tmux_session: str,
    keys: list[str] | tuple[str, ...],
    *,
    window_index: int = 0,
) -> None:
    """Send tmux key names (Up, Down, Enter, Escape, …) to a pane."""
    if not keys:
        return
    target = f"{tmux_session}:{window_index}"
    _run_tmux(["send-keys", "-t", target, *keys])


_PROMPT_MARKERS = ("❯", ">", "λ", "»")


def _pane_looks_ready(pane: str) -> bool:
    """Heuristic: interactive CLI prompt is visible and pane output has settled."""
    if not pane.strip():
        return False
    tail = pane.rstrip().splitlines()[-1] if pane.strip() else ""
    return any(marker in tail for marker in _PROMPT_MARKERS)


def send_text_when_ready(
    tmux_session: str,
    text: str,
    *,
    window_index: int = 0,
    enter: bool = True,
    timeout_s: float = 20.0,
    poll_interval_s: float = 0.25,
) -> None:
    """Wait for the tmux pane to settle, then send literal text and Enter."""
    deadline = time.monotonic() + max(0.5, timeout_s)
    previous = ""
    stable_reads = 0
    while time.monotonic() < deadline:
        pane = capture_pane(tmux_session, window_index=window_index, lines=30)
        if pane == previous:
            stable_reads += 1
        else:
            stable_reads = 0
            previous = pane
        if stable_reads >= 2 and _pane_looks_ready(pane):
            break
        time.sleep(poll_interval_s)
    send_text(tmux_session, text, window_index=window_index, enter=enter)


def send_text(
    tmux_session: str,
    text: str,
    *,
    window_index: int = 0,
    enter: bool = True,
) -> None:
    target = f"{tmux_session}:{window_index}"
    literal = text.replace("\n", " ")
    _run_tmux(["send-keys", "-t", target, "-l", literal])
    if enter:
        _run_tmux(["send-keys", "-t", target, "Enter"])


def capture_pane(
    tmux_session: str,
    *,
    window_index: int = 0,
    lines: int = 40,
) -> str:
    target = f"{tmux_session}:{window_index}"
    result = _run_tmux([
        "capture-pane",
        "-t", target,
        "-p",
        "-S", f"-{max(1, lines)}",
    ])
    return (result.stdout or "").rstrip()


def attach_session(tmux_session: str) -> int:
    """Attach to tmux session (replaces current process on success)."""
    ensure_launch_platform()
    proc = subprocess.run(["tmux", "attach", "-t", tmux_session])
    return proc.returncode


def kill_session(tmux_session: str) -> None:
    _run_tmux(["kill-session", "-t", tmux_session], check=False)


def find_launched_session(profile: str, ref: str) -> LaunchedSession | None:
    store = ExternalCliStore(profile)
    ref = ref.strip()
    for session in store.load_sessions():
        if session.session_id == ref or session.tmux_session == ref:
            return session
    return None


def find_active_sessions_for_cli(profile: str, cli_id: str) -> list[LaunchedSession]:
    """Return alive Holix tmux sessions for a given external CLI."""
    needle = cli_id.strip().lower()
    return [s for s in prune_dead_sessions(profile) if s.cli_id == needle]


def prune_dead_sessions(profile: str) -> list[LaunchedSession]:
    store = ExternalCliStore(profile)
    alive: list[LaunchedSession] = []
    for session in store.load_sessions():
        if tmux_session_alive(session.tmux_session):
            alive.append(session)
    store.save_sessions(alive)
    return alive


def kill_active_sessions_for_cli(profile: str, cli_id: str) -> list[str]:
    """Stop all alive Holix tmux sessions for a CLI; return killed tmux names."""
    store = ExternalCliStore(profile)
    killed: list[str] = []
    for session in list(store.load_sessions()):
        if session.cli_id != cli_id.strip().lower():
            continue
        if not tmux_session_alive(session.tmux_session):
            store.remove_session(session.session_id)
            continue
        kill_session(session.tmux_session)
        store.remove_session(session.session_id)
        killed.append(session.tmux_session)
    return killed


def restart_cli_by_id(
    *,
    profile: str,
    cli_id: str,
    profile_config: Any,
    cwd: Path | None = None,
    task: str = "",
    model_slot: str | None = None,
) -> LaunchedSession:
    """Kill existing tmux sessions for this CLI and start a fresh one."""
    kill_active_sessions_for_cli(profile, cli_id)
    return launch_cli_by_id(
        profile=profile,
        cli_id=cli_id,
        profile_config=profile_config,
        cwd=cwd,
        task=task,
        model_slot=model_slot,
    )


def launch_cli_by_id(
    *,
    profile: str,
    cli_id: str,
    profile_config: Any,
    cwd: Path | None = None,
    task: str = "",
    model_slot: str | None = None,
    new_window: bool = False,
    target_session: str | None = None,
) -> LaunchedSession:
    spec = get_cli_spec(cli_id)
    if spec is None:
        raise TmuxError(f"Unknown CLI: {cli_id}. Run: holix launch list")

    store = ExternalCliStore(profile)
    binding = store.get_binding(cli_id)
    if binding is None:
        binding = ExternalCliBinding(
            cli_id=cli_id,
            command="",
            model_slot=model_slot or spec.default_model_slot,
            agent_slot=model_slot or spec.default_model_slot,
        )
    elif model_slot:
        binding.model_slot = model_slot
        binding.agent_slot = model_slot

    workdir = cwd
    if workdir is None and binding.default_cwd.strip():
        workdir = Path(binding.default_cwd)
    if workdir is None:
        workdir = Path.cwd()

    return create_cli_session(
        profile=profile,
        spec=spec,
        binding=binding,
        profile_config=profile_config,
        cwd=workdir,
        task=task,
        new_window=new_window,
        target_session=target_session,
    )