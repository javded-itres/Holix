"""holix launch — external coding CLIs in tmux (Linux/macOS)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import typer
from core.external_cli.platform import ensure_launch_platform
from core.external_cli.registry import EXTERNAL_CLI_REGISTRY, list_cli_specs
from core.external_cli.store import ExternalCliStore
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from cli.core import get_current_config, get_current_profile
from cli.launch.setup_wizard import run_launch_setup
from cli.services.tmux_launcher import (
    TmuxError,
    attach_session,
    capture_pane,
    find_launched_session,
    kill_session,
    launch_cli_by_id,
    list_all_tmux_sessions,
    prune_dead_sessions,
    send_text,
    tmux_session_alive,
)
from cli.utils.rich_console import console, print_error, print_info, print_success

app = typer.Typer(
    help="Launch external coding CLIs in tmux (Linux/macOS). Models from Holix profile.",
    no_args_is_help=True,
)


def _require_platform() -> None:
    try:
        ensure_launch_platform()
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc


def _profile_config(ctx: typer.Context) -> tuple[str, Any]:
    obj = ctx.obj or {}
    profile = obj.get("profile") or get_current_profile()
    config = obj.get("config") or get_current_config()
    return profile, config


@app.command("setup")
def launch_setup(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults"),
) -> None:
    """Interactive install and profile binding for external CLIs."""
    _require_platform()
    profile, config = _profile_config(ctx)
    run_launch_setup(profile, config, yes=yes)


@app.command("list")
def launch_list(ctx: typer.Context) -> None:
    """List supported external CLIs and profile bindings."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    import shutil

    store = ExternalCliStore(profile)
    bindings = store.load_bindings()

    table = Table(title="External CLIs", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Installed")
    table.add_column("Enabled")
    table.add_column("Model slot")
    table.add_column("Command")

    for spec in list_cli_specs():
        binding = bindings.get(spec.cli_id)
        path = None
        for name in spec.binary_names:
            path = shutil.which(name)
            if path:
                break
        if binding and binding.command:
            path = binding.command
        table.add_row(
            spec.cli_id,
            spec.display_name,
            "yes" if path else "no",
            "yes" if binding and binding.enabled else "no",
            binding.model_slot if binding else spec.default_model_slot,
            path or "—",
        )

    console.print(table)
    console.print()
    print_info("Setup: holix launch setup  |  Launch: holix launch <cli_id>")


@app.command("sessions")
def launch_sessions(ctx: typer.Context) -> None:
    """List Holix-managed tmux sessions for this profile."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    sessions = prune_dead_sessions(profile)

    if not sessions:
        print_info("No active Holix launch sessions for this profile.")
        print_info("Start one: holix launch claude --task \"implement feature X\"")
        return

    table = Table(title=f"Holix sessions ({profile})", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("tmux")
    table.add_column("CLI")
    table.add_column("Model")
    table.add_column("CWD")
    table.add_column("Win")

    for session in sessions:
        table.add_row(
            session.session_id,
            session.tmux_session,
            session.cli_id,
            session.model_name or session.model_slot,
            session.cwd[:48] + ("…" if len(session.cwd) > 48 else ""),
            str(session.window_index),
        )

    console.print(table)
    console.print()
    print_info("Attach: holix launch attach <tmux_session>")
    print_info("Send:   holix launch send <id> \"your prompt\"")
    print_info("Chat:   holix launch chat <id>")


@app.command("tmux")
def launch_tmux() -> None:
    """List all tmux sessions on this machine."""
    _require_platform()
    sessions = list_all_tmux_sessions()
    if not sessions:
        print_info("No tmux sessions running.")
        return

    table = Table(title="tmux sessions", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Windows")
    table.add_column("Attached")

    for session in sessions:
        table.add_row(
            session.name,
            str(session.windows),
            "yes" if session.attached else "no",
        )
    console.print(table)


@app.command("attach")
def launch_attach(
    session: str = typer.Argument(..., help="tmux session name or Holix session id"),
    ctx: typer.Context = None,
) -> None:
    """Attach to a tmux session (hands control to tmux)."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    target = session
    found = find_launched_session(profile, session)
    if found:
        target = found.tmux_session
    if not tmux_session_alive(target):
        print_error(f"tmux session not found: {target}")
        raise typer.Exit(1)
    print_info(f"Attaching to {target} (detach: Ctrl+b d)")
    raise typer.Exit(attach_session(target))


@app.command("send")
def launch_send(
    session: str = typer.Argument(..., help="Session id or tmux name"),
    message: str = typer.Argument(..., help="Text to send to the CLI"),
    ctx: typer.Context = None,
    no_enter: bool = typer.Option(False, "--no-enter", help="Do not press Enter after text"),
) -> None:
    """Send a task/prompt to a running external CLI session."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    found = find_launched_session(profile, session)
    target = found.tmux_session if found else session
    if not tmux_session_alive(target):
        print_error(f"Session not found: {session}")
        raise typer.Exit(1)
    window = found.window_index if found else 0
    send_text(target, message, window_index=window, enter=not no_enter)
    if found:
        ExternalCliStore(profile).touch_session_output(found.session_id)
    print_success(f"Sent to {target}:{window}")


@app.command("output")
def launch_output(
    session: str = typer.Argument(..., help="Session id or tmux name"),
    ctx: typer.Context = None,
    lines: int = typer.Option(40, "--lines", "-n", help="Lines to capture"),
) -> None:
    """Show recent output from an external CLI pane."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    found = find_launched_session(profile, session)
    target = found.tmux_session if found else session
    if not tmux_session_alive(target):
        print_error(f"Session not found: {session}")
        raise typer.Exit(1)
    window = found.window_index if found else 0
    text = capture_pane(target, window_index=window, lines=lines)
    console.print(Panel(text or "(empty)", title=f"{target}:{window}", border_style="dim"))
    if found:
        ExternalCliStore(profile).touch_session_output(found.session_id)


@app.command("chat")
def launch_chat(
    session: str = typer.Argument(..., help="Session id or tmux name"),
    ctx: typer.Context = None,
) -> None:
    """Interactive relay: type prompts, see CLI output (Ctrl+C to exit)."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    found = find_launched_session(profile, session)
    target = found.tmux_session if found else session
    if not tmux_session_alive(target):
        print_error(f"Session not found: {session}")
        raise typer.Exit(1)
    window = found.window_index if found else 0

    console.print(Panel.fit(
        f"[bold]Relay → {target}:{window}[/bold]\n"
        "Type a prompt and press Enter. Empty line shows output. Ctrl+C to quit.",
        border_style="cyan",
    ))

    store = ExternalCliStore(profile)
    try:
        while True:
            try:
                user_input = Prompt.ask("[bold cyan]holix[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not user_input.strip():
                text = capture_pane(target, window_index=window, lines=30)
                console.print(Panel(text or "(empty)", border_style="dim"))
                continue
            send_text(target, user_input.strip(), window_index=window)
            time.sleep(0.8)
            text = capture_pane(target, window_index=window, lines=35)
            console.print(Panel(text, title="CLI output", border_style="green"))
            if found:
                store.touch_session_output(found.session_id)
    except KeyboardInterrupt:
        console.print()
    print_info("Relay ended.")


@app.command("kill")
def launch_kill(
    session: str = typer.Argument(..., help="Session id or tmux name"),
    ctx: typer.Context = None,
) -> None:
    """Stop a tmux session launched by Holix."""
    _require_platform()
    profile, _ = _profile_config(ctx)
    found = find_launched_session(profile, session)
    target = found.tmux_session if found else session
    kill_session(target)
    if found:
        ExternalCliStore(profile).remove_session(found.session_id)
    print_success(f"Killed {target}")


def _launch_cli(
    ctx: typer.Context,
    cli_id: str,
    *,
    cwd: Path | None,
    task: str,
    model_slot: str | None,
    detach: bool,
    new_window: bool,
    session: str | None,
) -> None:
    _require_platform()
    profile, config = _profile_config(ctx)

    try:
        launched = launch_cli_by_id(
            profile=profile,
            cli_id=cli_id,
            profile_config=config,
            cwd=cwd,
            task=task,
            model_slot=model_slot,
            new_window=new_window,
            target_session=session,
        )
    except TmuxError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    print_success(f"Started {cli_id} in tmux [bold]{launched.tmux_session}[/bold]")
    print_info(f"Model: {launched.model_name} (slot: {launched.model_slot})")
    print_info(f"CWD:   {launched.cwd}")
    print_info(f"Attach: holix launch attach {launched.tmux_session}")
    print_info(f"Relay:  holix launch chat {launched.session_id}")

    if not detach:
        print_info("Attach now? (y/n)")
        if sys.stdin.isatty():
            answer = Prompt.ask("Attach", default="y")
            if answer.strip().lower() in {"y", "yes", ""}:
                raise typer.Exit(attach_session(launched.tmux_session))


def _register_cli_launch_commands() -> None:
    for cli_name, spec in EXTERNAL_CLI_REGISTRY.items():
        def _make_cmd(name: str, label: str):
            def _cmd(
                ctx: typer.Context,
                cwd: Path | None = typer.Option(None, "--cwd", "-C", help="Working directory"),
                task: str = typer.Option("", "--task", "-t", help="Initial prompt"),
                model_slot: str | None = typer.Option(None, "--model-slot", "-m", help="Profile model slot"),
                detach: bool = typer.Option(True, "--detach/--attach", help="Detach after launch"),
                new_window: bool = typer.Option(False, "--window", "-w", help="New window in session"),
                session: str | None = typer.Option(None, "--session", "-s", help="Target tmux session"),
            ) -> None:
                _launch_cli(
                    ctx,
                    name,
                    cwd=cwd,
                    task=task,
                    model_slot=model_slot,
                    detach=detach,
                    new_window=new_window,
                    session=session,
                )
            _cmd.__doc__ = f"Launch {label} in tmux with Holix profile models."
            return _cmd

        app.command(cli_name, help=f"Launch {spec.display_name} in tmux")(
            _make_cmd(cli_name, spec.display_name)
        )


_register_cli_launch_commands()