"""Discover extensions from Holix folders (no pip install required).

Supported layouts (any of)::

    ~/.holix/extensions/<name>/
        extension.py          # get_extension()  — host / telegram
        agent.py              # get_agent_extension() — agent tools
        holix.plugin.json

    ~/.holix/extensions/<repo-clone>/
        holix_telegram_billing/extension.py   # nested package (git clone)
        pyproject.toml

    ~/.holix/profiles/<profile>/extensions/<name>/
        ... same ...

Removing the folder unloads the extension on next Holix / bot start.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENTRY_FILES = ("extension.py", "agent.py", "__init__.py")


def global_extensions_dir() -> Path:
    from core.env_loader import holix_home

    return holix_home() / "extensions"


def profile_extensions_dir(profile: str) -> Path:
    from core.profile.names import profile_dir_for_name

    return profile_dir_for_name(profile) / "extensions"


def iter_extension_roots(profile: str | None = None) -> list[Path]:
    roots: list[Path] = []
    global_root = global_extensions_dir()
    if global_root.is_dir():
        roots.append(global_root)
    if profile:
        prof_root = profile_extensions_dir(profile)
        if prof_root.is_dir():
            roots.append(prof_root)
    return roots


def _ensure_path(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _load_module_from_file(module_name: str, path: Path, *, package_roots: list[Path] | None = None) -> Any | None:
    try:
        for root in package_roots or []:
            _ensure_path(root)
        # Parent of entry file is on path for sibling imports
        _ensure_path(path.parent)
        # If parent is a package dir, also add grandparent (repo root)
        if (path.parent / "__init__.py").is_file():
            _ensure_path(path.parent.parent)

        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        # Nested package (repo/pkg/extension.py): allow `from pkg.x import …`
        if (path.parent / "__init__.py").is_file() and path.name != "__init__.py":
            pkg = path.parent.name
            mod.__package__ = pkg
            # Register under real package name too (do not rename before exec_module)
            sys.modules.setdefault(f"{pkg}.{path.stem}", mod)
            if pkg not in sys.modules:
                # Minimal parent package
                import types

                parent = types.ModuleType(pkg)
                parent.__path__ = [str(path.parent.resolve())]  # type: ignore[attr-defined]
                sys.modules[pkg] = parent
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        logger.exception("failed to import local extension module %s", path)
        return None


def _call_factory(mod: Any, names: tuple[str, ...]) -> Any | None:
    for fname in names:
        factory = getattr(mod, fname, None)
        if not callable(factory):
            continue
        try:
            return factory()
        except Exception:
            logger.exception("%s() failed in %s", fname, getattr(mod, "__file__", "?"))
    return None


def _instantiate_agent_from_module(mod: Any, folder_name: str) -> Any | None:
    ext = _call_factory(mod, ("get_agent_extension",))
    if ext is not None:
        if not getattr(ext, "name", ""):
            ext.name = folder_name
        return ext
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name, None)
        if not isinstance(obj, type) or attr_name.startswith("_"):
            continue
        if attr_name in ("AgentExtensionBase", "AgentExtension", "ExtensionBase"):
            continue
        if not hasattr(obj, "register_tools"):
            continue
        try:
            inst = obj()
            if not getattr(inst, "name", ""):
                inst.name = folder_name
            return inst
        except Exception:
            continue
    return None


def _instantiate_host_from_module(mod: Any, folder_name: str) -> Any | None:
    ext = _call_factory(mod, ("get_extension", "get_host_extension", "get_telegram_extension"))
    if ext is not None:
        if not getattr(ext, "name", ""):
            ext.name = folder_name
        return ext
    # Class with host-ish hooks
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name, None)
        if not isinstance(obj, type) or attr_name.startswith("_"):
            continue
        if attr_name in ("ExtensionBase", "HolixExtension", "AgentExtensionBase"):
            continue
        hooks = ("register_cli", "mount_gateway", "register_telegram", "on_startup")
        if not any(hasattr(obj, h) for h in hooks):
            continue
        # Prefer classes that look like product extensions
        try:
            inst = obj()
            if not getattr(inst, "name", ""):
                inst.name = folder_name
            return inst
        except Exception:
            continue
    return None


def _find_entry_files(folder: Path) -> list[Path]:
    """Locate extension entry modules under a folder (flat or nested package)."""
    found: list[Path] = []
    # Flat layout
    for name in _ENTRY_FILES:
        p = folder / name
        if p.is_file():
            found.append(p)
    if found:
        return found

    # Nested package: holix_*/extension.py or */extension.py one level down
    try:
        children = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    for child in children:
        if child.name in ("tests", "docs", ".git", "dist", "build", "__pycache__"):
            continue
        for name in ("extension.py", "agent.py"):
            p = child / name
            if p.is_file():
                found.append(p)
    return found


def _scan_folders(profile: str | None, *, kind: str) -> list[Any]:
    """kind: 'agent' | 'host'"""
    found: list[Any] = []
    seen_names: set[str] = set()

    for root in iter_extension_roots(profile):
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            continue
        for folder in children:
            entries = _find_entry_files(folder)
            if not entries:
                continue
            for entry in entries:
                # Prefer extension.py for host, agent.py for agent
                if kind == "agent" and entry.name == "extension.py" and (folder / "agent.py").is_file():
                    continue
                if kind == "host" and entry.name == "agent.py" and any(
                    e.name == "extension.py" for e in entries
                ):
                    continue
                if kind == "agent" and entry.name not in ("agent.py", "__init__.py"):
                    # only load agent entry for agent kind unless it's the only file
                    if any(e.name == "agent.py" for e in entries):
                        continue
                if kind == "host" and entry.name == "agent.py":
                    # host kind does not load pure agent modules
                    continue

                mod_name = f"holix_local_{kind}_{folder.name}_{entry.parent.name}_{entry.stem}"
                package_roots = [folder]
                if entry.parent != folder:
                    package_roots.append(folder)  # repo root for nested package
                mod = _load_module_from_file(mod_name, entry, package_roots=package_roots)
                if mod is None:
                    continue
                if kind == "agent":
                    ext = _instantiate_agent_from_module(mod, folder.name)
                else:
                    ext = _instantiate_host_from_module(mod, folder.name)
                if ext is None:
                    continue
                name = str(getattr(ext, "name", "") or folder.name)
                if name in seen_names:
                    logger.debug("skipping duplicate local extension name %s", name)
                    continue
                seen_names.add(name)
                try:
                    ext._holix_local_path = str(folder.resolve())  # type: ignore[attr-defined]
                except Exception:
                    pass
                found.append(ext)
                logger.info(
                    "discovered local %s extension '%s' from %s",
                    kind,
                    name,
                    folder,
                )
                break  # one instance per folder
    return found


def discover_local_agent_extensions(profile: str | None = None) -> tuple[Any, ...]:
    """Scan extension folders for agent extensions (tools / middleware)."""
    return tuple(_scan_folders(profile, kind="agent"))


def discover_local_host_extensions(profile: str | None = None) -> tuple[Any, ...]:
    """Scan extension folders for host/telegram extensions (CLI, gateway, telegram)."""
    return tuple(_scan_folders(profile, kind="host"))


def purge_local_agent_extension_modules() -> int:
    """Drop cached local agent extension modules so the next discover re-imports.

    Used by hot-reload after the agent scaffolds or edits drop-in extensions.
    Returns the number of sys.modules keys removed.
    """
    prefix = "holix_local_agent_"
    to_drop = [k for k in list(sys.modules) if k.startswith(prefix)]
    for key in to_drop:
        try:
            del sys.modules[key]
        except KeyError:
            pass
    return len(to_drop)


def load_local_default_settings(folder: Path) -> dict[str, Any]:
    """Optional settings.default.yaml next to agent.py / extension.py."""
    import yaml

    for name in ("settings.default.yaml", "settings.default.yml", "settings.yaml"):
        path = folder / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            logger.debug("failed reading %s", path, exc_info=True)
    return {}
