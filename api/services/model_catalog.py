"""OpenAI-style model list for GET /v1/models."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.models.setup_helpers import probe_provider


def _openai_entry(model_id: str, *, owned_by: str, created: int) -> dict[str, Any]:
    return {
        "id": model_id,
        "object": "model",
        "created": created,
        "owned_by": owned_by,
    }


def collect_cached_model_entries(profile: str) -> list[dict[str, Any]]:
    """Return models configured for a profile (providers, agent slots, legacy)."""
    from cli.core import ProfileManager
    from core.models.manager import ModelManager

    try:
        cfg = ProfileManager().load_profile(profile)
    except Exception:
        return []

    created = int(time.time())
    seen: set[str] = set()
    data: list[dict[str, Any]] = []

    def add(model_id: str, owned_by: str) -> None:
        mid = (model_id or "").strip()
        if not mid or mid in seen:
            return
        seen.add(mid)
        data.append(_openai_entry(mid, owned_by=owned_by, created=created))

    for pname, pdata in sorted((cfg.providers or {}).items()):
        owner = pname or "holix"
        for mid in pdata.get("available_models") or []:
            add(str(mid), owner)
        add(str(pdata.get("default_model") or ""), owner)

    mm = ModelManager(cfg)
    default = mm.get_default_model_config()
    if default:
        add(default.model, default.provider)

    for slot in sorted((cfg.agent_models or {}).keys()):
        mc = mm.get_agent_model_config(slot)
        if mc:
            add(mc.model, mc.provider)

    if not data and cfg.model:
        add(cfg.model, "legacy")

    return data


async def discover_live_model_entries(profile: str) -> list[dict[str, Any]]:
    """Probe configured providers when cached model lists are empty."""
    from cli.core import ProfileManager

    try:
        cfg = ProfileManager().load_profile(profile)
    except Exception:
        return []

    providers = cfg.providers or {}
    if not providers:
        return []

    created = int(time.time())
    seen: set[str] = set()
    data: list[dict[str, Any]] = []

    async def probe_one(name: str, pdata: dict[str, Any]) -> None:
        base_url = str(pdata.get("base_url") or "").strip()
        if not base_url:
            return
        api_key = str(pdata.get("api_key") or "dummy")
        metadata = pdata.get("metadata") if isinstance(pdata.get("metadata"), dict) else {}
        ok, models, _ = await probe_provider(base_url, api_key, metadata)
        if not ok:
            return
        for item in models:
            mid = str(item.get("id") or "").strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            data.append(
                _openai_entry(
                    mid,
                    owned_by=str(item.get("owned_by") or name or "holix"),
                    created=int(item.get("created") or created),
                )
            )

    await asyncio.gather(*(probe_one(name, pdata) for name, pdata in providers.items()))
    return data


async def list_profile_models(profile: str, *, refresh: bool = False) -> list[dict[str, Any]]:
    """Models for GET /v1/models: cached config first, optional live provider probe."""
    data = collect_cached_model_entries(profile)
    if data and not refresh:
        return data
    live = await discover_live_model_entries(profile)
    if live:
        return live
    return data