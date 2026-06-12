"""holix telegram — setup and run Holix via Telegram bot."""

from __future__ import annotations

import asyncio

import typer

from cli.commands.telegram_admin import telegram_admin_clear, telegram_admin_show
from cli.commands.telegram_map import (
    run_telegram_map_import,
    telegram_map_bind,
    telegram_map_list,
    telegram_map_remove,
    telegram_map_set,
)
from cli.commands.telegram_requests import (
    telegram_requests_approve,
    telegram_requests_list,
    telegram_requests_reject,
)
from cli.commands.telegram_setup import run_telegram_setup, show_telegram_status
from cli.utils.profile import resolve_profile
from cli.utils.rich_console import print_error, print_info, print_success

telegram_app = typer.Typer(
    help="Telegram bot: interactive setup and run",
    invoke_without_command=True,
)

map_app = typer.Typer(help="Привязка Telegram user id → профиль Holix (один бот, несколько профилей)")
requests_app = typer.Typer(help="Запросы доступа: пользователи подают через /start, админ одобряет здесь")
admin_app = typer.Typer(help="Telegram-администратор (один, назначается только через CLI)")
telegram_app.add_typer(map_app, name="map")
telegram_app.add_typer(requests_app, name="requests")
telegram_app.add_typer(admin_app, name="admin")


@telegram_app.callback()
def telegram_default(ctx: typer.Context) -> None:
    """Start Telegram bot (same as ``holix telegram run``)."""
    if ctx.invoked_subcommand is not None:
        return
    telegram_run(ctx)


@telegram_app.command("run")
def telegram_run(ctx: typer.Context) -> None:
    """Start Telegram bot polling."""
    profile = resolve_profile(ctx)
    try:
        from integrations.telegram.env_store import load_telegram_env_files
        from integrations.telegram.main import run_bot

        load_telegram_env_files(profile)
    except ImportError as e:
        print_error(str(e))
        print_info("Install: uv sync --extra telegram")
        raise typer.Exit(1) from e

    print_info(f"Starting Holix Telegram bot (profile={profile})…")
    try:
        asyncio.run(run_bot(profile))
    except RuntimeError as e:
        print_error(str(e))
        if "TELEGRAM_BOT_TOKEN" in str(e):
            print_info("Настройка: holix telegram setup")
        raise typer.Exit(1) from e


@telegram_app.command("setup")
def telegram_setup(
    ctx: typer.Context,
    project_env: bool = typer.Option(
        False,
        "--project-env",
        help="Also write keys to ./.env in the current directory",
    ),
    no_start: bool = typer.Option(False, "--no-start", help="Do not offer to start the bot"),
) -> None:
    """Interactive wizard: token, allowlist, save config, optional test run."""
    profile = resolve_profile(ctx)
    asyncio.run(
        run_telegram_setup(
            profile=profile,
            also_project_env=project_env,
            skip_start=no_start,
        )
    )


@telegram_app.command("status")
def telegram_status(ctx: typer.Context) -> None:
    """Show saved Telegram configuration (token masked)."""
    show_telegram_status(resolve_profile(ctx))


@telegram_app.command("sync-menu")
def telegram_sync_menu(ctx: typer.Context) -> None:
    """Push slash-command menu to Telegram (incl. /models) without restarting the bot."""
    profile = resolve_profile(ctx)
    try:
        from integrations.telegram.commands import sync_bot_menu
        from integrations.telegram.env_store import load_telegram_env_files

        load_telegram_env_files(profile)
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


@map_app.command("list")
def telegram_map_list_cmd(ctx: typer.Context) -> None:
    """Показать привязки user id → профиль."""
    telegram_map_list(resolve_profile(ctx))


@map_app.command("set")
def telegram_map_set_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="Telegram user id (число)"),
    profile: str = typer.Argument(..., help="Имя профиля Holix"),
) -> None:
    """Привязать user id к профилю."""
    telegram_map_set(resolve_profile(ctx), user_id, profile)


@map_app.command("remove")
def telegram_map_remove_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="Telegram user id"),
) -> None:
    """Удалить привязку."""
    telegram_map_remove(resolve_profile(ctx), user_id)


@map_app.command("bind")
def telegram_map_bind_cmd(
    ctx: typer.Context,
    profile: str = typer.Argument(..., help="Профиль Holix"),
    user_id: int | None = typer.Option(None, "--user-id", "-u", help="Telegram user id"),
) -> None:
    """Быстрая привязка (user id из allowlist или --user-id)."""
    telegram_map_bind(resolve_profile(ctx), profile, user_id=user_id)


@requests_app.command("list")
def telegram_requests_list_cmd(ctx: typer.Context) -> None:
    """Показать ожидающие запросы доступа из Telegram."""
    telegram_requests_list(resolve_profile(ctx))


@requests_app.command("approve")
def telegram_requests_approve_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="Telegram user id"),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Существующий профиль Holix для пользователя",
    ),
    create_profile: str | None = typer.Option(
        None,
        "--create-profile",
        help="Создать новый профиль Holix и назначить пользователю",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Интерактивный выбор профиля",
    ),
    set_admin: bool = typer.Option(
        False,
        "--set-admin",
        help="Назначить пользователя Telegram-администратором (профиль admin; только один)",
    ),
) -> None:
    """Одобрить запрос: добавить в allowlist и привязать к профилю."""
    if profile and create_profile:
        print_error("Укажите только --profile или --create-profile, не оба.")
        raise typer.Exit(1)
    if set_admin and (profile or create_profile):
        print_error("--set-admin нельзя сочетать с --profile или --create-profile.")
        raise typer.Exit(1)
    bot_profile = resolve_profile(ctx)
    try:
        telegram_requests_approve(
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
def telegram_admin_show_cmd(ctx: typer.Context) -> None:
    """Показать назначенного Telegram-администратора."""
    telegram_admin_show(resolve_profile(ctx))


@admin_app.command("clear")
def telegram_admin_clear_cmd(ctx: typer.Context) -> None:
    """Сбросить Telegram-администратора (перед назначением другого через --set-admin)."""
    try:
        telegram_admin_clear(resolve_profile(ctx))
    except SystemExit as exc:
        raise typer.Exit(exc.code if exc.code is not None else 1) from exc


@requests_app.command("reject")
def telegram_requests_reject_cmd(
    ctx: typer.Context,
    user_id: int = typer.Argument(..., help="Telegram user id"),
) -> None:
    """Отклонить запрос доступа."""
    try:
        telegram_requests_reject(resolve_profile(ctx), user_id)
    except SystemExit as exc:
        raise typer.Exit(exc.code if exc.code is not None else 1) from exc


@map_app.command("import")
def telegram_map_import_cmd(
    ctx: typer.Context,
    pairs: str = typer.Argument(
        ...,
        help="Список USER_ID:profile через запятую, напр. 123:alice,456:bob",
    ),
) -> None:
    """Импорт нескольких привязок одной строкой."""
    run_telegram_map_import(resolve_profile(ctx), pairs)


def register_telegram_command(app: typer.Typer) -> None:
    app.add_typer(telegram_app, name="telegram")