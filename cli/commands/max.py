"""holix max — setup and run Holix via MAX messenger bot."""

from __future__ import annotations

import asyncio

import typer

from cli.commands.max_admin import max_admin_clear, max_admin_show
from cli.commands.max_map import (
    max_map_bind,
    max_map_list,
    max_map_remove,
    max_map_set,
    run_max_map_import,
)
from cli.commands.max_requests import (
    max_requests_approve,
    max_requests_list,
    max_requests_reject,
)
from cli.commands.max_setup import run_max_setup, show_max_status
from cli.utils.profile import resolve_profile
from cli.utils.rich_console import print_error, print_info, print_success

max_app = typer.Typer(
    help="MAX messenger bot: interactive setup and run",
    invoke_without_command=True,
)

map_app = typer.Typer(help="Привязка MAX user id → профиль Holix (один бот, несколько профилей)")
requests_app = typer.Typer(help="Запросы доступа: пользователи подают через /start, админ одобряет здесь")
admin_app = typer.Typer(help="MAX-администратор (один, назначается только через CLI)")
max_app.add_typer(map_app, name="map")
max_app.add_typer(requests_app, name="requests")
max_app.add_typer(admin_app, name="admin")


@max_app.callback()
def max_default(ctx: typer.Context) -> None:
    """Start MAX bot (same as ``holix max run``)."""
    if ctx.invoked_subcommand is not None:
        return
    max_run(ctx)


@max_app.command("run")
def max_run(ctx: typer.Context) -> None:
    """Start MAX bot Long Polling (dev/test)."""
    profile = resolve_profile(ctx)
    try:
        from integrations.max.env_store import load_max_env_files
        from integrations.max.main import run_bot

        load_max_env_files(profile)
    except ImportError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_info(f"Starting Holix MAX bot (profile={profile})…")
    print_info("Initializing Holix agent (memory, tools, MCP)…")
    try:
        asyncio.run(run_bot(profile))
    except RuntimeError as e:
        print_error(str(e))
        if "MAX_ACCESS_TOKEN" in str(e):
            print_info("Настройка: holix max setup")
        raise typer.Exit(1) from e


@max_app.command("setup")
def max_setup(
    ctx: typer.Context,
    project_env: bool = typer.Option(
        False,
        "--project-env",
        help="Also write keys to ./.env in the current directory",
    ),
    no_start: bool = typer.Option(False, "--no-start", help="Do not offer to start the bot"),
) -> None:
    """Interactive wizard: token, allowlist, mode, save config."""
    profile = resolve_profile(ctx)
    asyncio.run(
        run_max_setup(
            profile=profile,
            also_project_env=project_env,
            skip_start=no_start,
        )
    )


@max_app.command("status")
def max_status(ctx: typer.Context) -> None:
    """Show saved MAX configuration (token masked)."""
    show_max_status(resolve_profile(ctx))


@max_app.command("sync-menu")
def max_sync_menu(ctx: typer.Context) -> None:
    """Push slash-command menu to MAX (incl. /models) without restarting the bot."""
    profile = resolve_profile(ctx)
    try:
        from integrations.max.commands import sync_bot_menu
        from integrations.max.env_store import load_max_env_files

        load_max_env_files(profile)
        names = asyncio.run(sync_bot_menu(profile))
    except ImportError as e:
        print_error(str(e))
        print_info("Install: uv sync --extra max")
        raise typer.Exit(1) from e
    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_success(f"MAX menu updated ({len(names)} commands)")
    if "models" in names:
        print_info("  /models — смена LLM")
    else:
        print_error("  /models missing from registration — report a bug")
    print_info("If the client still shows the old list, re-open the chat with the bot")


@map_app.command("list")
def max_map_list_cmd(ctx: typer.Context) -> None:
    max_map_list(resolve_profile(ctx))


@map_app.command("set")
def max_map_set_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="MAX user id (число)"),
    profile: str = typer.Argument(..., help="Имя профиля Holix"),
) -> None:
    max_map_set(resolve_profile(ctx), user_id, profile)


@map_app.command("remove")
def max_map_remove_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="MAX user id"),
) -> None:
    max_map_remove(resolve_profile(ctx), user_id)


@map_app.command("bind")
def max_map_bind_cmd(
    ctx: typer.Context,
    profile: str = typer.Argument(..., help="Профиль Holix"),
    user_id: int | None = typer.Option(None, "--user-id", "-u", help="MAX user id"),
) -> None:
    max_map_bind(resolve_profile(ctx), profile, user_id=user_id)


@map_app.command("import")
def max_map_import_cmd(
    ctx: typer.Context,
    pairs: str = typer.Argument(
        ...,
        help="Список USER_ID:profile через запятую, напр. 123:alice,456:bob",
    ),
) -> None:
    run_max_map_import(resolve_profile(ctx), pairs)


@requests_app.command("list")
def max_requests_list_cmd(ctx: typer.Context) -> None:
    max_requests_list(resolve_profile(ctx))


@requests_app.command("approve")
def max_requests_approve_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="MAX user id"),
    profile: str | None = typer.Option(None, "--profile", help="Существующий профиль Holix"),
    create_profile: str | None = typer.Option(
        None,
        "--create-profile",
        help="Создать новый профиль Holix",
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Интерактивный выбор"),
    set_admin: bool = typer.Option(
        False,
        "--set-admin",
        help="Назначить MAX-администратором (профиль admin; только один)",
    ),
) -> None:
    if profile and create_profile:
        print_error("Укажите только --profile или --create-profile, не оба.")
        raise typer.Exit(1)
    if set_admin and (profile or create_profile):
        print_error("--set-admin нельзя сочетать с --profile или --create-profile.")
        raise typer.Exit(1)
    bot_profile = resolve_profile(ctx)
    try:
        max_requests_approve(
            bot_profile,
            user_id,
            profile=profile,
            create_profile=create_profile,
            interactive=interactive
            or (profile is None and create_profile is None and not set_admin),
            set_admin=set_admin,
        )
    except SystemExit as exc:
        raise typer.Exit(exc.code if exc.code is not None else 1) from exc


@admin_app.command("show")
def max_admin_show_cmd(ctx: typer.Context) -> None:
    max_admin_show(resolve_profile(ctx))


@admin_app.command("clear")
def max_admin_clear_cmd(ctx: typer.Context) -> None:
    try:
        max_admin_clear(resolve_profile(ctx))
    except SystemExit as exc:
        raise typer.Exit(exc.code if exc.code is not None else 1) from exc


@requests_app.command("reject")
def max_requests_reject_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="MAX user id"),
) -> None:
    try:
        max_requests_reject(resolve_profile(ctx), user_id)
    except SystemExit as exc:
        raise typer.Exit(exc.code if exc.code is not None else 1) from exc


def register_max_command(app: typer.Typer) -> None:
    app.add_typer(max_app, name="max")