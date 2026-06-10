"""``helix telegram map`` — bind Telegram user ids to Helix profiles."""

from __future__ import annotations

from integrations.telegram.env_store import load_telegram_env_files, read_telegram_env_values
from integrations.telegram.user_profiles import (
    ENV_KEY,
    format_user_profiles_text,
    load_user_profiles,
    remove_user_profile,
    set_user_profile,
    telegram_users_path,
    validate_user_profiles_text,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import ProfileManager
from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


def _profiles_list() -> list[str]:
    try:
        return ProfileManager().list_profiles() or ["default"]
    except Exception:
        return ["default"]


def _pick_profile(prompt: str, default: str) -> str:
    profiles = _profiles_list()
    if len(profiles) == 1:
        return profiles[0]
    console.print("[dim]Профили:[/dim] " + ", ".join(profiles))
    choice = Prompt.ask(prompt, default=default)
    return choice.strip() or default


def telegram_map_list(bot_profile: str) -> None:
    load_telegram_env_files(bot_profile)
    mapping = load_user_profiles(bot_profile)
    path = telegram_users_path(bot_profile)
    console.print()
    if not mapping:
        print_warning("Привязок нет.")
        print_info(f"Добавить: helix -p {bot_profile} telegram map set USER_ID PROFILE")
        print_info(f"Файл: {path}")
        return

    table = Table(title=f"Telegram → профиль (бот: {bot_profile})")
    table.add_column("User ID", style="cyan")
    table.add_column("Профиль Helix", style="green")
    for uid, name in sorted(mapping.items()):
        table.add_row(str(uid), name)
    console.print(table)
    print_info(f"Файл: {path}")
    env_val = read_telegram_env_values(bot_profile).get(ENV_KEY, "")
    if env_val:
        print_info(f"{ENV_KEY}={env_val}")


def telegram_map_set(bot_profile: str, user_id: int, profile: str) -> None:
    profiles = _profiles_list()
    profile = profile.strip()
    if profile not in profiles:
        print_warning(f"Профиль '{profile}' не найден — будет создан при первом использовании.")
    path = set_user_profile(bot_profile, user_id, profile)
    print_success(f"Привязка: {user_id} → {profile}")
    print_info(f"Сохранено: {path}")


def telegram_map_remove(bot_profile: str, user_id: int) -> None:
    path = remove_user_profile(bot_profile, user_id)
    if path is None:
        print_warning(f"Привязка для user id {user_id} не найдена.")
        raise SystemExit(1)
    print_success(f"Удалена привязка user id {user_id}")
    print_info(f"Обновлено: {path}")


def telegram_map_bind(bot_profile: str, profile: str, *, user_id: int | None = None) -> None:
    """Bind one user id to a profile (interactive if user_id omitted)."""
    load_telegram_env_files(bot_profile)
    allowed_raw = read_telegram_env_values(bot_profile).get("HELIX_TELEGRAM_ALLOWED_USERS", "")
    allowed = [p.strip() for p in allowed_raw.replace(" ", "").split(",") if p.strip().isdigit()]

    if user_id is None:
        if len(allowed) == 1:
            user_id = int(allowed[0])
            print_info(f"User id из allowlist: {user_id}")
        else:
            hint = allowed_raw or "(пусто)"
            user_id_s = Prompt.ask(
                "Telegram user id (число)",
                default=allowed[0] if allowed else "",
            ).strip()
            if not user_id_s.isdigit():
                print_error(f"Нужен numeric user id. Allowlist: {hint}")
                raise SystemExit(1)
            user_id = int(user_id_s)

    profile = profile.strip() or _pick_profile("Профиль Helix для этого user id", "default")
    telegram_map_set(bot_profile, user_id, profile)


def run_telegram_map_setup(bot_profile: str) -> None:
    """Optional wizard step: map allowlisted users to Helix profiles."""
    load_telegram_env_files(bot_profile)
    allowed_raw = read_telegram_env_values(bot_profile).get("HELIX_TELEGRAM_ALLOWED_USERS", "")
    user_ids = [int(p) for p in allowed_raw.replace(" ", "").split(",") if p.strip().isdigit()]
    if not user_ids:
        return

    profiles = _profiles_list()
    if len(profiles) <= 1 and len(user_ids) <= 1:
        return

    console.print()
    if not Confirm.ask(
        "Привязать Telegram user id к профилям Helix? (один бот — разные профили)",
        default=True,
    ):
        return

    existing = load_user_profiles(bot_profile)
    for uid in user_ids:
        current = existing.get(uid, "")
        default_profile = current or (profiles[0] if len(profiles) == 1 else bot_profile)
        profile = Prompt.ask(
            f"User id [cyan]{uid}[/cyan] → профиль Helix",
            default=default_profile,
        ).strip()
        if profile:
            set_user_profile(bot_profile, uid, profile)

    console.print()
    telegram_map_list(bot_profile)


def run_telegram_map_import(bot_profile: str, text: str) -> None:
    err = validate_user_profiles_text(text)
    if err:
        print_error(err)
        raise SystemExit(1)
    from integrations.telegram.user_profiles import parse_user_profiles_text, save_user_profiles

    mapping = parse_user_profiles_text(text)
    if not mapping:
        print_error("Пустой список привязок.")
        raise SystemExit(1)
    path = save_user_profiles(bot_profile, mapping)
    print_success(f"Импортировано {len(mapping)} привязок")
    print_info(format_user_profiles_text(mapping))
    print_info(f"Сохранено: {path}")