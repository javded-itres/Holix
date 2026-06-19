"""Holix management: MCP servers, assignments, install."""

from __future__ import annotations

from typing import Any

from cli.core import ProfileManager
from core.mcp.installer import build_config_from_popular, install_from_git
from core.mcp.popular import get_popular_by_key, get_popular_list
from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import verify_api_key
from api.errors import client_safe_message
from api.schemas.holix import McpAssignmentsPatchRequest, McpInstallRequest, McpServerCreateRequest
from api.services.config_mask import mask_config_dict
from api.services.holix_deps import profile_access

router = APIRouter(prefix="/api/holix/profiles/{profile_id}/mcp", tags=["holix-mcp"])


def _require_profile(profile_id: str) -> tuple[ProfileManager, object]:
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return manager, manager.load_profile(profile_id)


async def _test_mcp_server(name: str, data: dict[str, Any]) -> list[str]:
    from core.mcp.manager import MCPManager

    mgr = MCPManager({name: data})
    await mgr.connect_all()
    try:
        await mgr.wait_ready([name], timeout=12.0)
    except Exception:
        pass
    adapters = mgr.get_tool_adapters([name])
    await mgr.disconnect_all()
    if not adapters:
        errs = getattr(mgr, "_last_errors", {})
        if name in errs:
            raise RuntimeError(errs[name])
    return [a.name for a in adapters]


@router.get("/servers")
async def list_servers(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = _require_profile(profile_id)
    servers = mask_config_dict({"mcp_servers": getattr(config, "mcp_servers", {}) or {}})["mcp_servers"]
    assignments = getattr(config, "mcp_assignments", {}) or {}
    return {"servers": servers, "assignments": assignments, "count": len(servers)}


@router.post("/servers")
async def create_server(
    profile_id: str,
    body: McpServerCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = _require_profile(profile_id)
    servers = dict(getattr(config, "mcp_servers", {}) or {})
    if body.name in servers:
        raise HTTPException(status_code=409, detail="Server already exists")

    data: dict[str, Any] = {
        "transport": body.transport,
        "default_risk_level": body.risk_level,
    }
    if body.transport == "stdio":
        data["command"] = body.command
        if body.args:
            data["args"] = body.args
        if body.env:
            data["env"] = body.env
    else:
        if not body.url:
            raise HTTPException(status_code=400, detail="url required for sse transport")
        data["url"] = body.url

    servers[body.name] = data
    config.mcp_servers = servers
    manager.save_profile(profile_id, config)
    return {"server": body.name, "reload_required": True}


@router.get("/servers/{server_name}")
async def get_server(
    profile_id: str,
    server_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = _require_profile(profile_id)
    servers = getattr(config, "mcp_servers", {}) or {}
    if server_name not in servers:
        raise HTTPException(status_code=404, detail="Server not found")
    masked = mask_config_dict({"mcp_servers": {server_name: servers[server_name]}})["mcp_servers"]
    return {"server": server_name, "config": masked[server_name]}


@router.delete("/servers/{server_name}")
async def delete_server(
    profile_id: str,
    server_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = _require_profile(profile_id)
    servers = dict(getattr(config, "mcp_servers", {}) or {})
    if server_name not in servers:
        raise HTTPException(status_code=404, detail="Server not found")
    servers.pop(server_name)
    assigns = dict(getattr(config, "mcp_assignments", {}) or {})
    for role, lst in list(assigns.items()):
        if server_name in (lst or []):
            assigns[role] = [x for x in lst if x != server_name]
    config.mcp_servers = servers
    config.mcp_assignments = assigns
    manager.save_profile(profile_id, config)
    return {"removed": server_name, "reload_required": True}


@router.post("/servers/{server_name}/test")
async def test_server(
    profile_id: str,
    server_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = _require_profile(profile_id)
    servers = getattr(config, "mcp_servers", {}) or {}
    if server_name not in servers:
        raise HTTPException(status_code=404, detail="Server not found")
    try:
        tools = await _test_mcp_server(server_name, servers[server_name])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=client_safe_message(exc),
        ) from exc
    return {"server": server_name, "ok": True, "tools": tools, "count": len(tools)}


@router.get("/assignments")
async def get_assignments(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = _require_profile(profile_id)
    return {"assignments": getattr(config, "mcp_assignments", {}) or {}}


@router.patch("/assignments")
async def patch_assignments(
    profile_id: str,
    body: McpAssignmentsPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = _require_profile(profile_id)
    servers = set((getattr(config, "mcp_servers", {}) or {}).keys())
    for role, lst in body.assignments.items():
        unknown = [s for s in lst if s not in servers]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown servers for '{role}': {', '.join(unknown)}",
            )
    config.mcp_assignments = body.assignments
    manager.save_profile(profile_id, config)
    return {"assignments": config.mcp_assignments, "reload_required": True}


@router.get("/popular")
async def list_popular(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    popular = []
    for entry in get_popular_list():
        popular.append({
            "key": entry.key,
            "display_name": entry.display_name,
            "category": entry.category,
            "description": entry.description,
            "repo_url": entry.repo_url,
        })
    return {"popular": popular, "count": len(popular)}


@router.post("/install")
async def install_server(
    profile_id: str,
    body: McpInstallRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = _require_profile(profile_id)
    servers = dict(getattr(config, "mcp_servers", {}) or {})

    if body.popular_key:
        pop = get_popular_by_key(body.popular_key)
        if pop is None:
            raise HTTPException(status_code=400, detail=f"Unknown popular server: {body.popular_key}")
        data = build_config_from_popular(pop, body.params)
        data["_source"] = "popular"
        name = body.popular_key
    elif body.git_url:
        data = install_from_git(body.git_url, auto_prepare_steps=True)
        data["_source"] = "git"
        name = body.git_url.rstrip("/").split("/")[-1].removesuffix(".git")
    else:
        raise HTTPException(status_code=400, detail="popular_key or git_url required")

    if name in servers:
        raise HTTPException(status_code=409, detail="Server already exists")

    servers[name] = data
    config.mcp_servers = servers
    manager.save_profile(profile_id, config)
    return {"server": name, "source": data.get("_source"), "reload_required": True}