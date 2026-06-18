"""Default UI locale for Telegram and MAX messenger integrations."""

from __future__ import annotations

from core.i18n.locale import LocaleStore, locale_path

MESSENGER_DEFAULT_LOCALE = "ru"


def messenger_locale(profile: str) -> str:
    """Resolve UI language for a messenger session profile."""
    name = (profile or "default").strip() or "default"
    store = LocaleStore(name)
    if not store._path.exists():
        return MESSENGER_DEFAULT_LOCALE
    return store.get()


def apply_messenger_locale(profile: str, *, locale: str = MESSENGER_DEFAULT_LOCALE) -> str:
    """Persist messenger default locale for a profile (new user onboarding)."""
    return LocaleStore((profile or "default").strip() or "default").set(locale)


def ensure_messenger_locale(profile: str) -> str:
    """Set messenger default locale when the profile has no saved locale yet."""
    name = (profile or "default").strip() or "default"
    if locale_path(name).is_file():
        return LocaleStore(name).get()
    return apply_messenger_locale(name)


def messenger_host_locale(host: object) -> str:
    from core.i18n.locale import host_profile_name

    return messenger_locale(host_profile_name(host))


def bootstrap_messenger_locales(platform, bot_profile: str) -> list[str]:
    """Ensure RU locale for bot host, admin, and mapped users without locale.json."""
    from integrations.messenger.admin import load_admin_holix_profile
    from integrations.messenger.user_profiles import load_user_profiles

    bot_profile = (bot_profile or "default").strip() or "default"
    names: set[str] = {bot_profile}
    admin_profile = load_admin_holix_profile(platform, bot_profile)
    if admin_profile:
        names.add(admin_profile)
    for holix_profile in load_user_profiles(platform, bot_profile).values():
        names.add(holix_profile)

    updated: list[str] = []
    for name in sorted(names):
        if not locale_path(name).is_file():
            ensure_messenger_locale(name)
            updated.append(name)
    return updated