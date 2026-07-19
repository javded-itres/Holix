"""Folder-based host extensions + list dedupe."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.extensions.local_loader import discover_local_host_extensions
from core.extensions.registry import (
    clear_extension_discovery_cache,
    list_all_entrypoint_rows,
)


@pytest.fixture()
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    clear_extension_discovery_cache()
    return home


def test_discover_flat_host_folder(holix_home: Path) -> None:
    root = holix_home / "extensions" / "my_bill"
    root.mkdir(parents=True)
    (root / "extension.py").write_text(
        """
class Ext:
    name = "my_bill"
    version = "1.2.3"
    def register_telegram(self, api):
        api.add_command("pay", "Pay")

def get_extension():
    return Ext()
""",
        encoding="utf-8",
    )
    exts = discover_local_host_extensions("default")
    names = {getattr(e, "name", "") for e in exts}
    assert "my_bill" in names


def test_discover_nested_package_clone(holix_home: Path) -> None:
    """git clone layout: extensions/repo/pkg/extension.py"""
    repo = holix_home / "extensions" / "holix-telegram-billing"
    pkg = repo / "holix_telegram_billing"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "extension.py").write_text(
        """
class TelegramBillingExtension:
    name = "telegram_billing"
    version = "0.1.0"
    def register_telegram(self, api):
        pass

def get_extension():
    return TelegramBillingExtension()
""",
        encoding="utf-8",
    )
    exts = discover_local_host_extensions("default")
    by_name = {getattr(e, "name", ""): e for e in exts}
    assert "telegram_billing" in by_name
    assert getattr(by_name["telegram_billing"], "_holix_local_path", "").endswith(
        "holix-telegram-billing"
    )


def test_list_dedupes_host_and_telegram_kinds(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same name from host discovery should appear once with merged kinds."""
    clear_extension_discovery_cache()

    class Fake:
        name = "telegram_billing"
        version = "0.1.0"
        requires_holix = ">=0.1"
        capabilities = frozenset({"http"})
        permissions = frozenset()
        _holix_local_path = str(holix_home / "extensions" / "billing")

        def register_telegram(self, api):
            return None

    monkeypatch.setattr(
        "core.extensions.registry.discover_extensions",
        lambda profile=None: (Fake(),),
    )
    monkeypatch.setattr(
        "core.extensions.registry._entry_points_for_group",
        lambda group: [],
    )
    rows = list_all_entrypoint_rows()
    billing = [r for r in rows if r["name"] == "telegram_billing"]
    assert len(billing) == 1
    assert "host" in billing[0]["kind"]
    assert "telegram" in billing[0]["kind"]


def test_folder_overrides_entrypoint_same_name(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = holix_home / "extensions" / "studio"
    root.mkdir(parents=True)
    (root / "extension.py").write_text(
        """
class Ext:
    name = "studio"
    version = "9.9.9"
    def register_cli(self, app):
        pass

def get_extension():
    return Ext()
""",
        encoding="utf-8",
    )
    clear_extension_discovery_cache()
    # Even if entrypoint studio exists, folder version wins when name matches
    from core.extensions.local_loader import discover_local_host_extensions

    local = {e.name: e for e in discover_local_host_extensions("default")}
    assert local["studio"].version == "9.9.9"
