"""Per-conversation model choice persistence (TUI, Telegram, CLI hosts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cli.core import ProfileManager


class SessionModelRecord(BaseModel):
    slot_id: str
    label: str
    provider: str
    model: str


class SessionModelStoreData(BaseModel):
    version: int = 1
    sessions: dict[str, SessionModelRecord] = Field(default_factory=dict)


def session_models_path(profile: str) -> Path:
    d = ProfileManager().get_profile_dir(profile) / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "session_models.json"


class SessionModelStore:
    def __init__(self, profile: str = "default") -> None:
        self.profile = profile
        self._path = session_models_path(profile)

    def load(self) -> SessionModelStoreData:
        if not self._path.exists():
            return SessionModelStoreData()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return SessionModelStoreData.model_validate(data)
        except Exception:
            return SessionModelStoreData()

    def save(self, store: SessionModelStoreData) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(store.model_dump_json(indent=2), encoding="utf-8")

    def get(self, conversation_id: str) -> SessionModelRecord | None:
        if not conversation_id:
            return None
        return self.load().sessions.get(conversation_id)

    def set(self, conversation_id: str, record: SessionModelRecord) -> None:
        if not conversation_id:
            return
        store = self.load()
        store.sessions[conversation_id] = record
        self.save(store)

    def remove(self, conversation_id: str) -> None:
        store = self.load()
        if conversation_id in store.sessions:
            del store.sessions[conversation_id]
            self.save(store)


def host_conversation_id(host: Any) -> str:
    cid = getattr(host, "conversation_id", None)
    if cid:
        return str(cid)
    session = getattr(host, "_session", None)
    if session is not None:
        return str(getattr(session, "conversation_id", "") or "")
    return ""


def host_profile(host: Any) -> str:
    return getattr(host, "profile", None) or getattr(
        getattr(host, "_session", None), "profile", "default"
    )


def persist_session_model(host: Any, choice: Any) -> None:
    """Save model pick for the host's current conversation."""
    from integrations.telegram.model_switch import ModelChoice

    cid = host_conversation_id(host)
    if not cid:
        return
    if isinstance(choice, ModelChoice):
        record = SessionModelRecord(
            slot_id=choice.slot_id,
            label=choice.label,
            provider=choice.provider,
            model=choice.model,
        )
    elif isinstance(choice, SessionModelRecord):
        record = choice
    else:
        return
    SessionModelStore(host_profile(host)).set(cid, record)


def default_model_choice(profile: str) -> Any | None:
    from integrations.telegram.model_switch import ModelChoice, build_models_menu

    menu = build_models_menu(profile)
    if menu.presets:
        return menu.presets[0]
    if menu.providers and menu.providers[0].models:
        p = menu.providers[0]
        mid = p.models[0]
        return ModelChoice(
            slot_id=f"prov:{p.name}:{mid}",
            label=mid,
            provider=p.name,
            model=mid,
        )
    return None


def restore_session_model(host: Any, *, profile: str | None = None) -> str | None:
    """Apply saved model for current conversation, or profile default if unset."""
    from integrations.telegram.model_switch import ModelChoice, apply_model_choice_sync

    prof = profile or host_profile(host)
    cid = host_conversation_id(host)
    if not cid or not getattr(host, "agent", None):
        return None

    store = SessionModelStore(prof)
    saved = store.get(cid)
    if saved:
        choice = ModelChoice(
            slot_id=saved.slot_id,
            label=saved.label,
            provider=saved.provider,
            model=saved.model,
        )
    else:
        choice = default_model_choice(prof)
        if choice is None:
            return None

    try:
        label = apply_model_choice_sync(host, choice, profile=prof, persist=False)
        _mark_model_synced(host, cid)
        return label
    except Exception:
        return None


def _mark_model_synced(host: Any, conversation_id: str) -> None:
    session = getattr(host, "_session", None)
    if session is not None:
        session._model_synced_for = conversation_id
    else:
        host._model_synced_for = conversation_id


def ensure_session_model(host: Any) -> str | None:
    """Restore session model once per conversation_id (e.g. Telegram per message)."""
    cid = host_conversation_id(host)
    if not cid or not getattr(host, "agent", None):
        return None
    session = getattr(host, "_session", None)
    synced = (
        getattr(session, "_model_synced_for", None)
        if session is not None
        else getattr(host, "_model_synced_for", None)
    )
    if synced == cid:
        return None
    return restore_session_model(host)