"""Holix UI internationalization (EN default, RU via /lang)."""

from core.i18n.locale import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    LocaleStore,
    host_locale,
    host_profile_name,
    normalize_locale,
    set_host_locale,
)
from core.i18n.messages import t
from core.i18n.system_locale import (
    apply_profile_locale,
    detect_system_locale,
    resolve_install_locale,
)

__all__ = [
    "apply_profile_locale",
    "detect_system_locale",
    "resolve_install_locale",
    "DEFAULT_LOCALE",
    "LocaleStore",
    "SUPPORTED_LOCALES",
    "host_locale",
    "host_profile_name",
    "normalize_locale",
    "set_host_locale",
    "t",
]