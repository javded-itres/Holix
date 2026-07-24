"""Load extensions via ``importlib.metadata`` entry points."""

from __future__ import annotations

import importlib
import logging
import sys
from functools import lru_cache
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from core.extensions.base import ExtensionContext, ExtensionInfo, HolixExtension
from core.extensions.manifest import load_manifest_from_module, merge_manifest_into_extension
from core.extensions.permissions import PERMISSION_GATEWAY, enforce_permissions

logger = logging.getLogger(__name__)

ENTRYPOINT_GROUP = "holix.extensions"
AGENT_ENTRYPOINT_GROUP = "holix.agent.extensions"
TELEGRAM_ENTRYPOINT_GROUP = "holix.telegram.extensions"

_loaded_extensions: list[Any] = []
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


def _looks_like_host_extension(ext: Any) -> bool:
    """Duck-type host extensions (do not require runtime_checkable Protocol)."""
    if isinstance(ext, HolixExtension):
        return True
    # Custom packages may not inherit holix_sdk.ExtensionBase
    return any(
        callable(getattr(ext, name, None))
        for name in ("register_cli", "mount_gateway", "register_telegram", "on_startup")
    )


def _instantiate_extension(ep: Any) -> Any | None:
    try:
        obj = ep.load()
        if isinstance(obj, type):
            ext = obj()
        elif callable(obj):
            ext = obj()
        else:
            ext = obj
        if not _looks_like_host_extension(ext):
            logger.warning(
                "extension %s has no host hooks "
                "(register_cli/mount_gateway/register_telegram/on_startup)",
                ep.name,
            )
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
def _discover_entrypoint_host_extensions() -> tuple[Any, ...]:
    loaded: list[Any] = []
    for ep in sorted(_entry_points_for_group(ENTRYPOINT_GROUP), key=lambda e: e.name):
        ext = _instantiate_extension(ep)
        if ext is not None:
            loaded.append(ext)
    return tuple(loaded)


def discover_extensions(profile: str | None = None) -> tuple[Any, ...]:
    """Host extensions: pip entry points + drop-in folders.

    Local folders override the same *name* as an installed package (easier dev).
    """
    by_name: dict[str, Any] = {}
    for ext in _discover_entrypoint_host_extensions():
        name = str(getattr(ext, "name", "") or "")
        if name:
            by_name[name] = ext
    try:
        from core.env_loader import active_profile_name
        from core.extensions.local_loader import discover_local_host_extensions

        prof = profile or active_profile_name()
        for ext in discover_local_host_extensions(prof):
            name = str(getattr(ext, "name", "") or "")
            if name:
                by_name[name] = ext  # folder wins
    except Exception:
        logger.debug("local host extension discovery skipped", exc_info=True)
    return tuple(by_name.values())


def clear_extension_discovery_cache() -> None:
    """Clear caches so newly installed / dropped folders appear."""
    if hasattr(_discover_entrypoint_host_extensions, "cache_clear"):
        _discover_entrypoint_host_extensions.cache_clear()


def get_extension(name: str) -> Any | None:
    for ext in discover_extensions():
        if ext.name == name:
            return ext
    return None


def list_extension_info() -> list[ExtensionInfo]:
    """Host extensions (entry points + local folders), one row per name."""
    clear_extension_discovery_cache()
    infos: list[ExtensionInfo] = []
    for ext in discover_extensions():
        name = str(getattr(ext, "name", "") or "unnamed")
        local = getattr(ext, "_holix_local_path", None)
        package = Path(local).name if local else name
        infos.append(
            ExtensionInfo(
                name=name,
                version=str(getattr(ext, "version", "0.0.0") or "0.0.0"),
                requires_holix=str(getattr(ext, "requires_holix", ">=0.1.0") or ">=0.1.0"),
                description=str(getattr(ext, "description", "") or ""),
                capabilities=frozenset(getattr(ext, "capabilities", frozenset()) or ()),
                permissions=frozenset(getattr(ext, "permissions", frozenset()) or ()),
                package=str(package),
                entry_point=("folder:" + str(local)) if local else f"{ENTRYPOINT_GROUP}:{name}",
                manifest_id=None,
            )
        )
    return infos


def list_all_entrypoint_rows() -> list[dict[str, Any]]:
    """Unified rows for host / agent / telegram — **one row per extension name**.

    Kinds from multiple entry-point groups are merged (e.g. host+telegram →
    ``host,telegram``) so packages that register twice are not duplicated.
    """
    clear_extension_discovery_cache()
    by_name: dict[str, dict[str, Any]] = {}

    def _upsert(
        name: str,
        *,
        kind: str,
        version: str = "—",
        requires: str = "—",
        caps: str = "—",
        package: str = "—",
        entry_point: str = "",
        status: str = "ok",
        error: str = "",
        source: str = "package",
    ) -> None:
        key = (name or "").strip() or "unnamed"
        row = by_name.get(key)
        if row is None:
            by_name[key] = {
                "name": key,
                "kind": kind,
                "version": version,
                "requires_holix": requires,
                "capabilities": caps,
                "package": package,
                "entry_point": entry_point,
                "status": status,
                "error": error,
                "source": source,
            }
            return
        # Merge kinds
        kinds = {k.strip() for k in str(row["kind"]).split(",") if k.strip()}
        kinds.add(kind)
        row["kind"] = ",".join(sorted(kinds))
        if version and version != "—" and row["version"] in ("—", "", None):
            row["version"] = version
        if requires and requires != "—" and row["requires_holix"] in ("—", "", None):
            row["requires_holix"] = requires
        if caps and caps != "—" and row["capabilities"] in ("—", "", None):
            row["capabilities"] = caps
        if entry_point and entry_point not in str(row["entry_point"]):
            row["entry_point"] = f"{row['entry_point']}; {entry_point}".strip("; ")
        if source == "folder":
            row["source"] = "folder"
        if status == "fail":
            row["status"] = "fail"
            if error:
                row["error"] = error

    # Host (includes local folders)
    for ext in discover_extensions():
        name = str(getattr(ext, "name", "") or "unnamed")
        local = getattr(ext, "_holix_local_path", None)
        kinds = ["host"]
        if callable(getattr(ext, "register_telegram", None)):
            kinds.append("telegram")
        if callable(getattr(ext, "register_tools", None)):
            kinds.append("agent")
        _upsert(
            name,
            kind=",".join(kinds),
            version=str(getattr(ext, "version", "0.0.0") or "0.0.0"),
            requires=str(getattr(ext, "requires_holix", ">=0.1.0") or ""),
            caps=", ".join(sorted(getattr(ext, "capabilities", frozenset()) or ())) or "—",
            package=Path(local).name if local else name,
            entry_point=("folder:" + str(local)) if local else f"{ENTRYPOINT_GROUP}:{name}",
            source="folder" if local else "package",
        )

    # Extra agent entry points not already covered
    for ep in sorted(_entry_points_for_group(AGENT_ENTRYPOINT_GROUP), key=lambda e: e.name):
        try:
            obj = ep.load()
            inst = obj() if isinstance(obj, type) else (obj() if callable(obj) else obj)
            name = str(getattr(inst, "name", None) or ep.name)
            if name in by_name:
                _upsert(name, kind="agent", entry_point=f"{AGENT_ENTRYPOINT_GROUP}:{ep.name}")
                continue
            _upsert(
                name,
                kind="agent",
                version=str(getattr(inst, "version", "0.0.0") or "0.0.0"),
                requires=str(getattr(inst, "requires_holix", ">=0.1.0") or ""),
                package=str(ep.value).split(":", 1)[0].split(".", 1)[0],
                entry_point=f"{AGENT_ENTRYPOINT_GROUP}:{ep.name}",
            )
        except Exception as exc:
            _upsert(ep.name, kind="agent", status="fail", error=str(exc)[:80],
                    entry_point=f"{AGENT_ENTRYPOINT_GROUP}:{ep.name}")

    # Telegram-only entry points (skip if already listed via host)
    for ep in sorted(_entry_points_for_group(TELEGRAM_ENTRYPOINT_GROUP), key=lambda e: e.name):
        try:
            obj = ep.load()
            inst = obj() if isinstance(obj, type) else (obj() if callable(obj) else obj)
            name = str(getattr(inst, "name", None) or ep.name)
            if name in by_name:
                _upsert(name, kind="telegram", entry_point=f"{TELEGRAM_ENTRYPOINT_GROUP}:{ep.name}")
                continue
            _upsert(
                name,
                kind="telegram",
                version=str(getattr(inst, "version", "0.0.0") or "0.0.0"),
                requires=str(getattr(inst, "requires_holix", ">=0.1.0") or ""),
                package=str(ep.value).split(":", 1)[0].split(".", 1)[0],
                entry_point=f"{TELEGRAM_ENTRYPOINT_GROUP}:{ep.name}",
            )
        except Exception as exc:
            _upsert(ep.name, kind="telegram", status="fail", error=str(exc)[:80],
                    entry_point=f"{TELEGRAM_ENTRYPOINT_GROUP}:{ep.name}")

    # Local agent folders not yet listed
    try:
        from core.env_loader import active_profile_name
        from core.extensions.local_loader import discover_local_agent_extensions

        for ext in discover_local_agent_extensions(active_profile_name()):
            name = str(getattr(ext, "name", "") or "")
            if not name or name in by_name:
                if name in by_name:
                    _upsert(name, kind="agent", source="folder")
                continue
            local = getattr(ext, "_holix_local_path", None)
            _upsert(
                name,
                kind="agent",
                version=str(getattr(ext, "version", "0.0.0") or "0.0.0"),
                package=Path(local).name if local else name,
                entry_point=f"folder:{local}" if local else name,
                source="folder",
            )
    except Exception:
        logger.debug("local agent list skipped", exc_info=True)

    return sorted(by_name.values(), key=lambda r: str(r["name"]))


def holix_install_hint() -> str:
    """How to add extensions without system pip (preferred: drop-in folder)."""
    try:
        from core.env_loader import holix_home

        ext_dir = holix_home() / "extensions"
    except Exception:
        ext_dir = Path("~/.holix/extensions").expanduser()
    py = sys.executable
    return (
        "Preferred — clone/copy into Holix extensions folder (no pip):\n"
        f"  mkdir -p {ext_dir}\n"
        f"  git clone <repo-url> {ext_dir}/<name>\n"
        f"  # or: cp -R ./my-ext {ext_dir}/my-ext\n"
        "Then: holix extensions list\n"
        "Optional pip into this CLI env only:\n"
        f"  uv pip install -e /path/to/ext --python {py}\n"
        f"Current interpreter: {py}"
    )


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
        return [getattr(ext, "name", "?") for ext in _loaded_extensions]

    from core.paths import resolve_holix_default_data_dir

    clear_extension_discovery_cache()
    ctx = ExtensionContext(
        holix_version=_holix_version(),
        data_dir=data_dir or str(resolve_holix_default_data_dir()),
        profile=profile,
    )
    names: list[str] = []
    for ext in discover_extensions():
        try:
            if hasattr(ext, "on_startup") and callable(ext.on_startup):
                ext.on_startup(ctx)
            names.append(str(getattr(ext, "name", type(ext).__name__)))
            _loaded_extensions.append(ext)
        except Exception:
            logger.exception("extension %s on_startup failed", getattr(ext, "name", "?"))
    _startup_done = True
    return names


def shutdown_extensions() -> None:
    for ext in reversed(_loaded_extensions):
        try:
            if hasattr(ext, "on_shutdown") and callable(ext.on_shutdown):
                ext.on_shutdown()
        except Exception:
            logger.exception("extension %s on_shutdown failed", getattr(ext, "name", "?"))


def register_cli_extensions(root_app: Any) -> list[str]:
    # Use the same instances that received on_startup (local drop-ins are
    # re-instantiated on every discover_extensions() call otherwise).
    startup_extensions()
    names: list[str] = []
    for ext in _loaded_extensions:
        try:
            if hasattr(ext, "register_cli") and callable(ext.register_cli):
                ext.register_cli(root_app)
            names.append(str(getattr(ext, "name", type(ext).__name__)))
        except Exception:
            logger.exception("extension %s CLI registration failed", getattr(ext, "name", "?"))
    return names


def mount_gateway_extensions(app: Any) -> list[str]:
    # Must mount the *same* extension instances that ran on_startup so
    # stateful fields (e.g. billing ``_service``) are visible to HTTP routes.
    startup_extensions()
    names: list[str] = []
    for ext in _loaded_extensions:
        if not enforce_permissions(ext, frozenset({PERMISSION_GATEWAY}), context="gateway"):
            continue
        try:
            if hasattr(ext, "mount_gateway") and callable(ext.mount_gateway):
                ext.mount_gateway(app)
            names.append(str(getattr(ext, "name", type(ext).__name__)))
        except Exception:
            logger.exception("extension %s gateway mount failed", getattr(ext, "name", "?"))
    return names


def load_extension_module(dotted: str) -> Any:
    return importlib.import_module(dotted)
