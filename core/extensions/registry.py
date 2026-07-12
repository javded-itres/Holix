"""Load extensions via ``importlib.metadata`` entry points."""

from __future__ import annotations

import importlib
import logging
from functools import lru_cache
from importlib.metadata import version as pkg_version
from typing import Any

from core.extensions.base import ExtensionContext, ExtensionInfo, HolixExtension
from core.extensions.manifest import load_manifest_from_module, merge_manifest_into_extension
from core.extensions.permissions import PERMISSION_GATEWAY, enforce_permissions

logger = logging.getLogger(__name__)

ENTRYPOINT_GROUP = "holix.extensions"
_AGENT_ENTRYPOINT_GROUP = "holix.agent.extensions"

_loaded_extensions: list[HolixExtension] = []
_startup_done = False


def _entry_points_for_group(group: str) -> list[Any]:
    try:
        from importlib.metadata import entry_points
    except ImportError:
        from importlib_metadata import entry_points  # type: ignore[no-redef]

    try:
        eps = entry_points(group=group)
    except TypeError:
        eps = entry_points().get(group, [])
    return list(eps)


def _instantiate_extension(ep: Any) -> HolixExtension | None:
    try:
        obj = ep.load()
        if isinstance(obj, type):
            ext = obj()
        elif callable(obj):
            ext = obj()
        else:
            ext = obj
        if not isinstance(ext, HolixExtension):
            logger.warning("extension %s does not implement HolixExtension", ep.name)
            return None
        module = getattr(ep, "module", None) or str(ep.value).split(":", 1)[0]
        manifest = load_manifest_from_module(module)
        merge_manifest_into_extension(ext, manifest)
        if not getattr(ext, "name", ""):
            ext.name = ep.name
        return ext
    except Exception:
        logger.exception("failed to load extension %s", ep.name)
        return None


@lru_cache
def discover_extensions() -> tuple[HolixExtension, ...]:
    loaded: list[HolixExtension] = []
    for ep in sorted(_entry_points_for_group(ENTRYPOINT_GROUP), key=lambda e: e.name):
        ext = _instantiate_extension(ep)
        if ext is not None:
            loaded.append(ext)
    return tuple(loaded)


def get_extension(name: str) -> HolixExtension | None:
    for ext in discover_extensions():
        if ext.name == name:
            return ext
    return None


def list_extension_info() -> list[ExtensionInfo]:
    infos: list[ExtensionInfo] = []
    for ep in sorted(_entry_points_for_group(ENTRYPOINT_GROUP), key=lambda e: e.name):
        ext = _instantiate_extension(ep)
        if ext is None:
            continue
        module = getattr(ep, "module", None) or str(ep.value).split(":", 1)[0]
        top = module.split(".", 1)[0]
        manifest = load_manifest_from_module(module)
        infos.append(
            ExtensionInfo(
                name=ext.name,
                version=getattr(ext, "version", "0.0.0"),
                requires_holix=getattr(ext, "requires_holix", ">=0.1.0"),
                description=getattr(ext, "description", ""),
                capabilities=frozenset(getattr(ext, "capabilities", frozenset()) or ()),
                permissions=frozenset(getattr(ext, "permissions", frozenset()) or ()),
                package=top,
                entry_point=f"{ENTRYPOINT_GROUP}:{ep.name}",
                manifest_id=manifest.id if manifest else None,
            )
        )
    return infos


def _holix_version() -> str:
    try:
        return pkg_version("Holix")
    except Exception:
        return "0.0.0"


def startup_extensions(
    *,
    profile: str | None = None,
    data_dir: str | None = None,
) -> list[str]:
    """Call ``on_startup`` once per process."""
    global _startup_done, _loaded_extensions
    if _startup_done:
        return [ext.name for ext in _loaded_extensions]

    from core.paths import resolve_holix_default_data_dir

    ctx = ExtensionContext(
        holix_version=_holix_version(),
        data_dir=data_dir or str(resolve_holix_default_data_dir()),
        profile=profile,
    )
    names: list[str] = []
    for ext in discover_extensions():
        try:
            ext.on_startup(ctx)
            names.append(ext.name)
            _loaded_extensions.append(ext)
        except Exception:
            logger.exception("extension %s on_startup failed", ext.name)
    _startup_done = True
    return names


def shutdown_extensions() -> None:
    for ext in reversed(_loaded_extensions):
        try:
            ext.on_shutdown()
        except Exception:
            logger.exception("extension %s on_shutdown failed", ext.name)


def register_cli_extensions(root_app: Any) -> list[str]:
    startup_extensions()
    names: list[str] = []
    for ext in discover_extensions():
        try:
            ext.register_cli(root_app)
            names.append(ext.name)
        except Exception:
            logger.exception("extension %s CLI registration failed", ext.name)
    return names


def mount_gateway_extensions(app: Any) -> list[str]:
    startup_extensions()
    names: list[str] = []
    for ext in discover_extensions():
        if not enforce_permissions(ext, frozenset({PERMISSION_GATEWAY}), context="gateway"):
            continue
        try:
            ext.mount_gateway(app)
            names.append(ext.name)
        except Exception:
            logger.exception("extension %s gateway mount failed", ext.name)
    return names


def load_extension_module(dotted: str) -> Any:
    return importlib.import_module(dotted)