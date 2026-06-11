"""Interactive ``holix telegram setup`` wizard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from integrations.telegram.env_store import (
    apply_to_environ,
    load_telegram_env_files,
    mask_token,
    merge_project_env,
    read_telegram_env_values,
    save_telegram_env,
    telegram_env_path,
    token_looks_valid,
)
from integrations.telegram.setup_api import (
    TelegramApiError,
    verify_bot_token,
)
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


def _telegram_extra_installed() -> bool:
    try:
        import aiogram  # noqa: F401

        return True
    except ImportError:
        return False


def _install_telegram_extra() -> bool:
    uv = __import__("shutil").which("uv")
    cmd = (
        [uv, "sync", "--extra", "telegram"]
        if uv
        else [sys.executable, "-m", "pip", "install", "HelixAgentAi[telegram]"]
    )
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
            "2. Запустите бота — пользователи отправляют /start\n"
            "3. Одобрите доступ: [dim]holix telegram requests list[/dim] → "
            "[dim]holix telegram requests approve …[/dim]",
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

    manager = ProfileManager()
    profiles = manager.list_profiles() or ["default"]
    if profile is None:
        if len(profiles) == 1:
            profile = profiles[0]
        else:
            console.print("[dim]Профили Holix:[/dim] " + ", ".join(profiles))
            profile = Prompt.ask("Профиль Holix для бота", default="default")
    if profile not in profiles:
        print_warning(f"Профиль '{profile}' не найден — будет создан при первом запуске.")

    existing = read_telegram_env_values(profile)
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

    values = {
        "TELEGRAM_BOT_TOKEN": token,
        "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
    }
    allowed = existing.get("HOLIX_TELEGRAM_ALLOWED_USERS", "").strip()
    if allowed:
        values["HOLIX_TELEGRAM_ALLOWED_USERS"] = allowed.replace(" ", "")
    edit_ms = existing.get("HOLIX_TELEGRAM_EDIT_MS", "")
    if edit_ms:
        values["HOLIX_TELEGRAM_EDIT_MS"] = edit_ms

    path = save_telegram_env(values, profile=profile)
    print_success(f"Сохранено: {path}")

    if also_project_env or Confirm.ask("Также записать в .env текущего проекта?", default=False):
        proj_env = Path.cwd() / ".env"
        merge_project_env(proj_env, values)
        print_success(f"Обновлено: {proj_env.resolve()}")

    apply_to_environ(values)
    load_telegram_env_files(profile)

    console.print()
    console.print(
        Panel(
            f"[cyan]Токен:[/cyan] {mask_token(token)}\n"
            f"[cyan]Режим:[/cyan] запросы доступа (/start → approve в CLI)\n"
            f"[cyan]Профиль бота:[/cyan] {profile}\n"
            f"[cyan]Файл:[/cyan] {telegram_env_path(profile)}",
            title="Готово",
            border_style="green",
        )
    )
    print_info(f"Откройте https://t.me/{username} и отправьте /start")
    print_info(f"Затем: holix -p {profile} telegram requests list")

    if skip_start:
        print_info("Запуск: holix telegram")
        return

    if Confirm.ask("Запустить бота сейчас?", default=False):
        from integrations.telegram.main import run_bot

        print_info("Остановка: Ctrl+C")
        await run_bot(profile)


def show_telegram_status(profile: str = "default") -> None:
    load_telegram_env_files(profile)
    from integrations.telegram.config import load_telegram_settings

    settings = load_telegram_settings(profile)
    tg_path = telegram_env_path(profile)
    path = tg_path if tg_path.is_file() else None
    console.print()
    if not settings.bot_token.strip():
        print_warning("Telegram не настроен. Запустите: holix telegram setup")
        return

    from integrations.telegram.access_requests import list_pending_requests
    from integrations.telegram.admin import load_admin_holix_profile, load_admin_user_id
    from integrations.telegram.user_profiles import load_user_profiles, telegram_users_path

    admin_id = load_admin_user_id(profile)
    admin_line = (
        f"{admin_id} → {load_admin_holix_profile(profile)}"
        if admin_id is not None
        else "(не назначен — approve с --set-admin)"
    )
    mapping = load_user_profiles(profile)
    map_lines = ", ".join(f"{uid}→{name}" for uid, name in sorted(mapping.items())) if mapping else "(нет)"
    pending = list_pending_requests(profile)
    pending_line = str(len(pending)) if pending else "0"

    lines = [
        f"[cyan]Токен:[/cyan] {mask_token(settings.bot_token)}",
        f"[cyan]Запросы доступа:[/cyan] {'включены' if settings.access_requests else 'выключены'}",
        f"[cyan]Ожидают одобрения:[/cyan] {pending_line}",
        f"[cyan]Allowlist:[/cyan] {settings.allowed_user_ids or '(пусто — одобряйте через requests)'}",
        f"[cyan]Telegram admin:[/cyan] {admin_line}",
        f"[cyan]Профиль бота:[/cyan] {settings.profile}",
        f"[cyan]Привязки user→профиль:[/cyan] {map_lines}",
        f"[cyan]Конфиг:[/cyan] {path or 'только env'}",
        f"[cyan]Привязки файл:[/cyan] {telegram_users_path(profile)}",
    ]
    console.print(Panel("\n".join(lines), title="Telegram", border_style="cyan"))
    if pending:
        print_info(f"Одобрить: holix -p {profile} telegram requests list")