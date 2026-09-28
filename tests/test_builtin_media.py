"""Bundled holix-media stays idle until a provider is actually configured."""

from holix_media.agent import get_agent_extension
from holix_media.config import load_media_config


def test_builtin_media_idle_without_settings(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("MIKROLLM_API_KEY", raising=False)
    monkeypatch.delenv("HOLIX_MEDIA_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("HOLIX_MEDIA_VIDEO_MODEL", raising=False)
    monkeypatch.delenv("HOLIX_MEDIA_ENABLED", raising=False)
    ext = get_agent_extension()
    assert ext.default_settings() == {}
    ext.on_settings_loaded({})
    assert not load_media_config(ext.settings).ready
    names: list[str] = []

    class Reg:
        def register(self, tool) -> None:
            names.append(tool.name)

    ext.register_tools(Reg(), agent=None)
    assert names == []
    assert ext.augment_system_prompt("default") is None
