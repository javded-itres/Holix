"""Which model describes photos and which one transcribes audio.

The admin screen in Studio writes this into the global Holix config
(``extension_settings.recognition``). Every profile inherits it. A profile
file ``extension_settings/recognition.yaml`` can override that profile only.

An empty photo model means the session pin. Audio defaults to local faster-whisper.
"""

from __future__ import annotations

from typing import Any

LOCAL_AUDIO = "local"
_LOCAL_AUDIO_VALUES = frozenset({LOCAL_AUDIO, "faster-whisper", "whisper-local"})
_MAX_MODEL_LEN = 200


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _recognition_block(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    block = raw.get("extension_settings")
    if not isinstance(block, dict):
        return {}
    rec = block.get("recognition")
    return rec if isinstance(rec, dict) else {}


def _read_global_recognition() -> dict[str, Any]:
    """Read the saved block. Does not create a global config file."""
    try:
        import yaml
        from core.global_config import global_config_path

        path = global_config_path()
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return _recognition_block(data)


def load_recognition(profile: str) -> dict[str, str]:
    """Effective image and audio models for *profile*."""
    raw = _read_global_recognition()
    try:
        from core.extensions.settings import load_extension_settings

        loaded = load_extension_settings(profile or "default", "recognition")
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                if _clean(value):
                    raw[key] = value
    except Exception:
        pass
    image = _clean(raw.get("image_model"))
    audio = _clean(raw.get("audio_model")) or LOCAL_AUDIO
    return {"image_model": image, "audio_model": audio}


def audio_is_local(model: str) -> bool:
    return _clean(model).lower() in _LOCAL_AUDIO_VALUES


def save_recognition(*, image_model: str, audio_model: str) -> dict[str, str]:
    """Store the admin choice in the global Holix config."""
    image = _clean(image_model)
    audio = _clean(audio_model) or LOCAL_AUDIO
    if len(image) > _MAX_MODEL_LEN or len(audio) > _MAX_MODEL_LEN:
        raise ValueError("model name is too long")
    if any(ch in image or ch in audio for ch in "\n\r\x00"):
        raise ValueError("model name is invalid")

    import yaml
    from core.global_config import (
        deep_merge_dict,
        ensure_global_config,
        global_config_path,
        load_global_config_raw,
        strip_profile_only_keys,
    )

    ensure_global_config()
    current = load_global_config_raw()
    merged = deep_merge_dict(
        current,
        {
            "extension_settings": {
                "recognition": {"image_model": image, "audio_model": audio},
            }
        },
    )
    path = global_config_path()
    path.write_text(
        yaml.safe_dump(
            strip_profile_only_keys(merged),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return {"image_model": image, "audio_model": audio}
