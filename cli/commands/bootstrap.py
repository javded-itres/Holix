"""``holix bootstrap`` — first-run LLM + Telegram setup."""

from __future__ import annotations

import typer

from cli.installer.bootstrap import BootstrapOptions, run_bootstrap_setup_sync
from cli.utils.rich_console import print_error

app = typer.Typer(
    help="Первичная настройка после установки (LLM, Telegram)",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def bootstrap_entry(
    ctx: typer.Context,
    full: bool = typer.Option(
        False,
        "--full",
        help="Отметить полную установку (информационно; extras ставятся install.sh)",
    ),
    minimal: bool = typer.Option(
        False,
        "--minimal",
        help="Минимальная установка (без подсказки про extras)",
    ),
    skip_llm: bool = typer.Option(False, "--skip-llm", help="Не настраивать LLM"),
    skip_telegram: bool = typer.Option(False, "--skip-telegram", help="Не настраивать Telegram"),
    profile: str = typer.Option("default", "--profile", "-p", help="Профиль Holix"),
    lang: str | None = typer.Option(
        None,
        "--lang",
        help="UI language for setup (en|ru). Auto-detected from OS; English systems are prompted.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Неинтерактивный режим"),
) -> None:
    """Интерактивная настройка LLM и Telegram после установки.

    Examples:

        holix bootstrap
        holix bootstrap --skip-telegram
        holix bootstrap -y
    """
    if ctx.invoked_subcommand is not None:
        return

    full_install: bool | None = True if full else False if minimal else None
    code = run_bootstrap_setup_sync(
        BootstrapOptions(
            full_install=full_install,
            skip_llm=skip_llm,
            skip_telegram=skip_telegram,
            profile=profile,
            lang=lang,
            non_interactive=yes,
        )
    )
    if code != 0:
        print_error("Настройка завершена с предупреждениями (см. выше).")
        raise typer.Exit(code)