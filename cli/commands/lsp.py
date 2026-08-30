"""holix lsp — language servers for the agent lsp tool."""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.prompt import Confirm
from rich.table import Table

from cli.lsp.install import install_recommended, setup_summary
from cli.utils.rich_console import console, print_error, print_info, print_success

app = typer.Typer(
    help="Language servers for the agent lsp tool (hover, definition, symbols).",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _print_status() -> None:
    summary = setup_summary()
    table = Table(title="Holix language servers", show_header=True)
    table.add_column("Language")
    table.add_column("Status")
    table.add_column("How / install")
    for row in summary["ready"]:
        table.add_row(escape(row["title"]), "[green]ready[/green]", escape(row["how"] or "—"))
    for row in summary["missing_recommended"]:
        table.add_row(
            escape(row["title"]),
            "[yellow]missing (recommended)[/yellow]",
            escape(row["install"] or "—"),
        )
    for row in summary["optional"]:
        table.add_row(escape(row["title"]), "[dim]optional[/dim]", escape(row["install"] or "—"))
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


@app.command("setup")
def lsp_setup(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Install recommended packages without prompting"
    ),
) -> None:
    """Install recommended language servers (Python Pyright + Node web stack if npm exists)."""
    summary = setup_summary()
    print_info(
        "The lsp tool uses installed language servers. Recommended default: "
        "Python (Pyright) and, if Node.js is present, JS/TS, JSON, HTML, CSS, YAML, Bash, Dockerfile."
    )
    if not yes:
        if not Confirm.ask("Install recommended language-server packages now?", default=True):
            print_info("Skipped. Later: holix lsp setup --yes")
            _print_status()
            return
    lines = install_recommended(npm=True)
    errors = [line for line in lines if line.startswith("error:")]
    for line in lines:
        if line.startswith("ok:"):
            print_success(line[4:].strip())
        elif line.startswith("error:"):
            print_error(line[7:].strip())
        else:
            print_info(line)
    _print_status()
    if errors:
        raise typer.Exit(1)
    if summary["has_node"] is False:
        print_info(
            "Install Node.js to enable JS/TS/JSON/HTML/CSS/YAML/Bash servers, then re-run holix lsp setup"
        )
