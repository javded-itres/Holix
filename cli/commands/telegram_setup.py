"""Interactive ``helix telegram setup`` wizard."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning
from integrations.telegram.env_store import (
    TELEGRAM_ENV_PATH,
    apply_to_environ,
    load_telegram_env_files,
    mask_token,
    merge_project_env,
    read_telegram_env_values,
    save_telegram_env,
    token_looks_valid,
)
from integrations.telegram.setup_api import TelegramApiError, verify_bot_token, wait_for_telegram_user


def _telegram_extra_installed() -> bool:
    try:
        import aiogram  # noqa: F401

        return True
    except ImportError:
        return False


def _install_telegram_extra() -> bool:
    uv = __import__("shutil").which("uv")
    cmd = [uv, "sync", "--extra", "telegram"] if uv else [sys.executable, "-m", "pip", "install", "aiogram>=3.15.0"]
    print_info("Installing Telegram dependencies…")
    try:
        subprocess.run(cmd, check=True, timeout=300)
        return _telegram_extra_installed()
    except (subprocess.CalledProcessError, OSError) as e:
        print_error(f"Install failed: {e}")
        return False


async def run_telegram_setup(
    *,
    profile: str | None = None,
    also_project_env: bool = False,
    skip_start: bool = False,
) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Telegram — подключение бота[/bold cyan]\n\n"
            "1. Откройте [@BotFather](https://t.me/BotFather) → /newbot → скопируйте токен\n"
            "2. Узнайте свой numeric user id (@userinfobot или авто-определение ниже)\n"
            "3. Настройки сохраняются в [dim]~/.helix/telegram.env[/dim]",
            border_style="cyan",
        )
    )

    if not _telegram_extra_installed():
        print_warning("Пакет aiogram не установлен (нужен для Telegram).")
        if Confirm.ask("Установить сейчас? (uv sync --extra telegram)", default=True):
            if not _install_telegram_extra():
                raise SystemExit(1)
        else:
            print_info("Выполните: uv sync --extra telegram")
            raise SystemExit(1)

    existing = read_telegram_env_values()
    default_token = existing.get("TELEGRAM_BOT_TOKEN", "")
    if default_token and Confirm.ask("Использовать сохранённый токен?", default=True):
        token = default_token
    else:
        token = Prompt.ask(
            "Токен бота от @BotFather",
            password=True,
            default=default_token or "",
        ).strip()

    if not token_looks_valid(token):
        print_error("Неверный формат токена. Ожидается: 123456789:AAH…")
        raise SystemExit(1)

    print_info("Проверка токена (getMe)…")
    try:
        me = await verify_bot_token(token)
    except TelegramApiError as e:
        print_error(f"Telegram API: {e}")
        raise SystemExit(1) from e

    username = me.get("username") or me.get("first_name") or "bot"
    print_success(f"Бот подключён: @{username} (id={me.get('id')})")

    allowed_default = existing.get("HELIX_TELEGRAM_ALLOWED_USERS", "")
    allowed = Prompt.ask(
        "Ваш Telegram user id (число, можно несколько через запятую)",
        default=allowed_default,
    ).strip()

    if not allowed and Confirm.ask(
        "Определить user id автоматически? (отправьте /start боту в Telegram)",
        default=True,
    ):
        print_info(f"Откройте https://t.me/{username} и отправьте /start …")
        detected = await wait_for_telegram_user(token, timeout_s=90.0)
        if detected is not None:
            allowed = str(detected)
            print_success(f"Найден user id: {detected}")
        else:
            print_warning("Не получено сообщений за 90 с. Введите id вручную.")
            allowed = Prompt.ask("Telegram user id").strip()

    if not allowed.replace(",", "").replace(" ", "").isdigit():
        print_error("User id должен содержать только цифры и запятые.")
        raise SystemExit(1)

    manager = ProfileManager()
    profiles = manager.list_profiles() or ["default"]
    if profile is None:
        if len(profiles) == 1:
            profile = profiles[0]
        else:
            console.print("[dim]Профили Helix:[/dim] " + ", ".join(profiles))
            profile = Prompt.ask("Профиль Helix для бота", default=existing.get("HELIX_TELEGRAM_PROFILE", "default"))
    if profile not in profiles:
        print_warning(f"Профиль '{profile}' не найден — будет создан при первом запуске.")

    values = {
        "TELEGRAM_BOT_TOKEN": token,
        "HELIX_TELEGRAM_ALLOWED_USERS": allowed.replace(" ", ""),
        "HELIX_TELEGRAM_PROFILE": profile,
    }
    edit_ms = existing.get("HELIX_TELEGRAM_EDIT_MS", "")
    if edit_ms:
        values["HELIX_TELEGRAM_EDIT_MS"] = edit_ms

    path = save_telegram_env(values)
    print_success(f"Сохранено: {path}")

    if also_project_env or Confirm.ask("Также записать в .env текущего проекта?", default=False):
        proj_env = Path.cwd() / ".env"
        merge_project_env(proj_env, values)
        print_success(f"Обновлено: {proj_env.resolve()}")

    apply_to_environ(values)
    load_telegram_env_files()

    console.print()
    console.print(
        Panel(
            f"[cyan]Токен:[/cyan] {mask_token(token)}\n"
            f"[cyan]Allowlist:[/cyan] {allowed}\n"
            f"[cyan]Профиль:[/cyan] {profile}\n"
            f"[cyan]Файл:[/cyan] {TELEGRAM_ENV_PATH}",
            title="Готово",
            border_style="green",
        )
    )

    if skip_start:
        print_info("Запуск: helix telegram")
        return

    if Confirm.ask("Запустить бота сейчас?", default=False):
        from integrations.telegram.main import run_bot

        print_info("Остановка: Ctrl+C")
        await run_bot(profile)


def show_telegram_status() -> None:
    load_telegram_env_files()
    from integrations.telegram.config import load_telegram_settings

    settings = load_telegram_settings()
    path = TELEGRAM_ENV_PATH if TELEGRAM_ENV_PATH.is_file() else None
    console.print()
    if not settings.bot_token.strip():
        print_warning("Telegram не настроен. Запустите: helix telegram setup")
        return

    lines = [
        f"[cyan]Токен:[/cyan] {mask_token(settings.bot_token)}",
        f"[cyan]Allowlist:[/cyan] {settings.allowed_user_ids or '(пусто — не рекомендуется)'}",
        f"[cyan]Профиль:[/cyan] {settings.profile}",
        f"[cyan]Конфиг:[/cyan] {path or 'только env'}",
    ]
    console.print(Panel("\n".join(lines), title="Telegram", border_style="cyan"))