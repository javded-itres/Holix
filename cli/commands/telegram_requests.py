"""``holix telegram requests`` — approve Telegram users who sent /start."""

from __future__ import annotations

from integrations.telegram.access_requests import (
    STATUS_PENDING,
    get_access_request,
    list_pending_requests,
    reject_access_request,
    resolve_access_request,
)
from integrations.telegram.allowlist import add_allowed_user
from integrations.telegram.env_store import load_telegram_env_files
from integrations.telegram.user_profiles import set_user_profile
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


def _prepare_profile_for_user(
    manager: ProfileManager,
    target_profile: str,
    *,
    create_new: bool,
    bot_profile: str,
) -> tuple[str | None, bool]:
    """Create or protect profile; return (access_key_plaintext, key_already_set)."""
    from core.profile_keys import profile_has_access_key, store_profile_access_key

    from cli.core import enable_profile_workspace_isolation, validate_profile_name_for_env

    target_profile = validate_profile_name_for_env(target_profile)
    access_key: str | None = None
    key_already_set = False

    if create_new:
        if manager.profile_exists(target_profile):
            print_warning(f"Профиль '{target_profile}' уже существует — используем его")
            if profile_has_access_key(target_profile):
                key_already_set = True
            else:
                access_key = store_profile_access_key(target_profile)
                workspace = enable_profile_workspace_isolation(manager, target_profile)
                print_info(f"Workspace jail: {workspace}")
        else:
            manager.create_profile(target_profile, with_access_key=True)
            access_key = manager.pop_last_created_access_key()
            workspace = manager.get_profile_dir(target_profile) / "workspace"
            print_success(f"Создан защищённый профиль '{target_profile}'")
            print_info(f"Изолированная директория: {workspace}")
        return access_key, key_already_set

    if not manager.profile_exists(target_profile):
        print_error(f"Профиль '{target_profile}' не найден.")
        print_info(f"Создать: holix profile create {target_profile}")
        print_info(
            f"Или: holix -p {bot_profile} telegram requests approve … --create-profile NAME"
        )
        raise SystemExit(1)

    return None, profile_has_access_key(target_profile)


def _profiles_list() -> list[str]:
    try:
        return ProfileManager().list_profiles() or ["default"]
    except Exception:
        return ["default"]


def telegram_requests_list(bot_profile: str) -> None:
    load_telegram_env_files(bot_profile)
    pending = list_pending_requests(bot_profile)
    console.print()
    if not pending:
        print_info("Нет ожидающих запросов. Пользователь должен отправить /start боту.")
        print_info(f"Проверка: holix -p {bot_profile} telegram requests list")
        return

    table = Table(title=f"Запросы доступа Telegram (бот: {bot_profile})")
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
    print_info("Одобрить:")
    print_info(
        f"  holix -p {bot_profile} telegram requests approve USER_ID --profile PROFILE"
    )
    print_info(
        f"  holix -p {bot_profile} telegram requests approve USER_ID --create-profile NAME"
    )
    print_info(
        f"  holix -p {bot_profile} telegram requests approve USER_ID --set-admin"
    )
    print_info("  (--create-profile создаёт защищённый профиль и шлёт ключ в Telegram)")
    print_info("  (--set-admin — первый администратор, профиль Holix admin; только CLI)")


def telegram_requests_approve(
    bot_profile: str,
    user_id: int,
    *,
    profile: str | None = None,
    create_profile: str | None = None,
    interactive: bool = False,
    set_admin: bool = False,
) -> None:
    from integrations.telegram.admin import (
        load_admin_holix_profile,
        load_admin_user_id,
        set_admin_user,
    )

    load_telegram_env_files(bot_profile)
    req = get_access_request(bot_profile, user_id)
    if req is None or req.status != STATUS_PENDING:
        print_error(f"Нет ожидающего запроса для user id {user_id}.")
        print_info(f"Список: holix -p {bot_profile} telegram requests list")
        raise SystemExit(1)

    if set_admin:
        if profile or create_profile:
            print_error("--set-admin нельзя сочетать с --profile или --create-profile.")
            raise SystemExit(1)
        existing_admin = load_admin_user_id(bot_profile)
        if existing_admin is not None and int(existing_admin) != int(user_id):
            print_error(
                f"Администратор уже назначен (user id {existing_admin}). "
                "Смена: holix telegram admin clear, затем approve с --set-admin."
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
        profiles = _profiles_list()
        console.print()
        console.print(
            f"[cyan]Пользователь:[/cyan] {req.display_name} "
            f"(id={req.user_id})"
        )
        if Confirm.ask("Создать новый профиль Holix для этого пользователя?", default=False):
            target_profile = Prompt.ask("Имя нового профиля").strip()
        else:
            if len(profiles) == 1:
                target_profile = profiles[0]
            else:
                console.print("[dim]Профили:[/dim] " + ", ".join(profiles))
                target_profile = Prompt.ask(
                    "Профиль Holix",
                    default=bot_profile,
                ).strip()

    if not target_profile:
        print_error("Укажите --profile или --create-profile (или запустите без флагов для мастера).")
        raise SystemExit(1)

    manager = ProfileManager()
    if set_admin and not manager.profile_exists(target_profile):
        manager.create_profile(target_profile, inherit_global=True)
        print_success(f"Создан профиль администратора '{target_profile}'")

    access_key, key_already_set = _prepare_profile_for_user(
        manager,
        target_profile,
        create_new=bool(create_profile) and not set_admin,
        bot_profile=bot_profile,
    )

    if set_admin:
        set_admin_user(bot_profile, user_id, holix_profile=target_profile)

    add_allowed_user(bot_profile, user_id)
    set_user_profile(bot_profile, user_id, target_profile)
    resolve_access_request(
        bot_profile,
        user_id,
        status="approved",
        holix_profile=target_profile,
    )

    try:
        from integrations.telegram.notify import notify_access_approved_sync
        from integrations.telegram.setup_api import TelegramApiError

        notify_access_approved_sync(
            bot_profile,
            user_id,
            target_profile,
            access_key=access_key,
            key_already_set=key_already_set and not access_key,
        )
    except TelegramApiError as exc:
        print_warning(f"Не удалось отправить сообщение в Telegram: {exc}")
        if access_key:
            print_info(f"Передайте ключ пользователю вручную: {access_key}")
    except Exception as exc:
        print_warning(f"Уведомление в Telegram не отправлено: {exc}")
        if access_key:
            print_info(f"Ключ профиля: {access_key}")

    print_success(
        f"Доступ одобрен: {req.display_name} (id={user_id}) → профиль '{target_profile}'"
    )
    if set_admin:
        print_success(
            f"Назначен Telegram-администратор (user id={user_id}, профиль '{target_profile}')"
        )
        print_info("Новые запросы доступа будут приходить этому пользователю в Telegram.")
    if access_key:
        print_info("Ключ профиля отправлен пользователю в Telegram.")
    print_info("Пользователь может снова отправить /start или написать боту.")


def telegram_requests_reject(bot_profile: str, user_id: int) -> None:
    load_telegram_env_files(bot_profile)
    req = reject_access_request(bot_profile, user_id)
    if req is None:
        print_error(f"Нет ожидающего запроса для user id {user_id}.")
        raise SystemExit(1)
    print_success(f"Запрос отклонён: {req.display_name} (id={user_id})")