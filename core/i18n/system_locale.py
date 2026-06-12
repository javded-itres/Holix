"""Detect OS locale and resolve install/bootstrap language."""

from __future__ import annotations

import locale
import os
import sys

from core.i18n.locale import DEFAULT_LOCALE, SUPPORTED_LOCALES, normalize_locale

_ENV_BOOTSTRAP_LANG = "HOLIX_BOOTSTRAP_LANG"


def _parse_lang_code(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value or value.lower() in {"c", "posix"}:
        return None
    code = value.replace("-", "_").split("_")[0].split(".")[0].lower()
    if code in SUPPORTED_LOCALES:
        return code
    return None


def detect_system_locale() -> str:
    """Best-effort OS UI language: ``ru`` or ``en`` (default)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        parsed = _parse_lang_code(os.environ.get(var, ""))
        if parsed:
            return parsed

    try:
        loc = locale.getlocale(locale.LC_MESSAGES)
        if loc and loc[0]:
            parsed = _parse_lang_code(loc[0])
            if parsed:
                return parsed
    except Exception:
        pass

    try:
        default = locale.getdefaultlocale()
        if default and default[0]:
            parsed = _parse_lang_code(default[0])
            if parsed:
                return parsed
    except Exception:
        pass

    return DEFAULT_LOCALE


def resolve_install_locale(
    *,
    explicit: str | None = None,
    interactive: bool | None = None,
) -> str:
    """Pick install/bootstrap locale.

    - Explicit ``--lang`` / ``HOLIX_BOOTSTRAP_LANG`` wins.
    - Russian system → ``ru`` without asking.
    - English (or unknown) system + TTY → ask EN/RU.
    - Otherwise → ``en``.
    """
    if explicit and str(explicit).strip():
        return normalize_locale(explicit)

    env_lang = os.environ.get(_ENV_BOOTSTRAP_LANG, "").strip()
    if env_lang:
        return normalize_locale(env_lang)

    system = detect_system_locale()
    if system == "ru":
        return "ru"

    is_interactive = interactive if interactive is not None else (sys.stdin.isatty() and sys.stdout.isatty())
    if not is_interactive:
        return DEFAULT_LOCALE

    from rich.prompt import Prompt

    print()
    print("Choose install language / Выберите язык установки:")
    print("  1) English")
    print("  2) Русский")
    choice = Prompt.ask("Language / Язык", default="1").strip().lower()

    if choice in {"2", "ru", "russian", "русский", "р"}:
        return "ru"
    return DEFAULT_LOCALE


def apply_profile_locale(locale: str, *profiles: str) -> None:
    """Persist UI locale for one or more Holix profiles."""
    from core.i18n.locale import LocaleStore

    loc = normalize_locale(locale)
    seen: set[str] = set()
    for name in profiles:
        profile = (name or "").strip()
        if not profile or profile in seen:
            continue
        seen.add(profile)
        try:
            from cli.core import init_profile

            init_profile(profile)
        except Exception:
            pass
        LocaleStore(profile).set(loc)