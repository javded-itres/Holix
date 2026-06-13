"""``holix logs`` — view, filter, rotate, and toggle debug logging."""

from __future__ import annotations

import typer
from core.logging.paths import LogSource, discover_log_files
from core.logging.reader import format_entry, read_log_entries, tail_log_entries
from core.logging.rotation import purge_old_rotations, rotate_all_known
from core.logging.setup import is_debug_enabled, set_debug_enabled
from core.logging.state import load_logging_state
from rich.console import Console
from rich.table import Table

from cli.utils.rich_console import print_info, print_success, print_warning

app = typer.Typer(help="View and manage Holix logs", no_args_is_help=True)
console = Console()


def _profile(ctx: typer.Context) -> str:
    if ctx.obj and ctx.obj.get("profile"):
        return ctx.obj["profile"]
    return "default"


def _parse_source(value: str) -> LogSource:
    try:
        return LogSource(value.lower())
    except ValueError:
        valid = ", ".join(s.value for s in LogSource)
        raise typer.BadParameter(f"Unknown source '{value}'. Choose: {valid}") from None


@app.command("list")
def logs_list(ctx: typer.Context) -> None:
    """List log files and sizes."""
    profile = _profile(ctx)
    table = Table(title=f"Holix logs (profile={profile})")
    table.add_column("Source", style="cyan")
    table.add_column("File")
    table.add_column("Size", justify="right")
    table.add_column("Status")

    for info in discover_log_files(profile):
        size = info.size_bytes
        size_str = f"{size:,} B" if size else "—"
        status = "[green]exists[/green]" if info.path.exists() else "[dim]missing[/dim]"
        table.add_row(info.source.value, str(info.path), size_str, status)

    debug = is_debug_enabled()
    table.caption = f"Debug mode: {'ON' if debug else 'OFF'} · state: {load_logging_state().level}"
    console.print(table)


@app.command("show")
def logs_show(
    ctx: typer.Context,
    lines: int = typer.Option(80, "--lines", "-n", help="Number of recent lines"),
    source: str = typer.Option("all", "--source", "-s", help="agent|gateway|cron|subagent|system|all"),
    level: str = typer.Option("", "--level", "-l", help="Minimum level: debug|info|warning|error"),
    grep: str = typer.Option("", "--grep", "-g", help="Filter lines containing text"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream new log lines"),
    debug: bool = typer.Option(False, "--debug", help="Include agent.debug.jsonl"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show extra JSON fields"),
) -> None:
    """Show recent log entries from all Holix sources."""
    profile = _profile(ctx)
    src = _parse_source(source)
    level_filter = level or None

    if follow:
        print_info(f"Following logs (source={src.value}, Ctrl+C to stop)…")
        try:
            for entry in tail_log_entries(
                source=src,
                profile=profile,
                lines=lines,
                level=level_filter,
                grep=grep or None,
                follow=True,
            ):
                console.print(format_entry(entry, verbose=verbose))
        except KeyboardInterrupt:
            print_info("Stopped.")
        return

    entries = read_log_entries(
        source=src,
        profile=profile,
        lines=lines,
        level=level_filter,
        grep=grep or None,
        include_debug=debug or is_debug_enabled(),
    )
    if not entries:
        print_warning("No log entries found. Run an agent or `holix gateway start` first.")
        return

    for entry in entries:
        style = None
        if entry.level.upper() in ("ERROR", "CRITICAL"):
            style = "red"
        elif entry.level.upper() in ("WARNING", "WARN"):
            style = "yellow"
        elif entry.level.upper() == "DEBUG":
            style = "dim"
        text = format_entry(entry, verbose=verbose)
        console.print(text, style=style)


@app.callback(invoke_without_command=True)
def logs_default(
    ctx: typer.Context,
    lines: int = typer.Option(80, "--lines", "-n"),
    source: str = typer.Option("all", "--source", "-s"),
    level: str = typer.Option("", "--level", "-l"),
    grep: str = typer.Option("", "--grep", "-g"),
    follow: bool = typer.Option(False, "--follow", "-f"),
    debug: bool = typer.Option(False, "--debug"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Default: show recent logs (same as ``holix logs show``)."""
    if ctx.invoked_subcommand is not None:
        return
    logs_show(
        ctx,
        lines=lines,
        source=source,
        level=level,
        grep=grep,
        follow=follow,
        debug=debug,
        verbose=verbose,
    )


@app.command("rotate")
def logs_rotate(
    ctx: typer.Context,
    purge: bool = typer.Option(True, "--purge/--no-purge", help="Remove backups older than retention"),
) -> None:
    """Rotate oversized log files."""
    profile = _profile(ctx)
    rotated = rotate_all_known(profile)
    if rotated:
        print_success(f"Rotated {len(rotated)} file(s)")
        for path in rotated:
            print_info(str(path))
    else:
        print_info("No logs exceeded rotation size threshold")

    if purge:
        removed = purge_old_rotations(profile)
        if removed:
            print_success(f"Purged {removed} old backup(s)")


debug_app = typer.Typer(help="Debug log mode", no_args_is_help=True)


@debug_app.command("on")
def debug_on() -> None:
    """Enable debug logging (persisted + agent.debug.jsonl)."""
    set_debug_enabled(True)
    print_success("Debug logging enabled")


@debug_app.command("off")
def debug_off() -> None:
    """Disable debug logging."""
    set_debug_enabled(False)
    print_success("Debug logging disabled")


@debug_app.command("status")
def debug_status() -> None:
    """Show debug log mode."""
    state = load_logging_state()
    on = is_debug_enabled()
    print_info(f"Debug mode: {'ON' if on else 'OFF'}")
    print_info(f"Persisted level: {state.level}")
    print_info(f"HOLIX_LOG_DEBUG env: {__import__('config').settings.log_debug_enabled}")


app.add_typer(debug_app, name="debug")