"""holix.plugin.json manifest loading."""

from __future__ import annotations

from core.extensions.base import ExtensionBase
from core.extensions.manifest import load_manifest_from_module, merge_manifest_into_extension


def test_load_studio_manifest_when_installed() -> None:
    manifest = load_manifest_from_module("holix_studio.extension")
    if manifest is None:
        return
    assert manifest.id == "studio"
    assert "cli" in manifest.capabilities or manifest.capabilities


def test_merge_manifest_into_extension() -> None:
    from core.extensions.manifest import PluginManifest

    class Ext(ExtensionBase):
        pass

    ext = Ext()
    manifest = PluginManifest(
        id="test-ext",
        version="2.0.0",
        requires_holix=">=0.2.0",
        description="Test",
        capabilities=frozenset({"cli"}),
        permissions=frozenset({"tools"}),
    )
    merge_manifest_into_extension(ext, manifest)
    assert ext.name == "test-ext"
    assert ext.version == "2.0.0"
    assert ext.requires_holix == ">=0.2.0"
    assert ext.capabilities == frozenset({"cli"})