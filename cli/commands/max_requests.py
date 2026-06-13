"""``holix max requests`` — approve MAX users who sent /start."""

from __future__ import annotations

from integrations.max.access_approval import (
    approve_access_request,
    reject_access_request_op,
)
from integrations.max.access_requests import STATUS_PENDING, list_pending_requests
from integrations.max.admin import load_admin_holix_profile, load_admin_user_id
from integrations.max.env_store import load_max_env_files
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success


def _profiles_list() -> list[str]:
    try:
        return ProfileManager().list_profiles() or ["default"]
    except Exception:
        return ["default"]


def max_requests_list(bot_profile: str) -> None:
    load_max_env_files(bot_profile)
    pending = list_pending_requests(bot_profile)
    console.print()
    if not pending:
        print_info("Нет ожидающих запросов. Пользователь должен отправить /start боту.")
        print_info(f"Проверка: holix -p {bot_profile} max requests list")
        return

    table = Table(title=f"Запросы доступа MAX (бот: {bot_profile})")
    table.add_column("User ID", style="cyan")
    table.add_column("Имя", style="green")
    table.add_column("Username")
    table.add_column("Запрошено")
    for req in pending:
        table.add_row(
            str(req.user_id),
            req.display_name,
            f"@{req.username}" if req.username else "—",
            req.requested_at or "—",
        )
    console.print(table)
    console.print()
    print_info("CLI:")
    print_info(
        f"  holix -p {bot_profile} max requests approve USER_ID --profile PROFILE"
    )
    print_info(
        f"  holix -p {bot_profile} max requests approve USER_ID --create-profile NAME"
    )


def max_requests_approve(
    bot_profile: str,
    user_id: int,
    *,
    profile: str | None = None,
    create_profile: str | None = None,
    interactive: bool = False,
    set_admin: bool = False,
) -> None:
    load_max_env_files(bot_profile)

    if set_admin:
        if profile or create_profile:
            print_error("--set-admin нельзя сочетать с --profile или --create-profile.")
            raise SystemExit(1)
        existing_admin = load_admin_user_id(bot_profile)
        if existing_admin is not None and int(existing_admin) != int(user_id):
            print_error(
                f"Администратор уже назначен (user id {existing_admin}). "
                "Смена: holix max admin clear, затем approve с --set-admin."
            )
            raise SystemExit(1)

    target_profile: str | None = None
    if set_admin:
        target_profile = load_admin_holix_profile(bot_profile)
    elif create_profile:
        target_profile = create_profile.strip()
    elif profile:
        target_profile = profile.strip()

    if target_profile is None and interactive:
        from integrations.max.access_requests import get_access_request

        req = get_access_request(bot_profile, user_id)
        if req is None or req.status != STATUS_PENDING:
            print_error(f"Нет ожидающего запроса для user id {user_id}.")
            raise SystemExit(1)
        profiles = _profiles_list()
        console.print()
        console.print(
            f"[cyan]Пользователь:[/cyan] {req.display_name} "
            f"(id={req.user_id})"
        )
        if Confirm.ask("Создать новый профиль Holix для этого пользователя?", default=False):
            target_profile = Prompt.ask("Имя нового профиля").strip()
            create_profile = target_profile
        else:
            if len(profiles) == 1:
                target_profile = profiles[0]
            else:
                console.print("[dim]Профили:[/dim] " + ", ".join(profiles))
                target_profile = Prompt.ask(
                    "Профиль Holix",
                    default=bot_profile,
                ).strip()

    if not target_profile and not set_admin and not create_profile:
        print_error("Укажите --profile или --create-profile (или запустите с -i).")
        raise SystemExit(1)

    if set_admin and not ProfileManager().profile_exists(load_admin_holix_profile(bot_profile)):
        ProfileManager().create_profile(load_admin_holix_profile(bot_profile), inherit_global=True)
        print_success(f"Создан профиль администратора '{load_admin_holix_profile(bot_profile)}'")

    try:
        result = approve_access_request(
            bot_profile,
            user_id,
            holix_profile=target_profile if not create_profile and not set_admin else None,
            create_profile=create_profile,
            set_admin=set_admin,
        )
    except ValueError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    print_success(result.message)
    if set_admin:
        print_success(
            f"Назначен MAX-администратор (user id={user_id}, "
            f"профиль '{load_admin_holix_profile(bot_profile)}')"
        )
    if result.access_key:
        print_info("Ключ профиля создан (уведомление в MAX — в следующих фазах).")


def max_requests_reject(bot_profile: str, user_id: int) -> None:
    load_max_env_files(bot_profile)
    try:
        result = reject_access_request_op(bot_profile, user_id)
    except ValueError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc
    print_success(result.message)