"""Read and write skills and MCP in the workspace `.holix` directory.

Profile files under ``~/.holix/profiles`` stay blocked. This directory adds
to the profile and overrides the same skill or MCP server name. Model,
providers, and auth are not stored here.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from core.tools.base import BaseTool

_SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class WorkspaceHolixTool(BaseTool):
    """Configure skills and MCP servers inside the current workspace."""

    def __init__(self) -> None:
        super().__init__()
        self._agent: Any = None
        self.name = "workspace_holix"
        self.description = (
            "Add or inspect skills and MCP servers in the workspace `.holix/` "
            "directory. Use this when the user asks to add a skill or connect "
            "an MCP server. Do not read or edit `~/.holix/profiles`. "
            "Actions: show, write_skill, remove_skill, upsert_mcp, remove_mcp, install_link. "
            "When the user pastes a skill or MCP link, use install_link. "
            "Files here add to the profile and override the same name. "
            "Model, providers, and auth cannot be set here."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "show",
                        "write_skill",
                        "remove_skill",
                        "upsert_mcp",
                        "remove_mcp",
                        "install_link",
                    ],
                    "description": "What to do in workspace .holix",
                },
                "link": {
                    "type": "string",
                    "description": (
                        "Skill or MCP URL for install_link: GitHub, GitLab, skills.sh, "
                        "ClawHub, a raw SKILL.md, or an http(s) endpoint ending in /mcp or /sse."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Skill slug or MCP server name",
                },
                "description": {
                    "type": "string",
                    "description": "One-line skill description",
                },
                "content": {
                    "type": "string",
                    "description": "Skill body (When to Use / Procedure / Pitfalls / Verification)",
                },
                "transport": {
                    "type": "string",
                    "enum": ["stdio", "sse", "http"],
                    "description": "stdio, sse, or http. http is started via npx mcp-remote.",
                },
                "command": {
                    "type": "string",
                    "description": "stdio executable (npx, uvx, docker, …)",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio arguments",
                },
                "url": {
                    "type": "string",
                    "description": "sse or http MCP URL. http is bridged with npx mcp-remote.",
                },
                "env": {
                    "type": "object",
                    "description": "Extra environment for this MCP server. Values are not echoed back.",
                    "additionalProperties": {"type": "string"},
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory for a stdio server",
                },
            },
            "required": ["action"],
        }

    def bind_agent(self, agent: Any) -> None:
        self._agent = agent

    async def execute(self, action: str = "show", **kwargs: Any) -> str:
        action = (action or "show").strip().lower()
        try:
            root = self._holix_dir()
        except ValueError as exc:
            return f"Error: {exc}"
        if action == "show":
            return self._show(root)
        if action == "write_skill":
            return self._write_skill(root, kwargs)
        if action == "remove_skill":
            return self._remove_skill(root, kwargs)
        if action == "upsert_mcp":
            return await self._upsert_mcp(root, kwargs)
        if action == "remove_mcp":
            return self._remove_mcp(root, kwargs)
        if action == "install_link":
            return await self._install_link(root, kwargs)
        return (
            "action must be show, write_skill, remove_skill, upsert_mcp, "
            "remove_mcp, or install_link."
        )

    def _workspace_root(self) -> Path | None:
        agent = self._agent
        cfg = getattr(agent, "config", None) if agent is not None else None
        raw = str(getattr(cfg, "workspace_root", None) or "").strip()
        if raw:
            return Path(raw).expanduser()
        try:
            from core.workspace import get_configured_workspace_root

            return get_configured_workspace_root()
        except Exception:
            return None

    def _holix_dir(self) -> Path:
        from core.config_utils import project_holix_dir

        ws = self._workspace_root()
        directory = project_holix_dir(workspace_root=str(ws) if ws else None).resolve()
        workspace = ws.resolve() if ws is not None else directory.parent.resolve()
        if directory != workspace and workspace not in directory.parents:
            raise ValueError("workspace .holix is outside the workspace")
        if directory.name != ".holix":
            raise ValueError("refusing to write outside .holix")
        return directory

    def _under(self, root: Path, *parts: str) -> Path:
        dest = root.joinpath(*parts).resolve()
        if dest != root and root not in dest.parents:
            raise ValueError("path escapes workspace .holix")
        return dest

    def _show(self, root: Path) -> str:
        lines = [f"Workspace Holix directory: {root}"]
        skills = root / "skills"
        if skills.is_dir():
            names = sorted(
                p.parent.name if p.name == "SKILL.md" else p.stem for p in _skill_files(skills)
            )
            lines.append("Skills: " + (", ".join(names) if names else "(none)"))
        else:
            lines.append("Skills: (none)")
        config = _read_config(root / "config.yaml")
        servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
        if not servers:
            lines.append("MCP servers: (none)")
        else:
            lines.append("MCP servers:")
            for name, spec in servers.items():
                if not isinstance(spec, dict):
                    lines.append(f"- {name}")
                    continue
                transport = spec.get("transport") or "stdio"
                target = spec.get("url") or spec.get("command") or ""
                lines.append(f"- {name}: {transport} {target}".rstrip())
        lines.append(
            "Same names override the profile. Profile config under ~/.holix/profiles is not readable here."
        )
        return "\n".join(lines)

    def _write_skill(self, root: Path, kwargs: dict[str, Any]) -> str:
        from core.hub.normalize import slugify_skill_name

        slug = slugify_skill_name(str(kwargs.get("name") or ""))
        if not slug:
            return "name is required."
        body = str(kwargs.get("content") or "").strip()
        if not body:
            return "content is required."
        description = str(kwargs.get("description") or slug).strip() or slug
        dest = self._under(root, "skills", slug, "SKILL.md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        front = {"name": slug, "description": description}
        dumped = yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
        dest.write_text(f"---\n{dumped}---\n\n{body}\n", encoding="utf-8")
        reloaded = self._reload_skills()
        note = "Loaded for this session." if reloaded else "Loaded on the next session start."
        shown = dest.relative_to(root.parent) if _is_relative(dest, root.parent) else dest
        return f"Wrote skill {slug} to {shown}. {note}"

    def _remove_skill(self, root: Path, kwargs: dict[str, Any]) -> str:
        from core.hub.normalize import slugify_skill_name

        slug = slugify_skill_name(str(kwargs.get("name") or ""))
        if not slug:
            return "name is required."
        folder = self._under(root, "skills", slug)
        flat = self._under(root, "skills", f"{slug}.md")
        removed = False
        if folder.is_dir():
            shutil.rmtree(folder)
            removed = True
        if flat.is_file():
            flat.unlink()
            removed = True
        if not removed:
            return f"No workspace skill named {slug}."
        self._reload_skills()
        return f"Removed workspace skill {slug}. The profile copy, if any, is unchanged."

    async def _install_link(self, root: Path, kwargs: dict[str, Any]) -> str:
        from core.hub.link_install import _redact_link, install_share_link

        raw = str(kwargs.get("link") or kwargs.get("url") or "").strip()
        if not raw:
            return "link is required."
        try:
            result = install_share_link(raw, skills_dir=self._under(root, "skills"))
        except Exception as exc:
            return f"Could not install {_redact_link(raw)}: {exc}"
        if result.mcp is not None:
            saved = await self._upsert_mcp(
                root,
                {"name": result.name, **result.mcp},
            )
            return f"{saved} Source: {result.detail}"
        names = ", ".join(result.skills) or result.name
        reloaded = self._reload_skills()
        note = "Loaded for this session." if reloaded else "Loaded on the next session start."
        return f"Installed skill {names} from {result.detail}. {note}"

    async def _upsert_mcp(self, root: Path, kwargs: dict[str, Any]) -> str:
        name = str(kwargs.get("name") or "").strip()
        if not _SERVER_NAME.fullmatch(name):
            return "name must be a short MCP server id (letters, digits, _, ., -)."
        transport = str(kwargs.get("transport") or "stdio").strip().lower()
        if transport not in {"stdio", "sse", "http"}:
            return "transport must be stdio, sse, or http."
        spec: dict[str, Any] = {"transport": transport}
        command = str(kwargs.get("command") or "").strip()
        url = str(kwargs.get("url") or "").strip()
        args = kwargs.get("args") or []
        if isinstance(args, str):
            args = [part for part in args.split() if part]
        if not isinstance(args, list):
            return "args must be a list of strings."
        spec["args"] = [str(item) for item in args if str(item).strip()]
        if transport == "stdio":
            if not command:
                return "stdio requires command."
            spec["command"] = command
        else:
            if not url:
                return f"{transport} requires url."
            spec["url"] = url
        cwd = str(kwargs.get("cwd") or "").strip()
        if cwd:
            spec["cwd"] = cwd
        env = kwargs.get("env") or {}
        if env:
            if not isinstance(env, dict):
                return "env must be an object of strings."
            spec["env"] = {str(key): str(value) for key, value in env.items()}
        if not spec.get("args"):
            spec.pop("args", None)
        from core.mcp.config import MCPServerConfig, validate_server_config

        errors = validate_server_config(MCPServerConfig.from_dict(name, spec))
        if errors:
            return "Invalid MCP server: " + "; ".join(errors)

        path = self._under(root, "config.yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_config(path)
        servers = (
            dict(data.get("mcp_servers") or {}) if isinstance(data.get("mcp_servers"), dict) else {}
        )
        servers[name] = spec
        data["mcp_servers"] = servers
        _write_config(path, data)
        self._remember_server(name, spec)
        connect = await self._connect(name, spec)
        return f"Saved MCP server {name} in .holix/config.yaml. {connect}"

    def _remove_mcp(self, root: Path, kwargs: dict[str, Any]) -> str:
        name = str(kwargs.get("name") or "").strip()
        if not _SERVER_NAME.fullmatch(name):
            return "name is required."
        path = root / "config.yaml"
        data = _read_config(path)
        servers = (
            dict(data.get("mcp_servers") or {}) if isinstance(data.get("mcp_servers"), dict) else {}
        )
        if name not in servers:
            return f"No workspace MCP server named {name}."
        del servers[name]
        data["mcp_servers"] = servers
        _write_config(path, data)
        return (
            f"Removed MCP server {name} from .holix/config.yaml. "
            "A server already connected in this process stays until the gateway restarts."
        )

    def _remember_server(self, name: str, spec: dict[str, Any]) -> None:
        agent = self._agent
        cfg = getattr(agent, "config", None) if agent is not None else None
        if cfg is None:
            return
        servers = dict(getattr(cfg, "mcp_servers", None) or {})
        servers[name] = spec
        assigns = dict(getattr(cfg, "mcp_assignments", None) or {})
        if "main" in assigns and name not in list(assigns.get("main") or []):
            assigns["main"] = [*(assigns.get("main") or []), name]
        try:
            agent.config = cfg.with_overrides(mcp_servers=servers, mcp_assignments=assigns)
        except Exception:
            try:
                cfg.mcp_servers = servers
                cfg.mcp_assignments = assigns
            except Exception:
                return

    async def _connect(self, name: str, spec: dict[str, Any]) -> str:
        agent = self._agent
        if agent is None or not hasattr(agent, "tools"):
            return "It applies on the next session start."
        if not bool(getattr(getattr(agent, "config", None), "mcp_enabled", True)):
            return "MCP is disabled on this profile, so the server was only saved."
        try:
            state = await agent.tools.connect_workspace_mcp(name, spec)
        except Exception as exc:
            return f"Saved, but connecting now failed: {exc}"
        if state == "started":
            return "Connected in this session."
        if state == "already_running":
            return "This server is already connected. A changed command applies after a gateway restart."
        if state == "unavailable":
            return "Saved. The MCP client library is not installed in this process."
        return "Saved."

    def _reload_skills(self) -> bool:
        agent = self._agent
        skills = getattr(agent, "skills", None) if agent is not None else None
        if skills is None or not hasattr(skills, "load_all_skills"):
            return False
        try:
            skills.load_all_skills(defer_index=True)
        except Exception:
            return False
        return True


def _skill_files(skills: Path) -> list[Path]:
    found: list[Path] = []
    if not skills.is_dir():
        return found
    for path in skills.rglob("SKILL.md"):
        found.append(path)
    for path in skills.glob("*.md"):
        found.append(path)
    return found


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(".holix/config.yaml must be a mapping")
    return loaded


def _write_config(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _is_relative(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
