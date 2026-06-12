"""Documentation website commands (web-docs/)."""

from __future__ import annotations

import typer

from cli.services.docs_site import build_docs_site, serve_docs_site
from cli.utils.rich_console import print_error

app = typer.Typer(
    help="Holix documentation website (dark theme, search, EN/RU)",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def docs_entry(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8080, "--port", "-p", help="HTTP port"),
    open_browser: bool = typer.Option(
        False,
        "--open",
        "-o",
        help="Open browser after start",
    ),
):
    """Start the documentation site (default when no subcommand is given).

    Examples:
        holix docs
        holix docs --port 9000 --open
        holix docs serve -p 8080
    """
    if ctx.invoked_subcommand is None:
        _serve(host=host, port=port, open_browser=open_browser)


@app.command("serve")
def docs_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8080, "--port", "-p", help="HTTP port"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="Open browser"),
):
    """Serve the documentation website."""
    _serve(host=host, port=port, open_browser=open_browser)


@app.command("build")
def docs_build():
    """Rebuild search index and sync content from docs/en and docs/ru."""
    try:
        build_docs_site()
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


def _serve(*, host: str, port: int, open_browser: bool) -> None:
    try:
        serve_docs_site(host=host, port=port, open_browser=open_browser)
    except FileNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except SystemExit:
        raise
    except Exception as e:
        print_error(f"Failed to start docs server: {e}")
        raise typer.Exit(1) from e