"""Fallback when holix-studio extension is not installed."""

from __future__ import annotations

import typer

_INSTALL_HINT = (
    "Holix Studio is not installed.\n\n"
    "Install the extension (separate repo, source-available license):\n"
    "  uv tool install --force-reinstall --with holix-studio Holix\n"
    "  # or editable checkout:\n"
    "  pip install -e /path/to/holix-studio\n"
    "  # or from git:\n"
    "  pip install git+https://github.com/javded-itres/holix-studio.git\n\n"
    "Then run: holix studio serve  |  holix studio open\n"
    "Docs: https://github.com/javded-itres/holix-studio"
)

app = typer.Typer(
    name="studio",
    help="Holix Studio — install holix-studio extension to enable serve/open",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def studio_missing(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    from cli.utils.rich_console import print_error

    print_error(_INSTALL_HINT)
    raise typer.Exit(1)