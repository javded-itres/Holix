"""Holix extension registry."""

from __future__ import annotations

from core.extensions.base import CAPABILITY_CLI, ExtensionBase
from core.extensions.registry import (
    ENTRYPOINT_GROUP,
    discover_extensions,
    list_extension_info,
    register_cli_extensions,
)


def test_extension_entrypoint_group_name() -> None:
    assert ENTRYPOINT_GROUP == "holix.extensions"


def test_discover_extensions_returns_tuple() -> None:
    discover_extensions.cache_clear()
    assert isinstance(discover_extensions(), tuple)


def test_builtin_telegram_and_max_extensions_discovered() -> None:
    discover_extensions.cache_clear()
    names = {ext.name for ext in discover_extensions()}
    assert "telegram" in names
    assert "max" in names


def test_list_extension_info_has_metadata() -> None:
    infos = list_extension_info()
    by_name = {i.name: i for i in infos}
    assert "telegram" in by_name
    tg = by_name["telegram"]
    assert tg.version
    assert CAPABILITY_CLI in tg.capabilities
    assert tg.package


def test_register_cli_extensions_accepts_typer() -> None:
    import typer

    root = typer.Typer()
    names = register_cli_extensions(root)
    assert "telegram" in names
    assert "max" in names


def test_extension_base_defaults() -> None:
    class EmptyExt(ExtensionBase):
        name = "empty"

    ext = EmptyExt()
    assert ext.version == "0.0.0"
    assert ext.capabilities == frozenset()
    assert ext.register_cli(None) is None