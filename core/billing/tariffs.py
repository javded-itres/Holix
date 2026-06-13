"""Tariff → workspace quota mapping (billing integration stub)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TARIFF_ID = "free"


@dataclass(frozen=True, slots=True)
class TariffLimits:
    tariff_id: str
    workspace_max_bytes: int
    workspace_max_files: int


_TARIFFS: dict[str, TariffLimits] = {
    "free": TariffLimits("free", 100 * 1024 * 1024, 5_000),
    "basic": TariffLimits("basic", 1024 * 1024 * 1024, 50_000),
    "pro": TariffLimits("pro", 10 * 1024 * 1024 * 1024, 500_000),
}


def default_tariff_id() -> str:
    return DEFAULT_TARIFF_ID


def limits_for_tariff(tariff_id: str) -> TariffLimits:
    key = (tariff_id or "").strip().lower() or DEFAULT_TARIFF_ID
    return _TARIFFS.get(key, _TARIFFS[DEFAULT_TARIFF_ID])