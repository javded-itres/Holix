"""Holix management: model providers, agent routing, fallbacks."""

from __future__ import annotations

from cli.core import ProfileManager
from core.models.catalog import get_provider_preset, list_provider_presets
from core.models.profile_cleanup import remove_provider_from_profile
from core.models.setup_helpers import add_preset_to_config, apply_ssl_override, probe_provider
from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import verify_api_key
from api.errors import client_safe_message
from api.schemas.holix import AgentModelsPatchRequest, FallbacksPatchRequest, ProviderAddRequest
from api.services.config_mask import mask_config_dict
from api.services.holix_deps import profile_access

router = APIRouter(prefix="/api/holix/profiles/{profile_id}/models", tags=["holix-models"])


def _require_profile(profile_id: str) -> ProfileManager:
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return manager


@router.get("/presets")
async def list_presets(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    presets = []
    for preset in list_provider_presets():
        presets.append({
            "id": preset.id,
            "display_name": preset.display_name,
            "auth_type": preset.auth_type,
            "api_key_env": preset.api_key_env,
            "configurable_host": preset.configurable_host,
            "default_port": preset.default_port,
        })
    return {"presets": presets, "count": len(presets)}


@router.get("/providers")
async def list_providers(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    providers = mask_config_dict({"providers": config.providers or {}})["providers"]
    return {
        "providers": providers,
        "default_provider": config.default_provider,
        "count": len(providers),
    }


@router.post("/providers")
async def add_provider(
    profile_id: str,
    body: ProviderAddRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)

    preset = get_provider_preset(body.preset_id)
    if preset is None:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {body.preset_id}")

    metadata_extra = {}
    if body.no_verify_ssl:
        metadata_extra["verify_ssl"] = False

    ok, message = await add_preset_to_config(
        config,
        body.preset_id,
        provider_name=body.name,
        api_key=body.api_key,
        host=body.host,
        port=body.port,
        skip_probe=body.skip_test,
        metadata_extra=metadata_extra or None,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    manager.save_profile(profile_id, config)
    name = body.name or body.preset_id
    return {
        "provider": name,
        "message": client_safe_message(message),
        "reload_required": True,
    }


@router.delete("/providers/{provider_name}")
async def remove_provider(
    profile_id: str,
    provider_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    if provider_name not in (config.providers or {}):
        raise HTTPException(status_code=404, detail="Provider not found")

    notes = remove_provider_from_profile(config, provider_name)
    manager.save_profile(profile_id, config)
    return {"removed": provider_name, "notes": notes, "reload_required": True}


@router.post("/providers/{provider_name}/test")
async def test_provider(
    profile_id: str,
    provider_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    providers = config.providers or {}
    if provider_name not in providers:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider_data = providers[provider_name]
    metadata = apply_ssl_override(provider_data.get("metadata") or {})
    ok, models, err = await probe_provider(
        provider_data["base_url"],
        provider_data.get("api_key", "dummy"),
        metadata,
    )
    if ok and models:
        provider_data["available_models"] = [m["id"] for m in models if m.get("id")]
        config.providers[provider_name] = provider_data
        manager.save_profile(profile_id, config)

    return {
        "provider": provider_name,
        "ok": ok,
        "models_found": len(models),
        "models": [m.get("id") for m in models[:20]],
        "error": client_safe_message(err) if err else None,
        "reload_required": bool(ok and models),
    }


@router.get("/agent-models")
async def get_agent_models(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    return {"agent_models": config.agent_models or {}, "count": len(config.agent_models or {})}


@router.patch("/agent-models")
async def patch_agent_models(
    profile_id: str,
    body: AgentModelsPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    config.agent_models = body.agent_models
    manager.save_profile(profile_id, config)
    return {"agent_models": config.agent_models, "reload_required": True}


@router.get("/fallbacks")
async def get_fallbacks(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    return {"providers": config.fallback_providers or []}


@router.patch("/fallbacks")
async def patch_fallbacks(
    profile_id: str,
    body: FallbacksPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = _require_profile(profile_id)
    config = manager.load_profile(profile_id)
    unknown = [p for p in body.providers if p not in (config.providers or {})]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown providers: {', '.join(unknown)}")
    config.fallback_providers = body.providers
    manager.save_profile(profile_id, config)
    return {"providers": config.fallback_providers, "reload_required": True}