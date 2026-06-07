"""Update Helix: ``helix update``."""

from __future__ import annotations

from pathlib import Path

import typer

from cli import __version__
from cli.installer.manifest import load_manifest
from cli.installer.update import UpdateOptions, update_helix
from cli.utils.rich_console import print_error, print_info, print_success, print_warning

app = typer.Typer(
    help="Check for and apply Helix updates",
    invoke_without_command=True,
)


@app.callback()
def update_helix_cli(
    ctx: typer.Context,
    check: bool = typer.Option(
        False,
        "--check",
        "-n",
        help="Only check for updates; do not install",
    ),
    channel: str = typer.Option(
        "auto",
        "--channel",
        "-c",
        help="Update source: auto, git, or pypi",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Git repository path (overrides saved install metadata)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Reinstall even if already up to date",
    ),
    no_fetch: bool = typer.Option(
        False,
        "--no-fetch",
        help="Skip git fetch (git channel only)",
    ),
) -> None:
    """Update Helix from git or PyPI.

    Uses ``~/.helix/install.json`` written by ``helix install``.

    Examples:

        helix update
        helix update --check
        helix update --channel git --repo ~/src/Helix
        helix update --force
    """
    if ctx.invoked_subcommand is not None:
        return

    if channel not in ("auto", "git", "pypi"):
        print_error("Channel must be: auto, git, or pypi")
        raise typer.Exit(1)

    manifest = load_manifest()
    if manifest:
        print_info(
            f"Current: {__version__} · install: {manifest.method} · source: {manifest.source}"
        )
    else:
        print_warning("No install manifest — inferring update source")

    opts = UpdateOptions(
        check_only=check,
        channel=channel,
        repo=Path(repo) if repo else None,
        force=force,
        no_fetch=no_fetch,
    )

    action = "Checking" if check else "Updating"
    print_info(f"{action}…")
    result = update_helix(opts)

    if not result.success:
        print_error(result.message)
        raise typer.Exit(1)

    if result.updated:
        print_success("Update applied")
    elif check:
        print_info(result.message)
    else:
        print_success(result.message)

    if "\n" in result.message:
        for line in result.message.strip().splitlines():
            print_info(line)

    if result.updated and result.target_version:
        print_info(f"Expected version after restart: {result.target_version}")