"""Interactive ``helix max setup`` wizard."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning
from integrations.max.env_store import (
    apply_to_environ,
    load_max_env_files,
    mask_token,
    merge_project_env,
    read_max_env_values,
    save_max_env,
    token_looks_valid,
)
from integrations.max.setup_api import MaxApiError, verify_access_token, wait_for_max_user


async def run_max_setup(
    *,
    profile: str | None = None,
    also_project_env: bool = False,
    skip_start: bool = False,
) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]MAX — подключение бота[/bold cyan]\n\n"
            "1. [business.max.ru](https://business.max.ru/self) → Чат-боты → Интеграция → токен\n"
            "2. Узнайте user id (авто-определение ниже или вручную)\n"
            "3. Настройки сохраняются в [dim]~/.holix/profiles/PROFILE/max.env[/dim]",
            border_style="cyan",
        )
    )

    profile_name = (profile or "default").strip() or "default"
    existing = read_max_env_values(profile_name)
    default_token = existing.get("MAX_ACCESS_TOKEN", "")
    if default_token and Confirm.ask("Использовать сохранённый токен?", default=True):
        token = default_token
    else:
        token = Prompt.ask(
            "Access token бота MAX",
            password=True,
            default=default_token or "",
        ).strip()

    if not token_looks_valid(token):
        print_error("Неверный формат токена (ожидается непустая строка ≥16 символов).")
        raise SystemExit(1)

    print_info("Проверка токена (GET /me)…")
    try:
        me = await verify_access_token(token)
    except MaxApiError as e:
        print_error(f"MAX API: {e}")
        raise SystemExit(1) from e

    username = me.get("username") or me.get("name") or "bot"
    print_success(f"Бот подключён: @{username} (user_id={me.get('user_id')})")

    allowed_default = existing.get(
        "HOLIX_MAX_ALLOWED_USERS",
        existing.get("HELIX_MAX_ALLOWED_USERS", ""),
    )
    allowed = Prompt.ask(
        "Ваш MAX user id (число, можно несколько через запятую)",
        default=allowed_default,
    ).strip()

    if not allowed and Confirm.ask(
        "Определить user id автоматически? (напишите боту в MAX)",
        default=True,
    ):
        print_info("Откройте бота в MAX и отправьте любое сообщение…")
        detected = await wait_for_max_user(token, timeout_s=90.0)
        if detected is not None:
            allowed = str(detected)
            print_success(f"Найден user id: {detected}")
        else:
            print_warning("Не получено событий за 90 с. Введите id вручную.")
            allowed = Prompt.ask("MAX user id").strip()

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
            profile = Prompt.ask(
                "Профиль Holix для бота",
                default=existing.get(
                    "HOLIX_MAX_PROFILE",
                    existing.get("HELIX_MAX_PROFILE", "default"),
                ),
            )
    if profile not in profiles:
        print_warning(f"Профиль '{profile}' не найден — будет создан при первом запуске.")

    mode_default = existing.get("HOLIX_MAX_MODE", existing.get("HELIX_MAX_MODE", "polling"))
    mode = Prompt.ask("Режим (polling / webhook)", default=mode_default).strip().lower()
    if mode not in {"polling", "webhook"}:
        print_error("Режим должен быть polling или webhook.")
        raise SystemExit(1)

    values: dict[str, str] = {
        "MAX_ACCESS_TOKEN": token,
        "HOLIX_MAX_ALLOWED_USERS": allowed.replace(" ", ""),
        "HOLIX_MAX_PROFILE": profile,
        "HOLIX_MAX_MODE": mode,
        "HOLIX_MAX_ACCESS_REQUESTS": "true",
    }
    if mode == "webhook":
        webhook_url = existing.get(
            "HOLIX_MAX_WEBHOOK_URL",
            existing.get("HELIX_MAX_WEBHOOK_URL", ""),
        )
        webhook_url = Prompt.ask("Webhook URL (HTTPS)", default=webhook_url).strip()
        if webhook_url:
            values["HOLIX_MAX_WEBHOOK_URL"] = webhook_url
        secret = existing.get(
            "HOLIX_MAX_WEBHOOK_SECRET",
            existing.get("HELIX_MAX_WEBHOOK_SECRET", ""),
        )
        secret = Prompt.ask("Webhook secret (X-Max-Bot-Api-Secret)", default=secret).strip()
        if secret:
            values["HOLIX_MAX_WEBHOOK_SECRET"] = secret

    path = save_max_env(values, profile=profile)
    print_success(f"Сохранено: {path}")

    if also_project_env or Confirm.ask("Также записать в .env текущего проекта?", default=False):
        proj_env = Path.cwd() / ".env"
        merge_project_env(proj_env, values)
        print_success(f"Обновлено: {proj_env.resolve()}")

    apply_to_environ(values)
    load_max_env_files(profile)

    console.print()
    console.print(
        Panel(
            f"[cyan]Токен:[/cyan] {mask_token(token)}\n"
            f"[cyan]Allowlist:[/cyan] {allowed}\n"
            f"[cyan]Профиль:[/cyan] {profile}\n"
            f"[cyan]Режим:[/cyan] {mode}\n"
            f"[cyan]Файл:[/cyan] {path}",
            title="Готово",
            border_style="green",
        )
    )

    if skip_start:
        print_info("Запуск: helix max  (или helix gateway start для webhook)")
        return

    if mode == "webhook":
        print_info("Webhook: helix gateway start")
        return

    if Confirm.ask("Запустить бота сейчас (Long Polling)?", default=False):
        from integrations.max.main import run_bot

        print_info("Остановка: Ctrl+C")
        await run_bot(profile)


async def _fetch_subscription_lines(token: str) -> list[str]:
    from integrations.max.client import MaxApiError, MaxClient

    try:
        async with MaxClient(token) as client:
            subs = await client.list_subscriptions()
    except MaxApiError as exc:
        return [f"[yellow]Подписки:[/yellow] ошибка API ({exc})"]

    if not subs:
        return ["[cyan]Подписки:[/cyan] (нет активных webhook)"]
    out = ["[cyan]Подписки:[/cyan]"]
    for sub in subs:
        url = sub.get("url") or sub.get("endpoint") or "?"
        out.append(f"  • {url}")
    return out


def show_max_status(profile: str = "default") -> None:
    load_max_env_files(profile)
    from integrations.max.config import load_max_settings
    from integrations.max.env_store import max_env_path

    settings = load_max_settings(profile)
    path = max_env_path(profile) if max_env_path(profile).is_file() else None
    console.print()
    if not settings.access_token.strip():
        print_warning("MAX не настроен. Запустите: helix max setup")
        return

    lines = [
        f"[cyan]Токен:[/cyan] {mask_token(settings.access_token)}",
        f"[cyan]Allowlist:[/cyan] {settings.allowed_user_ids or '(пусто — не рекомендуется)'}",
        f"[cyan]Профиль:[/cyan] {settings.profile}",
        f"[cyan]Режим:[/cyan] {settings.mode}",
        f"[cyan]Poll timeout:[/cyan] {settings.poll_timeout_s}s",
        f"[cyan]Webhook URL:[/cyan] {settings.webhook_url or '(не задан)'}",
        f"[cyan]Конфиг:[/cyan] {path or 'только env'}",
    ]
    lines.extend(asyncio.run(_fetch_subscription_lines(settings.access_token)))
    console.print(Panel("\n".join(lines), title="MAX", border_style="cyan"))