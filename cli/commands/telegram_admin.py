"""``helix telegram admin`` — view or clear the single Telegram administrator."""

from __future__ import annotations

from integrations.telegram.admin import (
    clear_admin_user,
    load_admin_helix_profile,
    load_admin_user_id,
)
from integrations.telegram.env_store import load_telegram_env_files

from cli.utils.rich_console import print_error, print_info, print_success, print_warning


def telegram_admin_show(bot_profile: str) -> None:
    load_telegram_env_files(bot_profile)
    admin_id = load_admin_user_id(bot_profile)
    if admin_id is None:
        print_warning("Telegram-администратор не назначен.")
        print_info(
            f"Назначить при первом approve: "
            f"helix -p {bot_profile} telegram requests approve USER_ID --set-admin"
        )
        return

    helix_profile = load_admin_helix_profile(bot_profile)
    print_success(f"Telegram admin: user id {admin_id}")
    print_info(f"Профиль Helix: {helix_profile}")
    print_info("Назначение и смена — только через CLI (не из Telegram).")


def telegram_admin_clear(bot_profile: str) -> None:
    load_telegram_env_files(bot_profile)
    if load_admin_user_id(bot_profile) is None:
        print_info("Администратор не был назначен.")
        return
    if not clear_admin_user(bot_profile):
        print_error("Не удалось сбросить администратора.")
        raise SystemExit(1)
    print_success("Telegram-администратор сброшен.")
    print_info(
        f"Назначить снова: helix -p {bot_profile} telegram requests approve USER_ID --set-admin"
    )