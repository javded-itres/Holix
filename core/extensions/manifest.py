"""Load ``holix.plugin.json`` from installed extension packages."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "holix.plugin.json"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Declarative extension metadata (VS Code / Chrome extension style)."""

    id: str
    version: str
    requires_holix: str
    description: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_manifest(data: dict[str, Any]) -> PluginManifest | None:
    ext_id = str(data.get("id") or "").strip()
    if not ext_id:
        return None
    requires = data.get("requires") or {}
    holix_req = ">=0.1.0"
    if isinstance(requires, dict):
        holix_req = str(requires.get("holix") or holix_req)
    caps_raw = data.get("capabilities") or {}
    caps: set[str] = set()
    if isinstance(caps_raw, dict):
        caps = {str(k) for k in caps_raw.keys()}
    elif isinstance(caps_raw, list):
        caps = {str(c) for c in caps_raw}
    perms_raw = data.get("permissions") or []
    perms = frozenset(str(p) for p in perms_raw) if perms_raw else frozenset()
    return PluginManifest(
        id=ext_id,
        version=str(data.get("version") or "0.0.0"),
        requires_holix=holix_req,
        description=str(data.get("description") or ""),
        capabilities=frozenset(caps),
        permissions=perms,
        raw=data,
    )


def load_manifest_from_module(module_name: str) -> PluginManifest | None:
    """Read holix.plugin.json from the top-level package of an entry point module."""
    top = module_name.split(".", 1)[0]
    try:
        pkg = resources.files(top)
    except (ModuleNotFoundError, TypeError):
        return None
    manifest_path = pkg.joinpath(MANIFEST_FILENAME)
    try:
        if not manifest_path.is_file():
            return None
        text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return _parse_manifest(data)
    except Exception:
        logger.debug("failed to load manifest for %s", top, exc_info=True)
        return None


def merge_manifest_into_extension(ext: Any, manifest: PluginManifest | None) -> None:
    """Apply manifest fields when extension class left defaults empty."""
    if manifest is None:
        return
    if not getattr(ext, "name", ""):
        ext.name = manifest.id
    if getattr(ext, "version", "0.0.0") in ("", "0.0.0"):
        ext.version = manifest.version
    if getattr(ext, "requires_holix", ">=0.1.0") == ">=0.1.0":
        ext.requires_holix = manifest.requires_holix
    if not getattr(ext, "description", ""):
        ext.description = manifest.description
    if not getattr(ext, "capabilities", frozenset()):
        ext.capabilities = manifest.capabilities
    if not getattr(ext, "permissions", frozenset()):
        ext.permissions = manifest.permissions