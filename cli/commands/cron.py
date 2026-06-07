"""CLI: manage profile cron jobs (same store as gateway scheduler)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from cli.shared.commands.cron_commands import parse_add_arguments, resolve_job_id
from cli.utils.rich_console import print_error, print_info, print_success
from core.cron.store import CronStore

app = typer.Typer(help="Scheduled agent tasks (cron)")


def _profile(ctx: typer.Context) -> str:
    if ctx.obj and ctx.obj.get("profile"):
        return ctx.obj["profile"]
    return "default"


@app.command("list")
def cron_list(ctx: typer.Context) -> None:
    """List cron jobs for the profile."""
    store = CronStore(_profile(ctx))
    jobs = store.list_jobs()
    if not jobs:
        print_info("No cron jobs.")
        return
    table = Table(title=f"Cron jobs ({_profile(ctx)})")
    table.add_column("ID", style="cyan")
    table.add_column("On")
    table.add_column("Name")
    table.add_column("Cron")
    table.add_column("Next (UTC)")
    table.add_column("Last")
    for j in jobs:
        table.add_row(
            j.id,
            "yes" if j.enabled else "no",
            (j.name or j.task[:32]),
            j.cron_expression,
            (j.next_run_at or "—")[:19],
            j.last_status or "—",
        )
    Console().print(table)


@app.command("add")
def cron_add(
    ctx: typer.Context,
    schedule_and_task: str = typer.Argument(
        ...,
        help='Schedule and task: "every day at 9 :: check logs" or "0 9 * * * :: task"',
    ),
    name: str = typer.Option("", "--name", "-n", help="Display name"),
) -> None:
    """Add a cron job."""
    profile = _profile(ctx)
    try:
        expr, task = parse_add_arguments(schedule_and_task)
        job = CronStore(profile).add(task=task, cron_expression=expr, name=name)
        print_success(f"Added {job.id}: {job.cron_expression}")
        print_info(f"Next run: {job.next_run_at}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


@app.command("enable")
def cron_enable(ctx: typer.Context, job_id: str = typer.Argument(...)) -> None:
    store = CronStore(_profile(ctx))
    try:
        job = resolve_job_id(store, job_id)
        store.set_enabled(job.id, True)
        print_success(f"Enabled {job.id}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


@app.command("disable")
def cron_disable(ctx: typer.Context, job_id: str = typer.Argument(...)) -> None:
    store = CronStore(_profile(ctx))
    try:
        job = resolve_job_id(store, job_id)
        store.set_enabled(job.id, False)
        print_success(f"Disabled {job.id}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


@app.command("remove")
def cron_remove(
    ctx: typer.Context,
    job_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    store = CronStore(_profile(ctx))
    try:
        job = resolve_job_id(store, job_id)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    if not yes:
        typer.confirm(f"Remove cron job {job.id} ({job.name})?", abort=True)
    if store.remove(job.id):
        print_success(f"Removed {job.id}")
    else:
        print_error("Job not found")
        raise typer.Exit(1)