"""Persist messenger pins for background processes (Telegram / MAX)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from core.profile.names import profile_dir_for_name, validate_profile_name

logger = logging.getLogger(__name__)

PLATFORMS = ("telegram", "max")


def pins_path(bot_profile: str) -> Path:
    name = validate_profile_name(bot_profile)
    path = profile_dir_for_name(name) / "data" / "process_pins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def chat_key(platform: str, chat_id: int | str) -> str:
    plat = (platform or "").strip().lower() or "telegram"
    return f"{plat}:{chat_id}"


def _load(bot_profile: str) -> dict[str, Any]:
    path = pins_path(bot_profile)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(bot_profile: str, data: dict[str, Any]) -> None:
    path = pins_path(bot_profile)
    raw = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(raw, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def list_chat_pins(
    bot_profile: str, platform: str, chat_id: int | str
) -> dict[str, dict[str, Any]]:
    data = _load(bot_profile)
    raw = data.get(chat_key(platform, chat_id)) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pid, rec in raw.items():
        if isinstance(rec, dict) and pid:
            out[str(pid)] = rec
    return out


def save_pin(
    bot_profile: str,
    platform: str,
    chat_id: int | str,
    *,
    process_id: str,
    message_id: int | str,
    script_key: str,
    label: str = "",
    os_pid: int = 0,
) -> None:
    pid = (process_id or "").strip()
    if not pid:
        return
    data = _load(bot_profile)
    key = chat_key(platform, chat_id)
    bucket = data.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
    bucket[pid] = {
        "process_id": pid,
        "message_id": message_id,
        "script_key": script_key,
        "label": label,
        "os_pid": int(os_pid or 0),
    }
    data[key] = bucket
    _save(bot_profile, data)


def remove_pin(bot_profile: str, platform: str, chat_id: int | str, process_id: str) -> None:
    pid = (process_id or "").strip()
    if not pid:
        return
    data = _load(bot_profile)
    key = chat_key(platform, chat_id)
    bucket = data.get(key)
    if not isinstance(bucket, dict):
        return
    bucket.pop(pid, None)
    if bucket:
        data[key] = bucket
    else:
        data.pop(key, None)
    _save(bot_profile, data)


def same_script_process_ids(
    bot_profile: str,
    platform: str,
    chat_id: int | str,
    script_key: str,
    *,
    exclude: str = "",
) -> list[str]:
    want = (script_key or "").strip()
    if not want:
        return []
    skip = (exclude or "").strip()
    out: list[str] = []
    for pid, rec in list_chat_pins(bot_profile, platform, chat_id).items():
        if pid == skip:
            continue
        if str(rec.get("script_key") or "").strip() == want:
            out.append(pid)
    return out


def iter_platform_pins(bot_profile: str, platform: str) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield (chat_id, process_id, record) for one messenger."""
    prefix = f"{(platform or '').strip().lower()}:"
    data = _load(bot_profile)
    out: list[tuple[str, str, dict[str, Any]]] = []
    for key, bucket in data.items():
        if not str(key).startswith(prefix) or not isinstance(bucket, dict):
            continue
        chat_id = str(key)[len(prefix) :]
        for pid, rec in bucket.items():
            if isinstance(rec, dict):
                out.append((chat_id, str(pid), rec))
    return out


def hydrate_session_pins(
    session: Any,
    *,
    platform: str,
    chat_id: int | str,
    bot_profile: str,
) -> None:
    """Copy persisted pins into in-memory session maps."""
    pins = list_chat_pins(bot_profile, platform, chat_id)
    ids = getattr(session, "background_process_message_ids", None)
    keys = getattr(session, "background_process_script_keys", None)
    if ids is None:
        return
    for pid, rec in pins.items():
        mid = rec.get("message_id")
        if mid is None or mid == "":
            continue
        ids[pid] = mid
        if keys is not None:
            sk = str(rec.get("script_key") or "")
            if sk:
                keys[pid] = sk
