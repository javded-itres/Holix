"""Install Holix globally: ``holix install``."""

from __future__ import annotations

import typer

from cli.installer import InstallOptions, detect_repo_root, install_holix, verify_holix_on_path
from cli.installer.system import record_install
from cli.utils.rich_console import print_error, print_info, print_success, print_warning

app = typer.Typer(
    help="Install or update the holix command on your system PATH",
    invoke_without_command=True,
)


@app.callback()
def install_holix_cli(
    ctx: typer.Context,
    system: bool = typer.Option(
        False,
        "--system",
        help="Install for all users (may require administrator/sudo)",
    ),
    no_path: bool = typer.Option(
        False,
        "--no-path",
        help="Do not modify shell PATH (.bashrc / .zshrc / Windows user PATH)",
    ),
    extra: list[str] = typer.Option(
        None,
        "--extra",
        "-e",
        help="Optional extras: telegram, browser",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Path to Holix source (default: auto-detect from this install)",
    ),
) -> None:
    """Install ``holix`` so it works from any directory.

    Examples:

        holix install
        holix install --extra telegram
        holix install --system
    """
    if ctx.invoked_subcommand is not None:
        return

    from pathlib import Path

    try:
        repo_root = detect_repo_root() if repo is None else detect_repo_root(Path(repo))
    except FileNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    scope = "system" if system else "user"
    if system:
        print_warning("System install may require sudo / Administrator.")

    opts = InstallOptions(
        repo_root=repo_root,
        scope=scope,
        update_path=not no_path,
        extras=tuple(extra or ()),
    )
    print_info(f"Installing from {repo_root} ({scope})…")
    result = install_holix(opts)

    if not result.success:
        print_error(result.message)
        raise typer.Exit(1)

    record_install(result, opts, repo_root=repo_root)
    print_success("Installation complete")
    for line in result.message.strip().splitlines():
        print_info(line)

    ok, loc = verify_holix_on_path()
    if ok:
        print_success(f"`holix` is on PATH → {loc}")
    else:
        print_warning("Open a new terminal, then run: holix version")


