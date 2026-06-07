"""helix telegram — setup and run Helix via Telegram bot."""

from __future__ import annotations

import asyncio

import typer

from cli.commands.telegram_setup import run_telegram_setup, show_telegram_status
from cli.utils.rich_console import print_error, print_info, print_success

telegram_app = typer.Typer(
    help="Telegram bot: interactive setup and run",
    invoke_without_command=True,
)


@telegram_app.callback()
def telegram_default(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", "-p", help="Helix profile"),
) -> None:
    """Start Telegram bot (same as ``helix telegram run``)."""
    if ctx.invoked_subcommand is not None:
        return
    telegram_run(profile=profile)


@telegram_app.command("run")
def telegram_run(
    profile: str = typer.Option("default", "--profile", "-p", help="Helix profile"),
) -> None:
    """Start Telegram bot polling."""
    try:
        from integrations.telegram.env_store import load_telegram_env_files
        from integrations.telegram.main import run_bot

        load_telegram_env_files()
    except ImportError as e:
        print_error(str(e))
        print_info("Install: uv sync --extra telegram")
        raise typer.Exit(1) from e

    print_info(f"Starting Helix Telegram bot (profile={profile})…")
    try:
        asyncio.run(run_bot(profile))
    except RuntimeError as e:
        print_error(str(e))
        if "TELEGRAM_BOT_TOKEN" in str(e):
            print_info("Настройка: helix telegram setup")
        raise typer.Exit(1) from e


@telegram_app.command("setup")
def telegram_setup(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Helix profile"),
    project_env: bool = typer.Option(
        False,
        "--project-env",
        help="Also write keys to ./.env in the current directory",
    ),
    no_start: bool = typer.Option(False, "--no-start", help="Do not offer to start the bot"),
) -> None:
    """Interactive wizard: token, allowlist, save config, optional test run."""
    asyncio.run(
        run_telegram_setup(
            profile=profile,
            also_project_env=project_env,
            skip_start=no_start,
        )
    )


@telegram_app.command("status")
def telegram_status() -> None:
    """Show saved Telegram configuration (token masked)."""
    show_telegram_status()


@telegram_app.command("sync-menu")
def telegram_sync_menu(
    profile: str = typer.Option("default", "--profile", "-p", help="Helix profile"),
) -> None:
    """Push slash-command menu to Telegram (incl. /models) without restarting the bot."""
    try:
        from integrations.telegram.env_store import load_telegram_env_files
        from integrations.telegram.commands import sync_bot_menu

        load_telegram_env_files()
        names = asyncio.run(sync_bot_menu(profile))
    except ImportError as e:
        print_error(str(e))
        print_info("Install: uv sync --extra telegram")
        raise typer.Exit(1) from e
    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_success(f"Telegram menu updated ({len(names)} commands)")
    if "models" in names:
        print_info("  /models — смена LLM")
    else:
        print_error("  /models missing from registration — report a bug")
    print_info("If the client still shows the old list, restart Telegram or re-open the chat")


def register_telegram_command(app: typer.Typer) -> None:
    app.add_typer(telegram_app, name="telegram")