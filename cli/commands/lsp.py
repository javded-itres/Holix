"""holix lsp — language servers for the agent lsp tool."""

from __future__ import annotations

import typer
from core.tools.lsp_servers import CATALOG, spec_ready
from rich.markup import escape
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.lsp.install import (
    catalog_choices,
    install_specs,
    parse_selection,
    prepend_bin_dirs_to_path,
    setup_summary,
    toolchain_labels,
)
from cli.utils.rich_console import console, print_error, print_info, print_success

app = typer.Typer(
    help="Language servers for the agent lsp tool (hover, definition, symbols).",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _print_status() -> None:
    prepend_bin_dirs_to_path()
    summary = setup_summary()
    table = Table(title="Holix language servers", show_header=True)
    table.add_column("#", justify="right")
    table.add_column("Id")
    table.add_column("Language")
    table.add_column("Status")
    table.add_column("How / install")
    for i, spec, ready in catalog_choices():
        if ready:
            status = "[green]ready[/green]"
            how = next((r["how"] for r in summary["rows"] if r["id"] == spec.id), "")
        elif spec.recommended:
            status = "[yellow]missing (recommended)[/yellow]"
            how = next((r["install"] for r in summary["rows"] if r["id"] == spec.id), "")
        else:
            status = "[dim]optional[/dim]"
            how = next((r["install"] for r in summary["rows"] if r["id"] == spec.id), "")
        table.add_row(str(i), spec.id, escape(spec.title), status, escape(how or "—"))
    console.print(table)
    print_info("Setup: holix lsp setup   |   Diagnose: holix doctor")


@app.callback()
def lsp_root(ctx: typer.Context) -> None:
    """Show which language servers are available."""
    if ctx.invoked_subcommand is None:
        _print_status()


@app.command("status")
def lsp_status() -> None:
    """List ready and missing language servers."""
    _print_status()


def _emit_lines(lines: list[str]) -> list[str]:
    errors: list[str] = []
    for line in lines:
        if line.startswith("ok:"):
            print_success(line[4:].strip())
        elif line.startswith("error:"):
            print_error(line[7:].strip())
            errors.append(line)
        elif line.startswith("skip:"):
            print_info(line[6:].strip())
        else:
            print_info(line)
    return errors


@app.command("setup")
def lsp_setup(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Assume yes: install the selection without prompting"
    ),
    all_servers: bool = typer.Option(
        False, "--all", help="Install every catalog server (recommended + optional)"
    ),
    missing: bool = typer.Option(
        False, "--missing", help="Install every server that is not ready yet"
    ),
    optional: bool = typer.Option(
        False, "--optional", help="Install optional servers only (Go, Rust, Vue, …)"
    ),
    ids: str = typer.Option(
        "",
        "--ids",
        help="Comma-separated ids, aliases, or numbers (e.g. go,rust,vue or 12,15)",
    ),
) -> None:
    """Install chosen language servers and the toolchains they need."""
    prepend_bin_dirs_to_path()
    print_info(
        "The lsp tool uses installed language servers. "
        "Pick recommended, optional, mixed (recommended,go,rust), or individual ids. "
        "Holix installs packages and missing toolchains "
        "(Node.js, Go, rustup, Ruby, Homebrew formulae)."
    )
    _print_status()

    flagged: str | None
    if ids.strip():
        flagged = ids
    elif all_servers:
        flagged = "all"
    elif missing:
        flagged = "missing"
    elif optional:
        flagged = "optional"
    elif yes:
        flagged = "recommended"
    else:
        flagged = None

    if flagged is None:
        print_info(
            "What to install:\n"
            "  [bold]recommended[/bold]  — Pyright + JS/TS/JSON/HTML/CSS/YAML/Bash/Dockerfile (default)\n"
            "  [bold]all[/bold]          — every server in the catalog\n"
            "  [bold]missing[/bold]      — everything not ready\n"
            "  [bold]optional[/bold]     — only optional (Go, Rust, C/C++, Vue, …)\n"
            "  mix                — e.g. [cyan]recommended,go,rust[/cyan]\n"
            "  numbers or ids     — e.g. [cyan]12,15,vue[/cyan] or [cyan]python js go[/cyan]"
        )
        selection = Prompt.ask("Select", default="recommended")
    else:
        selection = flagged

    try:
        specs = parse_selection(selection, CATALOG)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    already = [s for s in specs if spec_ready(s)]
    pending = [s for s in specs if not spec_ready(s)]
    if already:
        print_info("Already ready: " + ", ".join(s.title for s in already))
    if not pending:
        print_success("Nothing to install — selected servers are already ready.")
        return

    print_info("Will install: " + ", ".join(s.title for s in pending))
    chains = toolchain_labels(pending)
    if chains:
        print_info("Will also ensure if missing:")
        for label in chains:
            print_info(f"  • {label}")

    if flagged is None and not yes:
        if not Confirm.ask("Proceed?", default=True):
            print_info("Cancelled.")
            raise typer.Exit(0)

    lines = install_specs(pending, on_progress=print_info)
    errors = _emit_lines(lines)
    _print_status()
    if errors:
        raise typer.Exit(1)
