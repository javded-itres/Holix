"""CLI startup should not pull chromadb for lightweight commands (e.g. bootstrap)."""

from __future__ import annotations

import builtins
import importlib

import pytest


def test_bootstrap_argv_skips_heavy_modules() -> None:
    from cli.main import _needs_heavy_commands

    assert not _needs_heavy_commands(["bootstrap", "-y"])
    assert not _needs_heavy_commands(["install"])
    assert not _needs_heavy_commands(["doctor"])
    assert not _needs_heavy_commands(["--help"])
    assert _needs_heavy_commands(["chat"])
    assert _needs_heavy_commands(["run", "hello"])
    assert _needs_heavy_commands(["skills", "list"])
    assert _needs_heavy_commands(["memory", "search", "test"])


def test_register_bootstrap_without_chromadb(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__
    chromadb_hits: list[str] = []

    def tracking_import(
        name: str,
        globals=None,
        locals=None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if name == "chromadb" or name.startswith("chromadb."):
            chromadb_hits.append(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", tracking_import)

    import cli.main as main_mod

    importlib.reload(main_mod)
    main_mod._register_commands(["bootstrap", "--help"])
    assert chromadb_hits == []