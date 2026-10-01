"""Host-side media settings reader does not use core."""

from __future__ import annotations

from pathlib import Path

from holix_media.profile_files import litellm_base_url, load_media_settings


def test_load_media_settings_reads_yaml(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "holix"
    settings = home / "profiles" / "default" / "extension_settings"
    settings.mkdir(parents=True)
    (settings / "media.yaml").write_text(
        "enabled: true\n"
        "image_providers:\n"
        "  - id: zimage\n"
        "    type: openai_images\n"
        "    note: text-to-image\n"
        "    accepts_reference: false\n",
        encoding="utf-8",
    )
    (home / "global").mkdir()
    (home / "global" / "config.yaml").write_text(
        "providers:\n  litellm:\n    base_url: http://global.example/v1\n",
        encoding="utf-8",
    )
    (home / "profiles" / "default" / "config.yaml").write_text(
        "providers:\n  litellm:\n    base_url: http://profile.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOLIX_HOME", str(home))
    monkeypatch.delenv("HOLIX_PROFILE", raising=False)

    raw = load_media_settings("default")
    assert raw["enabled"] is True
    assert raw["image_providers"][0]["note"] == "text-to-image"
    assert raw["image_providers"][0]["accepts_reference"] is False
    assert litellm_base_url("default") == "http://profile.example/v1"
