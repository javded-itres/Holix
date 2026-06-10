"""Helix UI internationalization (EN default, RU via /lang)."""

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

__all__ = [
    "DEFAULT_LOCALE",
    "LocaleStore",
    "SUPPORTED_LOCALES",
    "host_locale",
    "host_profile_name",
    "normalize_locale",
    "set_host_locale",
    "t",
]