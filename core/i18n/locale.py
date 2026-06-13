"""UI locale persistence (per Holix profile)."""

from __future__ import annotations

import json
from pathlib import Path

from cli.core import ProfileManager
from pydantic import BaseModel

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = frozenset({"en", "ru"})


class LocaleData(BaseModel):
    version: int = 1
    locale: str = DEFAULT_LOCALE


def locale_path(profile: str) -> Path:
    d = ProfileManager().get_profile_dir(profile) / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "locale.json"


class LocaleStore:
    """Read/write interface language for a profile."""

    def __init__(self, profile: str = "default") -> None:
        self.profile = profile
        self._path = locale_path(profile)

    def load(self) -> LocaleData:
        if not self._path.exists():
            return LocaleData()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return LocaleData.model_validate(data)
        except Exception:
            return LocaleData()

    def save(self, data: LocaleData) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    def get(self) -> str:
        loc = self.load().locale.strip().lower()
        return loc if loc in SUPPORTED_LOCALES else DEFAULT_LOCALE

    def set(self, locale: str) -> str:
        loc = locale.strip().lower()
        if loc not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale: {locale}")
        data = self.load()
        data.locale = loc
        self.save(data)
        return loc


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    loc = locale.strip().lower()
    return loc if loc in SUPPORTED_LOCALES else DEFAULT_LOCALE


def host_profile_name(host: object) -> str:
    return (
        getattr(host, "profile", None)
        or getattr(getattr(host, "_session", None), "profile", None)
        or "default"
    )


def host_locale(host: object) -> str:
    return LocaleStore(host_profile_name(host)).get()


def set_host_locale(host: object, locale: str) -> str:
    return LocaleStore(host_profile_name(host)).set(normalize_locale(locale))