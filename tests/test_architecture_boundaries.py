"""Architecture boundary guards: core must not depend on outer packages.

See docs (en/ru) ARCHITECTURE.md — Target layering.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

FORBIDDEN_ROOTS = ("cli", "api", "integrations")

# Empty after PR-5/6/hooks: new violations fail CI.
ALLOWLIST: frozenset[str] = frozenset()


def _iter_core_py_files() -> list[Path]:
    return sorted(p for p in CORE.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                modules.append(node.module)
    return modules


def _is_forbidden(module: str) -> str | None:
    top = module.split(".", 1)[0]
    if top in FORBIDDEN_ROOTS:
        return module
    return None


def test_no_unexpected_core_to_outer_imports() -> None:
    violations: list[str] = []

    for path in _iter_core_py_files():
        rel = path.relative_to(ROOT).as_posix()
        for mod in _imported_modules(path):
            forbidden = _is_forbidden(mod)
            if not forbidden:
                continue
            key = f"{rel}:{forbidden}"
            allowed = False
            for entry in ALLOWLIST:
                file_part, mod_part = entry.split(":", 1)
                if rel == file_part and (
                    forbidden == mod_part or forbidden.startswith(mod_part + ".")
                ):
                    allowed = True
                    break
            if not allowed:
                violations.append(key)

    if violations:
        detail = "\n".join(f"  - {v}" for v in sorted(violations))
        pytest.fail(
            "core imports outer packages (cli/api/integrations):\n"
            f"{detail}\n"
            "Register outer behavior via core.plugins hooks or move code to outer packages."
        )


def test_core_does_not_import_api_package() -> None:
    hits: list[str] = []
    for path in _iter_core_py_files():
        for mod in _imported_modules(path):
            if mod == "api" or mod.startswith("api."):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{mod}")
    assert not hits, "core must not import api:\n" + "\n".join(hits)


def test_core_does_not_import_cli_package() -> None:
    hits: list[str] = []
    for path in _iter_core_py_files():
        for mod in _imported_modules(path):
            if mod == "cli" or mod.startswith("cli."):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{mod}")
    assert not hits, "core must not import cli:\n" + "\n".join(hits)
