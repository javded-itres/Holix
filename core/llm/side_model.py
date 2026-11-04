"""Cheap side model for titles, compaction, memory summaries, commit text.

``HOLIX_SMALL_MODEL`` wins, then ``settings.small_model``. When neither is
set, callers keep the session model so an unset side model changes nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def small_model_configured() -> bool:
    if os.environ.get("HOLIX_SMALL_MODEL", "").strip():
        return True
    try:
        from config import settings

        return bool(str(getattr(settings, "small_model", "") or "").strip())
    except Exception:
        return False


def resolve_small_model(main_model: str | None = None) -> str:
    env = os.environ.get("HOLIX_SMALL_MODEL", "").strip()
    if env:
        return env
    try:
        from config import settings

        configured = str(getattr(settings, "small_model", "") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return (main_model or "").strip()


def _titles_path(profile: str) -> Path | None:
    try:
        from core.profile.names import profile_dir_for_name

        return profile_dir_for_name(profile) / "data" / "session_titles.json"
    except Exception:
        return None


def get_session_title(profile: str, conversation_id: str) -> str:
    path = _titles_path(profile)
    if path is None or not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, dict):
        return ""
    return str(sessions.get(conversation_id or "default") or "").strip()


def set_session_title(profile: str, conversation_id: str, title: str) -> None:
    path = _titles_path(profile)
    if path is None:
        return
    payload: dict[str, Any] = {"sessions": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("sessions"), dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {"sessions": {}}
    payload.setdefault("sessions", {})
    payload["sessions"][conversation_id or "default"] = title.strip()[:80]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def complete_small(
    client: Any,
    main_model: str,
    *,
    system: str,
    user: str,
    max_tokens: int = 80,
) -> str:
    model = resolve_small_model(main_model)
    if client is None or not model:
        return ""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user[:4000]},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return str(response.choices[0].message.content or "").strip()


async def suggest_session_title(client: Any, main_model: str, user_text: str) -> str:
    raw = await complete_small(
        client,
        main_model,
        system="Reply with a session title of at most 6 words. No quotes.",
        user=user_text,
        max_tokens=24,
    )
    return " ".join(raw.split())[:80]


async def suggest_commit_message(client: Any, main_model: str, diff: str) -> str:
    raw = await complete_small(
        client,
        main_model,
        system="Write one git commit subject line. No quotes.",
        user=diff[:4000],
        max_tokens=40,
    )
    return " ".join(raw.split())[:120]


async def maybe_store_session_title(
    client: Any,
    main_model: str,
    *,
    profile: str,
    conversation_id: str,
    user_text: str,
) -> str:
    if not small_model_configured():
        return ""
    if get_session_title(profile, conversation_id):
        return ""
    text = (user_text or "").strip()
    if not text or text.startswith("Continue the session goal"):
        return ""
    try:
        title = await suggest_session_title(client, main_model, text)
    except Exception:
        return ""
    if not title:
        return ""
    set_session_title(profile, conversation_id, title)
    return title
