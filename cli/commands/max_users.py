"""``holix max users`` — list and fully remove MAX users."""

from __future__ import annotations

from integrations.max.env_store import load_max_env_files
from integrations.max.user_removal import list_known_user_ids, remove_max_user
from rich.table import Table

from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


def max_users_list(bot_profile: str) -> None:
    load_max_env_files(bot_profile)
    users = list_known_user_ids(bot_profile)
    console.print()
    if not users:
        print_warning("Пользователей нет (allowlist, привязки, запросы).")
        return

    table = Table(title=f"MAX-пользователи (бот: {bot_profile})")
    table.add_column("User ID", style="cyan")
    table.add_column("Профиль", style="green")
    table.add_column("Allowlist", style="dim")
    table.add_column("Запрос", style="dim")
    table.add_column("Роль", style="yellow")
    for uid, meta in sorted(users.items()):
        table.add_row(
            str(uid),
            meta.get("profile", "—"),
            "да" if meta.get("allowlist") == "yes" else "—",
            meta.get("request_status", "—"),
            "admin" if meta.get("admin") == "yes" else "—",
        )
    console.print(table)


def max_users_remove(
    bot_profile: str,
    user_id: int,
    *,
    notify: bool = True,
    force_admin: bool = False,
) -> None:
    load_max_env_files(bot_profile)
    try:
        result = remove_max_user(
            bot_profile,
            user_id,
            notify=notify,
            force_admin=force_admin,
        )
    except ValueError as exc:
        print_error(str(exc))
        if "administrator" in str(exc).lower():
            print_info(
                f"Снять админа: holix -p {bot_profile} max admin clear\n"
                f"Или: holix -p {bot_profile} max users remove {user_id} --force-admin"
            )
        raise SystemExit(1) from exc

    print_success(result.message)
    removed_bits = []
    if result.removed_allowlist:
        removed_bits.append("allowlist")
    if result.removed_mapping:
        removed_bits.append("привязка")
    if result.removed_access_request:
        removed_bits.append("запрос доступа")
    if result.cleared_admin:
        removed_bits.append("администратор")
    if removed_bits:
        print_info("Удалено: " + ", ".join(removed_bits))
    if result.notified:
        print_info("Пользователь уведомлён в MAX.")